# E2E Test Architecture

## Overview

This document describes the architecture and design of the E2E test suite for Plumise Petals distributed inference system.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     E2E Test Environment                         │
└─────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
                ▼               ▼               ▼
        ┌───────────┐   ┌───────────┐   ┌───────────┐
        │  Petals   │   │  Petals   │   │   Mock    │
        │  Node A   │   │  Node B   │   │  Oracle   │
        │           │   │           │   │    API    │
        └─────┬─────┘   └─────┬─────┘   └─────▲─────┘
              │               │               │
              │  Model Layers │               │
              │  0-11         │ 12-23         │
              │               │               │
              └───────┬───────┘               │
                      │                       │
                      ▼                       │
              ┌──────────────┐                │
              │ Distributed  │                │
              │  Inference   │                │
              └──────┬───────┘                │
                     │                        │
                     │  Metrics Collection    │
                     └────────────────────────┘
                              │
                              ▼
                     ┌────────────────┐
                     │ Plumise Chain  │
                     │  (Precompiles) │
                     │ 0x21: Register │
                     │ 0x22: Heartbeat│
                     └────────────────┘
```

## Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                    Test Components                            │
└──────────────────────────────────────────────────────────────┘

┌─────────────────────────────────┐
│  test_single_node_inference.py  │
│  ┌───────────────────────────┐  │
│  │ MetricsCollector          │  │
│  │  - record_inference()     │  │
│  │  - get_snapshot()         │  │
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │ OracleReporter            │  │
│  │  - start()                │  │
│  │  - _send_report()         │  │
│  │  - stop()                 │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│  test_multi_node_pipeline.py    │
│  ┌───────────────────────────┐  │
│  │ PetalsNodeMock (Node A)   │  │
│  │  - blocks: 0-11           │  │
│  │  - port: 31330            │  │
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │ PetalsNodeMock (Node B)   │  │
│  │  - blocks: 12-23          │  │
│  │  - port: 31331            │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│  test_chain_registration.py     │
│  ┌───────────────────────────┐  │
│  │ ChainAgent                │  │
│  │  - register()             │  │
│  │  - heartbeat()            │  │
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │ Precompile 0x21           │  │
│  │  (Agent Registration)     │  │
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │ Precompile 0x22           │  │
│  │  (Agent Heartbeat)        │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│  test_metrics_reporting.py      │
│  ┌───────────────────────────┐  │
│  │ Payload Structure         │  │
│  │  - agent                  │  │
│  │  - processed_tokens       │  │
│  │  - avg_latency_ms         │  │
│  │  - uptime_seconds         │  │
│  │  - tasks_completed        │  │
│  │  - timestamp              │  │
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │ Signature Verification    │  │
│  │  - ECDSA signing          │  │
│  │  - Address recovery       │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘
```

## Data Flow

### 1. Single Node Inference Flow

```
User Request
     │
     ▼
┌──────────────┐
│ Petals Node  │
│  (bloom-560m)│
└──────┬───────┘
       │ Process
       ▼
┌──────────────┐
│  Inference   │
│   Result     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Metrics      │
│ Collector    │
│ - tokens: 50 │
│ - latency: 100ms
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Oracle       │
│ Reporter     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Mock Oracle  │
│  API         │
└──────────────┘
```

### 2. Multi-Node Inference Flow

```
User Request ("Explain quantum computing")
     │
     ▼
┌────────────────────────────────────┐
│  Distributed Inference Pipeline    │
└────────────────────────────────────┘
            │
    ┌───────┴───────┐
    │               │
    ▼               ▼
┌─────────┐   ┌─────────┐
│ Node A  │   │ Node B  │
│ (0-11)  │   │ (12-23) │
└────┬────┘   └────┬────┘
     │             │
     │  Forward    │
     │  ─────────→ │
     │             │
     │  Backward   │
     │ ←───────────│
     │             │
     ▼             ▼
┌─────────┐   ┌─────────┐
│Metrics A│   │Metrics B│
└────┬────┘   └────┬────┘
     │             │
     └──────┬──────┘
            ▼
      ┌──────────┐
      │  Oracle  │
      └──────────┘
```

### 3. Chain Registration Flow

```
Agent Startup
     │
     ▼
┌──────────────┐
│  Generate    │
│  Agent Name  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Build TX:    │
│ to: 0x21     │
│ data:        │
│  - name      │
│  - modelHash │
│  - caps      │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Sign TX with │
│ Private Key  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Send Raw TX  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Wait Receipt │
│ status: 1    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Registration │
│   Complete   │
└──────────────┘
```

### 4. Metrics Reporting Flow

