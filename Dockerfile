FROM python:3.10-slim as builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml setup.py ./
COPY src/ ./src/
COPY contracts/ ./contracts/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        torch>=1.12 \
        "transformers>=4.32.0,<4.35.0" \
        hivemind==1.1.10.post2 \
        "accelerate>=0.22.0" \
        "huggingface-hub>=0.11.1,<1.0.0" \
        "safetensors>=0.3.1" \
        "tokenizers>=0.13.3" \
        "sentencepiece>=0.1.99" \
        bitsandbytes==0.41.1 \
        tensor-parallel==1.0.23 \
        peft==0.5.0 \
        speedtest-cli==2.1.3 \
        humanfriendly \
        "async-timeout>=4.0.2" \
        "packaging>=20.9" \
        "Dijkstar>=2.6.0" \
        cpufeature \
        web3 eth-account aiohttp click python-dotenv \
        pydantic pydantic-settings && \
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
