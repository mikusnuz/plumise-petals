# Plumise Petals

**[English](README.md) | [Korean](README.ko.md)**

Distributed LLM inference on Plumise chain -- a [Petals](https://github.com/bigscience-workshop/petals) fork with blockchain integration.

Nodes serve transformer model shards and together form a distributed inference network. Each node authenticates via the Plumise chain, reports inference metrics to the Oracle, and earns PLM rewards proportional to its contribution.

## Architecture

```
+------------------+       +------------------+       +------------------+
|   Petals Node A  |       |   Petals Node B  |       |   Petals Node C  |
|  (blocks 0-3)    | <---> |  (blocks 4-7)    | <---> |  (blocks 8-11)   |
+--------+---------+       +--------+---------+       +--------+---------+
         |                          |                          |
         |   signed metrics         |   signed metrics         |   signed metrics
         v                          v                          v
+--------+----------+------+--------+----------+------+--------+----------+
|                    Plumise Oracle API                                    |
+--------+------------------------------------------------------------+---+
         |                                                            |
         v                                                            v
+--------+---------+                                   +--------------+---+
|  AgentRegistry   |                                   |   RewardPool     |
|  (Plumise Chain) |                                   |  (Plumise Chain) |
+------------------+                                   +------------------+
```

## Features

- **Chain Authentication** -- Agents sign messages with their Ethereum private key to prove identity and verify registration in the on-chain AgentRegistry.
- **Metrics Collection** -- Thread-safe inference metrics (tokens processed, latency, uptime) collected from Petals server pipelines.
- **Oracle Reporting** -- Signed metrics reports sent periodically to the Plumise Oracle API.
- **Reward Tracking** -- Monitor pending rewards from the RewardPool contract and auto-claim when threshold is met.
- **CLI Interface** -- Simple command-line interface for starting the server and checking status.

## Minimum Requirements

- **RAM**: 2GB+ available (as low as ~300MB with lightweight models)
- **Disk**: 1GB free space
- **Python**: 3.10+
- **Network**: Plumise chain RPC endpoint
- **Wallet**: Ethereum-compatible private key registered in AgentRegistry

> **No GPU required!** Petals supports CPU inference. Apple Silicon Macs and even low-end PCs can participate and earn PLM rewards.

### Model Tiers

| Tier | Model | RAM per 2 blocks | Total Model Size | Best For |
|------|-------|-------------------|------------------|----------|
| **Lite** | `bigscience/bloom-560m` | ~300MB | ~1.1GB | Low-end PCs, background running |
| **Standard** | `bigscience/bloom-7b1` | ~1.5GB | ~14GB | 16GB RAM PCs |
| **Pro** | `meta-llama/Llama-3.1-8B` | ~2GB | ~16GB (FP16) | 32GB+ RAM / Apple Silicon |
| **Ultra** | `meta-llama/Llama-3.1-70B` | ~10GB | ~140GB | GPU servers |

The default model is **bloom-560m** (Lite tier) -- anyone can start earning PLM with minimal hardware.

## Installation

```bash
# Clone the repository
git clone https://github.com/mikusnuz/plumise-petals.git
cd plumise-petals

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

## Configuration

Copy the example environment file and edit it:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `PLUMISE_RPC_URL` | `http://localhost:26902` | Plumise chain RPC endpoint |
| `PLUMISE_CHAIN_ID` | `41956` | Plumise chain ID |
| `PLUMISE_PRIVATE_KEY` | -- | Agent wallet private key (hex) |
| `ORACLE_API_URL` | `http://localhost:3100` | Oracle API base URL |
| `REPORT_INTERVAL` | `60` | Metrics report interval (seconds) |
| `MODEL_NAME` | `bigscience/bloom-560m` | HuggingFace model to serve (see Model Tiers) |
| `NUM_BLOCKS` | `2` | Transformer blocks to serve (more = more rewards) |
| `PETALS_HOST` | `0.0.0.0` | Server listen address |
| `PETALS_PORT` | `31330` | Server listen port |

## Usage

### Quick Start with Docker

```bash
# Copy environment file
cp .env.example .env

# Edit configuration (set your private key)
nano .env

# Build and start
docker compose up -d

# Check logs
docker compose logs -f

# Check status
curl http://localhost:31330/health
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed Docker deployment guide.

### Manual Installation

```bash
# Using environment variables / .env
plumise-petals serve

# With explicit options
plumise-petals serve \
    --model bigscience/bloom-560m \
    --private-key 0xYOUR_PRIVATE_KEY \
    --rpc-url http://localhost:26902 \
    --oracle-url http://localhost:3100 \
    --num-blocks 2

# Serve a heavier model with more blocks (higher rewards)
plumise-petals serve \
    --model meta-llama/Llama-3.1-8B \
    --num-blocks 4

# Verbose logging
plumise-petals serve -v
```

### Check Status

```bash
plumise-petals status
```

Output:
```
Agent:   0x1234...5678
Chain:   http://localhost:26902 (ID 41956)
Online:  True
Balance: 42.5000 PLM
Registered: True
Active:     True
Pending Reward: 1.2500 PLM
Current Epoch:  15
Tasks Completed: 1024
Uptime:          86400s
```

## Project Structure

```
plumise-petals/
├── src/plumise_petals/
│   ├── chain/            # Plumise chain integration
│   │   ├── auth.py       # Agent authentication
│   │   ├── config.py     # Configuration management
│   │   ├── reporter.py   # Oracle metrics reporter
│   │   └── rewards.py    # Reward tracking & claiming
│   ├── server/           # Petals server integration
│   │   ├── metrics.py    # Inference metrics collection
│   │   └── plumise_server.py  # Enhanced server
│   └── cli/              # Command-line interface
│       └── run_server.py
├── contracts/            # Contract ABIs
│   ├── AgentRegistry.json
│   └── RewardPool.json
└── tests/                # Test suite
```

## Running Tests

```bash
pytest tests/ -v
```

## Smart Contracts

The system interacts with two on-chain contracts:

### AgentRegistry
- `isRegistered(address)` -- Check if an agent is registered
- `isActive(address)` -- Check if an agent is active
- `getAgent(address)` -- Get full agent record
- `register(name, metadata)` -- Register a new agent

### RewardPool
- `getPendingReward(address)` -- Query unclaimed rewards
- `claimReward()` -- Claim accumulated rewards
- `getContribution(address)` -- Get contribution metrics
- `getCurrentEpoch()` -- Get current reward epoch

## License

MIT
