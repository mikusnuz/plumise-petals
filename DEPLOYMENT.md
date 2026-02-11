# Plumise Petals - Docker Deployment Guide

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- At least 4GB free disk space (for model cache)
- Plumise chain RPC access

## Quick Start

### 1. Prepare Environment

```bash
# Copy the appropriate env file based on your server
cp .env.server-1 .env    # For server-1
# or
cp .env.server-2 .env    # For server-2

# Edit .env if needed
nano .env
```

### 2. Build and Run

```bash
# Build the Docker image
docker compose build

# Start the service
docker compose up -d

# Check logs
docker compose logs -f
```

### 3. Verify

```bash
# Check container status
docker compose ps

# Check health
curl http://localhost:31330/health

# View logs
docker compose logs --tail=100 -f
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PLUMISE_RPC_URL` | Plumise chain RPC endpoint | `http://localhost:26902` |
| `PLUMISE_CHAIN_ID` | Chain ID | `41956` |
| `PLUMISE_PRIVATE_KEY` | Private key for signing | Required |
| `ORACLE_API_URL` | Oracle API endpoint | `http://localhost:15481` |
| `REPORT_INTERVAL` | Report interval in seconds | `60` |
| `MODEL_NAME` | HuggingFace model name | `bigscience/bloom-560m` |
| `NUM_BLOCKS` | Number of blocks to serve | `12` |
| `PETALS_HOST` | Server bind address | `0.0.0.0` |
| `PETALS_PORT` | Server port | `31330` |

### Model Cache

The model files are cached in `./model-cache` directory. First run will download the model (~300MB for bloom-560m).

To clean the cache:

```bash
docker compose down
rm -rf model-cache
```

## Multi-Node Setup

### Server-1 (192.168.0.200)

```bash
# Use .env.server-1
cp .env.server-1 .env
docker compose up -d
```

### Server-2 (192.168.0.202)

```bash
# Use .env.server-2
cp .env.server-2 .env
docker compose up -d
```

Both nodes will:
- Serve 12 blocks each (total 24 blocks for bloom-560m)
- Discover each other via Petals P2P network
- Report metrics to the oracle

## Troubleshooting

### Container won't start

```bash
# Check logs
docker compose logs

# Check if port 31330 is available
netstat -tuln | grep 31330
```

### Model download fails

```bash
# Check HuggingFace connectivity
curl -I https://huggingface.co

# Manually download (optional)
docker compose run --rm plumise-petals python -c "from transformers import AutoModel; AutoModel.from_pretrained('bigscience/bloom-560m')"
```

### P2P connection issues

```bash
# Check if host network mode is working
docker compose exec plumise-petals netstat -tuln | grep 31330

# Restart container
docker compose restart
```

## Monitoring

### Check Metrics

```bash
# View recent reports
docker compose logs | grep "Reporting metrics"

# Check oracle API
curl http://localhost:15481/metrics
```

### Resource Usage

```bash
# CPU and memory usage
docker stats plumise-petals

# Disk usage (model cache)
du -sh model-cache
```

## Maintenance

### Update

```bash
# Pull latest code
git pull

# Rebuild and restart
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Cleanup

```bash
# Stop and remove container
docker compose down

# Remove model cache
rm -rf model-cache

# Remove Docker image
docker rmi plumise-petals
```

## Production Checklist

- [ ] Set unique `PLUMISE_PRIVATE_KEY` per server
- [ ] Configure correct `ORACLE_API_URL`
- [ ] Ensure `NUM_BLOCKS=12` for 2-node setup
- [ ] Verify network connectivity between nodes
- [ ] Monitor logs for P2P discovery
- [ ] Check disk space for model cache
- [ ] Set up log rotation (already configured in docker-compose.yml)
- [ ] Configure firewall rules for port 31330 (P2P)

## Network Architecture

```
bloom-560m (24 blocks total)
├── server-1: blocks 0-11 (NUM_BLOCKS=12)
└── server-2: blocks 12-23 (NUM_BLOCKS=12)

P2P Discovery (automatic via Petals DHT)
Metrics → Oracle API (server-1:15481)
Chain RPC → localhost:26902 (each server)
```
