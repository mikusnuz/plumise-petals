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
    printf "torch>=2.1,<2.2\npydantic>=1.10,<2\ntransformers>=4.32,<4.35\nhuggingface-hub>=0.21,<0.25\naccelerate>=0.25,<0.28\nnumpy>=1.24,<2\n" > /tmp/constraints.txt && \
    pip install --no-cache-dir -c /tmp/constraints.txt "torch>=2.1,<2.2" grpcio-tools && \
    pip install --no-cache-dir "setuptools<70" && \
    pip install --no-cache-dir --no-build-isolation -c /tmp/constraints.txt hivemind==1.1.10.post2 && \
    pip install --no-cache-dir -c /tmp/constraints.txt "transformers>=4.32,<4.35" "accelerate>=0.25,<0.28" "huggingface-hub>=0.21,<0.25" \
        safetensors tokenizers sentencepiece bitsandbytes \
        web3 eth-account aiohttp click python-dotenv "pydantic>=1.10,<2" && \
    pip install --no-cache-dir -c /tmp/constraints.txt petals && \
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
