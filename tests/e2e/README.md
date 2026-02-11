# Plumise Petals E2E Tests

End-to-end tests for verifying the complete distributed inference pipeline with multiple Petals nodes, Oracle reporting, and chain integration.

## Overview

These tests verify the full integration flow:
1. Multiple Petals nodes serving different model layers
2. Distributed inference across nodes
3. Metrics collection on each node
4. Oracle API reporting with signed payloads
5. On-chain registration via precompiles

## Test Structure

### Test Files

- **`test_single_node_inference.py`**: Single-node inference with metrics collection
  - MetricsCollector initialization and recording
  - Oracle reporter payload format
  - Thread-safe metrics tracking

- **`test_multi_node_pipeline.py`**: Multi-node distributed inference
  - Node initialization with layer distribution
  - Distributed inference spanning multiple nodes
  - Concurrent request handling
  - Independent Oracle reporting from each node

- **`test_chain_registration.py`**: On-chain agent lifecycle
  - Agent registration via precompile 0x21
  - Heartbeat via precompile 0x22
  - Transaction construction and signing
  - Error handling

- **`test_metrics_reporting.py`**: Oracle metrics reporting
  - Payload format and structure
  - Signature verification and recovery
  - HTTP error handling
  - Network failure resilience

### Docker Setup

- **`docker-compose.test.yml`**: Docker Compose configuration
  - Mock Oracle API server (FastAPI)
  - Petals Node A (blocks 0-11)
  - Petals Node B (blocks 12-23)

- **`run_e2e.sh`**: Automated test runner
  - Runs unit tests first
  - Runs E2E tests (mocked)
  - Builds Docker images
  - Starts services
  - Verifies integration
  - Collects logs
  - Cleanup

## Running Tests

### Quick Start (Mocked Tests)

Run E2E tests without Docker:

```bash
cd /Users/jskim/Desktop/vibe/plumise-petals
pytest tests/e2e/ -v
```

### Full E2E Suite (with Docker)

Run complete E2E tests including Docker services:

```bash
cd /Users/jskim/Desktop/vibe/plumise-petals/tests/e2e
./run_e2e.sh
```

The script will:
1. ✓ Run unit tests
2. ✓ Run mocked E2E tests
3. ✓ Build Docker image
4. ✓ Start mock Oracle and Petals nodes
5. ✓ Wait for services to be ready
6. ✓ Verify integration
7. ✓ Show logs
8. ✓ Cleanup

### Individual Test Suites

Run specific test files:

```bash
# Single node inference tests
pytest tests/e2e/test_single_node_inference.py -v

# Multi-node pipeline tests
pytest tests/e2e/test_multi_node_pipeline.py -v

# Chain registration tests
pytest tests/e2e/test_chain_registration.py -v

# Metrics reporting tests
pytest tests/e2e/test_metrics_reporting.py -v
```

### Run with Logging

Enable detailed logging:

```bash
pytest tests/e2e/ -v --log-cli-level=INFO
```

## Test Configuration

### Model Selection

Tests use `bigscience/bloom-560m` by default:
- Small enough to run on CPU
- Fast model download (~1GB)
- Suitable for testing distributed inference
- 24 transformer blocks (12 per node in multi-node setup)

### Private Keys

Test private keys (DO NOT use in production):
- Node A: `0xaaaa...aaaa` (32 bytes)
- Node B: `0xbbbb...bbbb` (32 bytes)
- Single node: `0xabab...abab` (32 bytes)

### Oracle URL

Mock Oracle runs at `http://localhost:3100` with endpoints:
- `POST /api/v1/report` - Receive metrics reports
- `GET /health` - Health check

## Expected Test Results

### Unit Test Coverage

All tests should pass with 100% success rate:
- ✓ Metrics collection
- ✓ Thread safety
- ✓ Payload format
- ✓ Signature verification
- ✓ Error handling

### Docker Integration

When running with Docker:
- Mock Oracle starts in ~5 seconds
- Petals nodes initialize in ~30 seconds
- At least 1 report per node within 60 seconds
- All services stop cleanly

## Requirements

### Python Dependencies

```
pytest>=7.0.0
pytest-asyncio>=0.21.0
aiohttp>=3.8.0
web3>=6.0.0
eth-account>=0.8.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
```

### Optional (for Docker tests)

```
docker>=20.10
docker-compose>=2.0
```

## Troubleshooting

### Tests Fail with Import Errors

Install dependencies:

```bash
pip install -e .
pip install pytest pytest-asyncio
```

### Docker Build Fails

Check Dockerfile exists:

```bash
ls -la /Users/jskim/Desktop/vibe/plumise-petals/Dockerfile
```

### Services Don't Start

Check Docker is running:

```bash
docker info
```

Increase timeout in `run_e2e.sh` if needed:

```bash
# Edit MAX_WAIT value
MAX_WAIT=60  # Increase from 30 to 60 seconds
```

### Mock Oracle Not Receiving Reports

Check network connectivity:

```bash
docker-compose -f tests/e2e/docker-compose.test.yml logs mock-oracle
docker-compose -f tests/e2e/docker-compose.test.yml logs petals-node-a
```

Increase report interval:

```yaml
# In docker-compose.test.yml
environment:
  - REPORT_INTERVAL=10  # Decrease from 30 to 10 seconds
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e .
          pip install pytest pytest-asyncio

      - name: Run E2E tests
        run: pytest tests/e2e/ -v

      - name: Run Docker E2E tests
        run: |
          cd tests/e2e
          ./run_e2e.sh
```

## Performance Notes

### CPU Mode

Tests run in CPU mode by default:
- bloom-560m: ~5-10 tokens/sec per node
- Sufficient for testing integration
- No GPU required

### GPU Mode

For production testing with GPU:
1. Ensure CUDA is available
2. Use larger models (bloom-7b1, llama-2-7b)
3. Adjust memory limits in docker-compose

### Memory Requirements

- Mock Oracle: ~100MB
- Each Petals node: ~2-4GB (CPU mode)
- Total for full E2E: ~6-8GB RAM

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                     E2E Test Suite                       │
└─────────────────────────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Petals      │    │  Petals      │    │  Mock        │
│  Node A      │    │  Node B      │    │  Oracle      │
│  (blocks     │    │  (blocks     │    │  (FastAPI)   │
│   0-11)      │    │   12-23)     │    │              │
└──────┬───────┘    └──────┬───────┘    └──────▲───────┘
       │                   │                    │
       │ Inference Request │                    │
       └───────────┬───────┘                    │
                   │                            │
                   ▼                            │
           ┌──────────────┐             Metrics Report
           │ Distributed  │                    │
           │ Inference    │                    │
           └──────┬───────┘                    │
                  │                            │
                  └────────────────────────────┘
```

## License

This test suite is part of Plumise Petals and follows the same license.

## Contact

For issues or questions:
- GitHub: https://github.com/mikusnuz/plumise-petals
- Issues: https://github.com/mikusnuz/plumise-petals/issues
