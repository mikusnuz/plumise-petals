FROM python:3.10-slim as builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml setup.py ./
COPY src/ ./src/
COPY contracts/ ./contracts/

RUN pip install --no-cache-dir --upgrade pip wheel && \
    pip install --no-cache-dir grpcio-tools && \
    pip install --no-cache-dir "setuptools<70" && \
    pip install --no-cache-dir --no-build-isolation hivemind==1.1.10.post2 && \
    pip install --no-cache-dir "torch>=2.1,<2.2" "transformers>=4.32,<4.35" accelerate huggingface-hub \
        safetensors tokenizers sentencepiece bitsandbytes \
        web3 eth-account aiohttp click python-dotenv pydantic pydantic-settings && \
    pip install --no-cache-dir --no-deps petals && \
    pip install --no-cache-dir --no-deps -e .

FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/root/.cache/huggingface

VOLUME ["/root/.cache/huggingface"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PETALS_PORT:-31330}/health || exit 1

ENTRYPOINT ["plumise-petals"]
CMD ["serve"]