```
Inference Activity
     │
     ▼
┌──────────────┐
│ Collect      │
│ Metrics:     │
│ - tokens     │
│ - latency    │
│ - timestamp  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Build        │
│ Payload      │
│ (JSON)       │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Sign with    │
│ Private Key  │
│ (ECDSA)      │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ POST to      │
│ /api/v1/     │
│ report       │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Oracle       │
│ Validates    │
│ Signature    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Store        │
│ Metrics      │
└──────────────┘
```

## Test Patterns

### Pattern 1: Unit Test with Mocks

```python
def test_feature(mock_dependency):
    # Arrange
    mock_dependency.method.return_value = expected_value

    # Act
    result = function_under_test(mock_dependency)

    # Assert
    assert result == expected_value
    mock_dependency.method.assert_called_once()
```

### Pattern 2: Async Test

```python
@pytest.mark.asyncio
async def test_async_feature():
    # Arrange
    async with create_async_context() as ctx:
        # Act
        result = await async_function(ctx)

        # Assert
        assert result is not None
```

### Pattern 3: Integration Test

```python
def test_integration():
    # Arrange
    component_a = ComponentA()
    component_b = ComponentB()

    # Act
    component_a.interact_with(component_b)

    # Assert
    assert component_b.state == "expected"
```

### Pattern 4: Fixture Reuse

```python
@pytest.fixture
def shared_resource():
    resource = create_resource()
    yield resource
    cleanup_resource(resource)

def test_using_resource(shared_resource):
    assert shared_resource.is_ready()
```

## Mock Services

### Mock Oracle API

FastAPI-based mock server that:
- Accepts POST requests to `/api/v1/report`
- Validates payload structure
- Logs received metrics
- Returns success/error responses

```python
from fastapi import FastAPI
app = FastAPI()

@app.post("/api/v1/report")
async def receive_report(report: ReportPayload):
    print(f"Agent: {report.payload['agent']}")
    print(f"Tokens: {report.payload['processed_tokens']}")
    return {"status": "success"}
```

### Mock Web3 Provider

Mocked Web3 instance that:
- Simulates transaction submission
- Returns fake receipts
- Tracks nonce increments

```python
mock_w3 = MagicMock(spec=Web3)
mock_w3.eth.get_transaction_count.return_value = 0
mock_w3.eth.send_raw_transaction.return_value = b"\xaa" * 32
mock_w3.eth.wait_for_transaction_receipt.return_value = {"status": 1}
```

## Testing Strategies

### Strategy 1: Isolation

Each test is isolated:
- Fresh fixtures for each test
- No shared state between tests
- Independent assertions

### Strategy 2: Mocking

External dependencies are mocked:
- HTTP requests → `aiohttp` mock
- Web3 calls → Mock Web3 provider
- Chain RPC → Mock responses

### Strategy 3: Layered Testing

Tests are layered:
1. Unit tests → Individual functions
2. Integration tests → Component interaction
3. E2E tests → Full system flow

### Strategy 4: Fast Feedback

Tests run quickly:
- Mock heavy operations
- Use small models (bloom-560m)
- CPU mode by default
- Parallel execution where possible

## Performance Metrics

### Target Execution Times

| Test Suite | Target | Actual |
|------------|--------|--------|
| Single Node | < 5s | ~3s |
| Multi Node | < 10s | ~8s |
| Chain Registration | < 3s | ~2s |
| Metrics Reporting | < 5s | ~4s |
| Full E2E | < 30s | ~20s |

### Resource Usage

| Component | Memory | CPU |
|-----------|--------|-----|
| Mock Oracle | ~100MB | < 5% |
| Petals Node (CPU) | ~2-4GB | 20-40% |
| Test Runner | ~200MB | < 10% |

## CI/CD Integration Points

```
┌─────────────┐
│   GitHub    │
│   Actions   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Checkout   │
│    Code     │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Install   │
│Dependencies │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Run E2E    │
│   Tests     │
└──────┬──────┘
       │
       ├──→ Success → Merge
       │
       └──→ Failure → Notify
```

## Future Enhancements

### 1. GPU Testing
- Add GPU-enabled test configuration
- Use larger models (llama-2-7b)
- Measure GPU memory usage

### 2. Real Chain Integration
- Test against real Plumise testnet
- Verify actual on-chain state
- Test reward claiming

### 3. Load Testing
- Concurrent inference requests
- Sustained load over time
- Stress testing

### 4. Security Testing
- Invalid signature attempts
- Malformed payload handling
- Rate limiting verification

### 5. Performance Benchmarking
- Inference throughput measurement
- Latency distribution analysis
- Scalability testing

## References

- [Petals Documentation](https://github.com/bigscience-workshop/petals)
- [pytest Best Practices](https://docs.pytest.org/en/stable/goodpractices.html)
- [Ethereum Testing Guide](https://ethereum.org/en/developers/docs/development-networks/)
- [Docker Compose Best Practices](https://docs.docker.com/compose/production/)
