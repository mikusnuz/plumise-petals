# Plumise Petals

**[English](README.md) | [한국어](README.ko.md)**

AI inference node for the Plumise network. Provide your GPU (or CPU) and mine PLM tokens.

A [Petals](https://github.com/bigscience-workshop/petals) fork with integrated blockchain authentication, metrics reporting, and reward distribution. Nodes serve transformer model shards and together form a distributed inference network -- each node authenticates via the Plumise chain, reports inference metrics to the Oracle, and earns PLM rewards proportional to its contribution.

## Quick Start

```bash
git clone https://github.com/mikusnuz/plumise-petals.git
cd plumise-petals
cp .env.example .env
# Edit .env -- set your PLUMISE_PRIVATE_KEY
docker compose up -d
```

That's it. Your node will start serving model shards and earning PLM.

## How You Earn PLM

```
 You run a node        Metrics reported         Score calculated       Rewards distributed
+--------------+      +---------------+        +----------------+     +------------------+
| Petals Node  | ---> | Oracle        | -----> | Scoring Engine | --> | RewardPool       |
| (inference)  |      | (collects)    |        | (contribution) |     | (on-chain PLM)   |
+--------------+      +---------------+        +----------------+     +------------------+
```

1. **Serve AI inference** -- Your node handles a portion of a large language model
2. **Report metrics** -- Token throughput, latency, and uptime are signed and sent to the Oracle
3. **Get scored** -- The Oracle calculates your contribution relative to other nodes
4. **Receive PLM** -- Rewards from the RewardPool contract are distributed each epoch

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
|                   Plumise Oracle                                        |
+--------+------------------------------------------------------------+---+
         |                                                            |
         v                                                            v
+--------+---------+                                   +--------------+---+
|  AgentRegistry   |                                   |   RewardPool     |
|  (Plumise Chain) |                                   |  (Plumise Chain) |
+------------------+                                   +------------------+
```

For the full ecosystem architecture (including Inference API Gateway and Oracle internals), see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Features

- **Chain Authentication** -- Agents sign messages with their Ethereum private key to prove identity and verify on-chain registration.
- **On-Chain Registration** -- Automatic agent registration via precompiled contract (0x21) on first start.
- **Heartbeat System** -- Periodic heartbeat pings (precompile 0x22) to maintain agent liveness status.
- **Metrics Collection** -- Thread-safe inference metrics (tokens processed, latency, uptime) collected from Petals server pipelines.
- **Oracle Reporting** -- Signed metrics reports sent periodically to the Plumise Oracle API (every 60 seconds).
- **Reward Tracking** -- Monitor pending rewards from the RewardPool contract and auto-claim when threshold is met.
- **CLI Interface** -- Simple command-line interface for starting the server and checking status.

## Requirements

- **RAM**: 2GB+ available (as low as ~300MB with lightweight models)
- **Disk**: 1GB free space
- **Docker** (recommended) or Python 3.10+
- **Network**: Plumise chain RPC endpoint
- **Wallet**: Ethereum-compatible private key

> **No GPU required!** Petals supports CPU inference. Apple Silicon Macs and even low-end PCs can participate and earn PLM rewards.

### Model Tiers

| Tier | Model | RAM per 2 blocks | Total Model Size | Best For |
|------|-------|-------------------|------------------|----------|
| **Lite** | `bigscience/bloom-560m` | ~300MB | ~1.1GB | Low-end PCs, background running |
| **Standard** | `bigscience/bloom-7b1` | ~1.5GB | ~14GB | 16GB RAM PCs |
| **Pro** | `meta-llama/Llama-3.1-8B` | ~2GB | ~16GB (FP16) | 32GB+ RAM / Apple Silicon |
| **Ultra** | `meta-llama/Llama-3.1-70B` | ~10GB | ~140GB | GPU servers |

The default model is **bloom-560m** (Lite tier) -- anyone can start earning PLM with minimal hardware.

## Configuration

Copy the example environment file and edit it:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `PLUMISE_PRIVATE_KEY` | -- | **Required.** Agent wallet private key (hex, with 0x prefix) |
| `ORACLE_API_URL` | `http://localhost:15481` | Oracle API base URL for metrics reporting |
| `PLUMISE_RPC_URL` | `http://localhost:26902` | Plumise chain RPC endpoint |
| `PLUMISE_CHAIN_ID` | `41956` | Plumise chain ID |
| `AGENT_REGISTRY_ADDRESS` | -- | AgentRegistry contract address (optional) |
| `REWARD_POOL_ADDRESS` | -- | RewardPool contract address (optional) |
| `REPORT_INTERVAL` | `60` | Metrics report interval (seconds) |
| `MODEL_NAME` | `bigscience/bloom-560m` | HuggingFace model to serve (see Model Tiers) |
| `NUM_BLOCKS` | `2` | Transformer blocks to serve (more = more rewards) |
| `PETALS_HOST` | `0.0.0.0` | Server listen address |
| `PETALS_PORT` | `31330` | Server listen port |
| `CLAIM_THRESHOLD_WEI` | `1000000000000000000` | Auto-claim threshold (1 PLM) |

## Usage

### Docker (Recommended)

```bash
# Copy and edit environment file
cp .env.example .env
nano .env  # Set PLUMISE_PRIVATE_KEY

# Start the node
docker compose up -d

# Check logs
docker compose logs -f

# Health check
curl http://localhost:31330/health
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed Docker deployment guide.

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/mikusnuz/plumise-petals.git
cd plumise-petals

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Start serving
plumise-petals serve

# Or with explicit options
plumise-petals serve \
    --model bigscience/bloom-560m \
    --private-key 0xYOUR_PRIVATE_KEY \
    --rpc-url http://localhost:26902 \
    --oracle-url http://localhost:15481 \
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
│   │   ├── auth.py       # Agent authentication & registration
│   │   ├── config.py     # Configuration management
│   │   ├── reporter.py   # Oracle metrics reporter
│   │   └── rewards.py    # Reward tracking & claiming
│   ├── server/           # Petals server integration
│   │   ├── metrics.py    # Inference metrics collection
│   │   └── plumise_server.py  # Enhanced server with chain agent
│   └── cli/              # Command-line interface
│       └── run_server.py
├── contracts/            # Contract ABIs
│   ├── AgentRegistry.json
│   └── RewardPool.json
├── docs/                 # Documentation
│   └── ARCHITECTURE.md   # Full ecosystem architecture
└── tests/                # Test suite
```

## Smart Contracts

The system uses **precompiled contracts** for agent lifecycle management:

### Precompile 0x21 (Agent Registration)
- Called automatically on first start
- Input: agent name (32B) + model hash (32B) + capabilities
- Registers agent address with metadata on-chain

### Precompile 0x22 (Heartbeat)
- Called every 5 minutes automatically
- No input required (uses `msg.sender`)
- Updates agent's last active timestamp

### AgentRegistry (optional, post-genesis deployment)
- `isRegistered(address)` -- Check if an agent is registered
- `isActive(address)` -- Check if an agent is active
- `getAgent(address)` -- Get full agent record

### RewardPool (0x1000)
- `getPendingReward(address)` -- Query unclaimed rewards
- `claimReward()` -- Claim accumulated rewards
- `getContribution(address)` -- Get contribution metrics
- `getCurrentEpoch()` -- Get current reward epoch

## Running Tests

```bash
pytest tests/ -v
```

## Related Projects

| Project | Description | Link |
|---------|-------------|------|
| **plumise-inference-api** | API Gateway for end-user inference requests | [GitHub](https://github.com/mikusnuz/plumise-inference-api) |
| **plumise-oracle** | Metrics aggregation, scoring, and on-chain reward reporting | [GitHub](https://github.com/mikusnuz/plumise-oracle) |
| **plumise** | Plumise chain node (geth fork with AI precompiles) | [GitHub](https://github.com/mikusnuz/plumise) |
| **plumise-contracts** | On-chain system contracts (RewardPool, AgentRegistry, etc.) | [GitHub](https://github.com/mikusnuz/plumise-contracts) |

## License

MIT
