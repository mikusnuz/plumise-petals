"""FastAPI HTTP gateway for Petals inference.

Exposes REST endpoints that the plumise-inference-api can call:
- GET  /health          → readiness check
- POST /api/v1/generate → text generation via Petals DHT
"""

from __future__ import annotations

import asyncio
import logging
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field as PydanticField

if TYPE_CHECKING:
    from plumise_petals.server.plumise_server import PlumiseServer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    inputs: str
    parameters: Optional[GenerateParams] = None
    stream: bool = False


class GenerateParams(BaseModel):
    max_new_tokens: int = PydanticField(default=128, ge=1, le=4096)
    temperature: float = PydanticField(default=0.7, ge=0.0, le=2.0)
    top_p: float = PydanticField(default=0.9, ge=0.0, le=1.0)
    do_sample: bool = True


# Fix forward reference
GenerateRequest.update_forward_refs()


class GenerateResponse(BaseModel):
    generated_text: str
    num_tokens: int


# ---------------------------------------------------------------------------
# Inference engine (loads Petals client)
# ---------------------------------------------------------------------------

class InferenceEngine:
    """Wraps Petals distributed model for HTTP-based inference."""

    def __init__(self, model_name: str, initial_peers: list[str], dht_prefix: str) -> None:
        self.model_name = model_name
        self.initial_peers = initial_peers
        self.dht_prefix = dht_prefix
        self.model = None
        self.tokenizer = None
        self.ready = False
        self._lock = threading.Lock()

    def load(self) -> None:
        """Load model and tokenizer. Called in a background thread."""
        try:
            from petals import AutoDistributedModelForCausalLM  # type: ignore
            from transformers import AutoTokenizer

            logger.info("Loading tokenizer: %s", self.model_name)
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token

            logger.info(
                "Loading distributed model: %s (peers=%s, prefix=%s)",
                self.model_name,
                self.initial_peers or "(bootstrap)",
                self.dht_prefix,
            )
            self.model = AutoDistributedModelForCausalLM.from_pretrained(
                self.model_name,
                initial_peers=self.initial_peers,
                dht_prefix=self.dht_prefix,
            )
            self.model.eval()
            self.ready = True
            logger.info("Inference engine ready")
        except Exception:
            logger.exception("Failed to load inference engine")

    def generate(self, prompt: str, max_new_tokens: int = 128,
                 temperature: float = 0.7, top_p: float = 0.9,
                 do_sample: bool = True) -> tuple[str, int]:
        """Generate text from prompt. Returns (generated_text, num_tokens)."""
        if not self.ready:
            raise RuntimeError("Model not ready")

        with self._lock:
            inputs = self.tokenizer(prompt, return_tensors="pt")
            input_len = inputs["input_ids"].shape[1]

            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    temperature=max(temperature, 0.01),
                    top_p=top_p,
                    do_sample=do_sample,
                )

            new_tokens = outputs[0][input_len:]
            generated_text = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
            num_tokens = len(new_tokens)

            return generated_text, num_tokens


# ---------------------------------------------------------------------------
# FastAPI application factory
# ---------------------------------------------------------------------------

def create_app(
    plumise_server: Optional["PlumiseServer"] = None,
    model_name: str = "bigscience/bloom-560m",
    initial_peers: Optional[list[str]] = None,
    dht_prefix: str = "plumise",
) -> FastAPI:
    """Create the FastAPI application.

    Args:
        plumise_server: If provided, inference metrics are recorded.
        model_name: HuggingFace model name.
        initial_peers: DHT bootstrap peers.
        dht_prefix: DHT namespace prefix.
    """
    app = FastAPI(title="Plumise Petals API", version="0.1.0")
    engine = InferenceEngine(model_name, initial_peers or [], dht_prefix)

    # Load model in background thread (don't block startup)
    load_thread = threading.Thread(target=engine.load, name="model-loader", daemon=True)
    load_thread.start()

    @app.get("/health")
    async def health():
        if engine.ready:
            return {"status": "ok", "model": model_name}
        return {"status": "loading", "model": model_name}

    @app.post("/api/v1/generate", response_model=GenerateResponse)
    async def generate(request: GenerateRequest):
        if not engine.ready:
            raise HTTPException(status_code=503, detail="Model is still loading")

        params = request.parameters or GenerateParams()
        start = time.time()

        try:
            loop = asyncio.get_event_loop()
            generated_text, num_tokens = await loop.run_in_executor(
                None,
                lambda: engine.generate(
                    prompt=request.inputs,
                    max_new_tokens=params.max_new_tokens,
                    temperature=params.temperature,
                    top_p=params.top_p,
                    do_sample=params.do_sample,
                ),
            )
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            logger.exception("Inference failed")
            raise HTTPException(status_code=500, detail=f"Inference error: {e}")

        latency_ms = (time.time() - start) * 1000

        # Record metrics if PlumiseServer is available
        if plumise_server is not None:
            plumise_server.record_inference(
                input_data=request.inputs,
                output_data=generated_text,
                token_count=num_tokens,
                latency_ms=latency_ms,
            )

        return GenerateResponse(generated_text=generated_text, num_tokens=num_tokens)

    return app


def run_api_server(
    app: FastAPI,
    host: str = "0.0.0.0",
    port: int = 31331,
) -> None:
    """Run the API server (blocking). Intended to be called in a thread."""
    logger.info("Starting API server on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="warning")
