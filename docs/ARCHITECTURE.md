# Plumise AI Inference Architecture

This document describes the full architecture of the Plumise distributed AI inference ecosystem.

## Overview

Plumise is a blockchain network where users contribute GPU/CPU compute to serve distributed LLM inference and earn PLM token rewards. The ecosystem consists of four main components:

| Component | Operator | Repository | Description |
|-----------|----------|------------|-------------|
| **plumise-petals** | Users/Miners | [GitHub](https://github.com/mikusnuz/plumise-petals) | All-in-one node package for AI inference |
| **plumise-inference-api** | Plumise Team | [GitHub](https://github.com/mikusnuz/plumise-inference-api) | API Gateway for end-user requests |
| **plumise-oracle** | Plumise Team | [GitHub](https://github.com/mikusnuz/plumise-oracle) | Metrics aggregation and reward distribution |
| **plumise** (chain) | Plumise Team | [GitHub](https://github.com/mikusnuz/plumise) | Blockchain node (geth fork) |

## System Architecture

```
                            USER / DEVELOPER
                                  |
                           wallet signature
                                  |
                                  v
                    +----------------------------+
                    |    plumise-inference-api    |
                    |      (API Gateway)         |
                    |                            |
                    |  - Wallet auth (JWT)       |
                    |  - Rate limiting           |
                    |  - Request routing         |
                    |  - Metrics aggregation     |
                    +---+----+----+---+----------+
                        |    |    |   |
            +-----------+    |    |   +----------+
            |                |    |              |
            v                v    v              v
   +--------+---+  +--------+--+ +---------+  +-+----------+
   | Petals     |  | Petals    | | Petals  |  | Petals     |
   | Node A     |  | Node B   | | Node C  |  | Node D     |
   | (miner 1)  |  | (miner 2)| | (miner 3)| | (miner 4)  |
   +-----+------+  +-----+----+ +----+-----+ +-----+------+
         |               |            |             |
         |  signed       |  signed    |  signed     |  signed
         |  metrics      |  metrics   |  metrics    |  metrics
         v               v            v             v
   +-----+---------------+------------+-------------+------+
   |                   plumise-oracle                       |
   |                                                        |
   |  - Multi-node metrics collection                       |
   |  - Contribution scoring (V2 formula)                   |
   |  - Active node list API (for Gateway)                  |
   |  - On-chain reward claims (precompile)                 |
   +---+-------------------------------------------+--------+
       |                                           |
       |  reportContribution()                     |  active node list
       |  (precompile 0x23)                        |  (HTTP API)
       v                                           v
   +---+-------------------------------------------+--------+
   |               Plumise Chain (geth fork)                 |
   |                                                         |
   |  +-------------+  +---------------+  +--------------+   |
   |  | Precompile  |  | Precompile    |  | Precompile   |   |
   |  | 0x20: Query |  | 0x21: Register|  | 0x22: Heart- |   |
   |  |   Agent     |  |   Agent       |  |   beat       |   |
   |  +-------------+  +---------------+  +--------------+   |
   |  +-------------+  +---------------+                      |
   |  | Precompile  |  | RewardPool    |                      |
   |  | 0x23: Report|  | (0x1000)      |                      |
   |  | Contribution|  | Block rewards |                      |
   |  +-------------+  +---+-----------+                      |
   |                        |                                  |
   |                   10 PLM/block                            |
   |                   halving every 42M blocks (~4 years)     |
   +---------------------------------------------------------+
```

## Component Details

### 1. plumise-petals (User-Installed Node)

The all-in-one package that miners/users install on their machines.

**Responsibilities:**
- Run Petals distributed LLM inference engine
- Serve transformer model shards (configurable number of blocks)
- Register agent on-chain via precompile 0x21 (automatic on first start)
- Send heartbeat pings via precompile 0x22 (every 5 minutes)
- Collect inference metrics (tokens processed, latency, uptime)
- Sign and report metrics to Oracle API (every 60 seconds)
- Track and auto-claim PLM rewards from RewardPool

**Tech Stack:** Python 3.10+, Petals (fork), web3.py, Docker

**Key Files:**
```
src/plumise_petals/
├── chain/
│   ├── auth.py        # Wallet authentication + on-chain registration
│   ├── config.py      # Configuration from .env
│   ├── reporter.py    # Signed metrics reporter (-> Oracle API)
│   └── rewards.py     # Reward tracking + auto-claim
├── server/
│   ├── metrics.py     # Thread-safe inference metrics collector
│   └── plumise_server.py  # Petals server with chain integration
└── cli/
    └── run_server.py  # CLI entry point
```

---

### 2. plumise-inference-api (API Gateway)

Team-operated service that provides an OpenAI-compatible API to end users.

**Responsibilities:**
- Authenticate user requests via wallet signature (EIP-712 -> JWT)
- Enforce tier-based rate limits (Free: 10/hr, Pro: unlimited)
- Discover active Petals nodes from Oracle API
- Route inference requests to healthy nodes (round-robin + failover)
- Aggregate and report request metrics to Oracle
- Provide OpenAI-compatible REST and WebSocket streaming API

**Tech Stack:** NestJS, TypeScript, ethers.js v6, Socket.IO, Passport/JWT

**Key Services:**
- `NodeRouterService` -- Node discovery, health checks, load balancing
- `InferenceService` -- Request orchestration, response formatting
- `MetricsReporterService` -- Aggregated metrics reporting to Oracle
- `AuthService` -- Wallet nonce challenge + JWT issuance

---

### 3. plumise-oracle (Metrics Oracle)

Team-operated service that collects metrics, scores contributions, and reports rewards on-chain.

**Responsibilities:**
- Receive signed metrics from multiple Petals nodes
- Verify metric signatures (ensure metrics come from registered agents)
- Calculate contribution scores using the V2 formula
- Report contributions on-chain via precompile 0x23
- Trigger epoch reward distribution
- Serve active node list API (consumed by Inference API Gateway)
- Monitor agent registrations and heartbeats

**Tech Stack:** NestJS, TypeScript, ethers.js v6, TypeORM, MySQL

**Scoring Formula (V2):**
```
score = (tokenScore x 40) + (taskCount x 25) + (uptimeSeconds x 20) + (latencyScore x 15)

where:
  tokenScore = processedTokens / 1000
  latencyScore = max(0, 10000 - avgLatencyMs)
```

---

### 4. plumise (Chain Node)

Plumise blockchain -- a geth v1.13.15 fork with AI-specific precompiled contracts.

**Chain Parameters:**
- Chain ID: 41956
- Block reward: 10 PLM/block
- Halving: every 42,048,000 blocks (~4 years)
- Consensus: Clique PoA (4 signers, 3 required)

**Precompiled Contracts:**
| Address | Name | Function |
|---------|------|----------|
| `0x20` | QueryAgent | Read agent data from state trie |
| `0x21` | RegisterAgent | Register new agent with metadata |
| `0x22` | Heartbeat | Update agent last-active timestamp |
| `0x23` | ReportContribution | Oracle reports contribution scores |

**Genesis Contracts:**
| Address | Name | Allocation |
|---------|------|------------|
| `0x1000` | RewardPool | Block rewards (10 PLM/block) |
| `0x1001` | FoundationTreasury | 47.7M PLM |
| `0x1002` | EcosystemFund | 55.7M PLM |
| `0x1003` | TeamVesting | 23.9M PLM |
| `0x1004` | LiquidityDeployer | 31.8M PLM |

---

## Data Flows

### Flow 1: Inference Request (User -> Response)

```
1. User signs message with wallet
2. Inference API verifies signature, issues JWT
3. User sends inference request with JWT
4. Inference API checks rate limit
5. NodeRouterService selects a healthy Petals node
6. Request forwarded to Petals node
7. Petals node processes inference (distributed across model shards)
8. Response returned to Inference API
9. Inference API counts tokens, measures latency
10. Formatted OpenAI-compatible response returned to user
```

### Flow 2: Metrics Collection (Node -> Oracle -> Chain)

```
1. Petals node processes inference requests
2. MetricsCollector tracks tokens, latency, uptime (thread-safe)
3. Every 60 seconds, MetricsReporter:
   a. Packages metrics into a report
   b. Signs report with agent's private key
   c. Sends signed report to Oracle API
4. Oracle receives report, verifies signature
5. Oracle aggregates metrics across all nodes
6. At epoch boundary:
   a. Oracle calculates contribution scores (V2 formula)
   b. Oracle calls precompile 0x23 (ReportContribution)
   c. RewardPool distributes PLM proportionally
7. Agents claim rewards from RewardPool
```

### Flow 3: Node Discovery (Gateway -> Oracle -> Nodes)

```
1. Inference API Gateway starts
2. NodeRouterService initializes with:
   a. Static NODE_URLS (if configured)
   b. Oracle API discovery endpoint
3. Every 30 seconds:
   a. Query Oracle GET /api/v1/nodes/active
   b. Add newly discovered nodes
   c. Health-check all known nodes
   d. Mark failed nodes as offline (after 3 consecutive failures)
4. On inference request:
   a. Select next online node (round-robin)
   b. If request fails, retry with next node (up to 3 retries)
```

### Flow 4: Agent Registration (Node -> Chain)

```
1. Petals node starts for the first time
2. auth.py checks if agent is registered (precompile 0x20)
3. If not registered:
   a. Construct registration data: name + model hash + capabilities
   b. Send transaction to precompile 0x21
   c. Agent is registered in chain state trie
4. Start heartbeat loop (every 5 minutes):
   a. Send transaction to precompile 0x22
   b. Updates lastActiveTime in state trie
5. Monitor service marks agents without heartbeat as inactive
```

## Security Model

### Authentication Layers

1. **Agent Authentication (Node -> Oracle)**
   - Each Petals node has a private key
   - Metrics reports are signed with `ethers.signMessage()`
   - Oracle verifies signature matches a registered agent address
   - Only registered and active agents can submit metrics

2. **User Authentication (User -> Gateway)**
   - Challenge-response with nonce
   - User signs nonce with wallet (EIP-712)
   - Gateway verifies signature, issues JWT
   - JWT required for all inference endpoints

3. **Oracle Authentication (Oracle -> Chain)**
   - Oracle has its own private key
   - Must be authorized as oracle in RewardPool contract
   - Only authorized oracle can call precompile 0x23

4. **Inter-Service Authentication (Gateway <-> Oracle)**
   - API key based (x-api-key header)
   - Gateway uses API key when reporting aggregated metrics
   - Oracle uses API key when pushing node lists

### On-Chain Verification

- Agent registration is stored in the chain state trie (precompile 0x20/0x21)
- Heartbeat timestamps are on-chain (precompile 0x22)
- Contribution scores are reported on-chain (precompile 0x23)
- Reward distribution is handled by RewardPool smart contract (0x1000)
- All on-chain operations are permissioned (only authorized callers)

## Deployment Topology

```
Server Infrastructure:
  server-1 (192.168.0.200) -- Main workload
    - Plumise chain signer node (P2P:16902, RPC:26902)
    - Petals nodes (port 31330)
    - MySQL database (port 15411)

  server-2 (192.168.0.202) -- Secondary workload
    - Plumise chain signer node (P2P:16902, RPC:26902)

  server-4 (192.168.0.206) -- Infrastructure
    - Nginx reverse proxy + SSL
    - Plumise chain signer node (P2P:16902, RPC:26902)
    - Monitoring (Beszel, Umami)

External:
  - Public RPC: https://node-1.plumise.com/rpc
  - Public WS: wss://node-1.plumise.com/ws
```

## Tokenomics

- **Block Reward**: 10 PLM/block
- **Halving**: Every 42,048,000 blocks (~4 years)
- **Total Block Rewards**: 840,960,000 PLM (84.1%)
- **Genesis Allocation**: 159,040,000 PLM (15.9%)
  - Foundation: 47.7M PLM
  - Ecosystem: 55.7M PLM
  - Team (vested): 23.9M PLM
  - Liquidity: 31.8M PLM
- **Total Supply**: ~1,000,000,000 PLM
