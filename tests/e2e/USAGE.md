# E2E Test Usage Guide

## Quick Start

### 1. Basic Test Execution

가장 간단한 방법으로 모든 E2E 테스트 실행:

```bash
cd /Users/jskim/Desktop/vibe/plumise-petals
pytest tests/e2e/ -v
```

### 2. 특정 테스트만 실행

#### 단일 노드 추론 테스트
```bash
pytest tests/e2e/test_single_node_inference.py -v
```

#### 멀티노드 파이프라인 테스트
```bash
pytest tests/e2e/test_multi_node_pipeline.py -v
```

#### 체인 등록 테스트
```bash
pytest tests/e2e/test_chain_registration.py -v
```

#### 메트릭 리포팅 테스트
```bash
pytest tests/e2e/test_metrics_reporting.py -v
```

### 3. 상세 로그와 함께 실행

```bash
pytest tests/e2e/ -v --log-cli-level=INFO
```

### 4. 특정 테스트 케이스만 실행

```bash
# 메트릭 수집 테스트만
pytest tests/e2e/test_single_node_inference.py::TestSingleNodeInference::test_metrics_collector_initialization -v

# 시그니처 검증 테스트만
pytest tests/e2e/test_metrics_reporting.py::TestMetricsReporting::test_signature_is_valid -v
```

## Docker 기반 통합 테스트

### 1. 전체 E2E 스위트 실행

```bash
cd /Users/jskim/Desktop/vibe/plumise-petals/tests/e2e
./run_e2e.sh
```

이 스크립트는 다음을 자동으로 수행합니다:
1. ✓ 유닛 테스트 실행
2. ✓ 모킹된 E2E 테스트 실행
3. ✓ Docker 이미지 빌드
4. ✓ Mock Oracle + 2개 Petals 노드 시작
5. ✓ 서비스 준비 대기
6. ✓ 통합 검증
7. ✓ 로그 수집
8. ✓ 정리

### 2. 수동 Docker 실행

서비스만 시작하고 수동으로 테스트:

```bash
cd /Users/jskim/Desktop/vibe/plumise-petals/tests/e2e

# 서비스 시작
docker-compose -f docker-compose.test.yml up -d

# 로그 확인
docker-compose -f docker-compose.test.yml logs -f

# 정리
docker-compose -f docker-compose.test.yml down -v
```

### 3. 특정 서비스만 시작

```bash
# Mock Oracle만
docker-compose -f docker-compose.test.yml up -d mock-oracle

# Node A만
docker-compose -f docker-compose.test.yml up -d petals-node-a

# 로그 확인
docker-compose -f docker-compose.test.yml logs petals-node-a
```

## 개발 워크플로우

### 새 테스트 추가

1. `tests/e2e/test_*.py` 파일 생성
2. 기존 패턴 참고하여 테스트 작성:

```python
"""E2E test for new feature."""

import pytest
from plumise_petals.server.metrics import MetricsCollector

@pytest.fixture
def collector() -> MetricsCollector:
    return MetricsCollector()

class TestNewFeature:
    """Test new feature."""

    def test_feature_works(self, collector: MetricsCollector) -> None:
        """Feature should work correctly."""
        # Arrange
        collector.record_inference(tokens=10, latency_ms=50.0)

        # Act
        snapshot = collector.get_snapshot()

        # Assert
        assert snapshot.total_tokens_processed == 10
```

3. 테스트 실행:

```bash
pytest tests/e2e/test_new_feature.py -v
```

### 디버깅

#### 1. pytest 디버거 사용

```bash
pytest tests/e2e/test_single_node_inference.py --pdb
```

#### 2. 특정 테스트만 재실행 (실패한 것만)

```bash
pytest tests/e2e/ --lf -v
```

#### 3. 상세 출력

```bash
pytest tests/e2e/ -vv -s --log-cli-level=DEBUG
```

#### 4. Docker 서비스 로그 확인

```bash
# 실시간 로그
docker-compose -f docker-compose.test.yml logs -f

# 특정 서비스만
docker-compose -f docker-compose.test.yml logs -f petals-node-a

# 최근 100줄
docker-compose -f docker-compose.test.yml logs --tail=100
```

## 성능 측정

### 테스트 실행 시간 측정

```bash
pytest tests/e2e/ -v --durations=10
```

출력 예:
```
========== slowest 10 durations ==========
2.50s call     tests/e2e/test_multi_node_pipeline.py::TestMultiNodePipeline::test_concurrent_inference_requests
1.20s call     tests/e2e/test_single_node_inference.py::TestSingleNodeInference::test_oracle_reporter_with_inference_activity
0.80s call     tests/e2e/test_chain_registration.py::TestChainRegistration::test_register_success
...
```

### 커버리지 측정

```bash
pytest tests/e2e/ --cov=plumise_petals --cov-report=html
open htmlcov/index.html
```

## CI/CD 통합

### GitHub Actions

`.github/workflows/e2e-tests.yml`:

```yaml
name: E2E Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test:
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
          pip install pytest pytest-asyncio pytest-cov

      - name: Run E2E tests
        run: pytest tests/e2e/ -v --cov=plumise_petals

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

### GitLab CI

`.gitlab-ci.yml`:

```yaml
e2e-tests:
  stage: test
  image: python:3.11

  services:
    - docker:dind

  script:
    - pip install -e .
    - pip install pytest pytest-asyncio
    - pytest tests/e2e/ -v

  only:
    - main
    - develop
    - merge_requests
```

## 트러블슈팅

### 문제: pytest 모듈을 찾을 수 없음

```bash
# 해결방법
pip install pytest pytest-asyncio
```

### 문제: Docker 서비스가 시작되지 않음

```bash
# Docker 상태 확인
docker info

# 컨테이너 강제 정리
docker-compose -f docker-compose.test.yml down -v
docker system prune -f
```

### 문제: Mock Oracle이 응답하지 않음

```bash
# 로그 확인
docker-compose -f docker-compose.test.yml logs mock-oracle

# 헬스체크
curl http://localhost:3100/health

# 재시작
docker-compose -f docker-compose.test.yml restart mock-oracle
```

### 문제: Petals 노드가 메모리 부족

```bash
# docker-compose.test.yml에서 메모리 제한 증가
deploy:
  resources:
    limits:
      memory: 8G  # 4G에서 8G로 증가
```

### 문제: 테스트가 너무 느림

```bash
# 빠른 모델 사용
MODEL_NAME=bigscience/bloom-560m  # 기본값

# 더 작은 모델
MODEL_NAME=gpt2  # 더 빠름

# 블록 수 감소
NUM_BLOCKS=6  # 기본 12에서 감소
```

## 베스트 프랙티스

### 1. 테스트 격리

각 테스트는 독립적이어야 합니다:

```python
@pytest.fixture
def metrics_collector() -> MetricsCollector:
    """각 테스트마다 새로운 인스턴스."""
    return MetricsCollector()
```

### 2. Mock 사용

외부 의존성은 항상 mock:

```python
with patch("plumise_petals.chain.reporter.aiohttp.ClientSession"):
    result = await reporter._send_report(snapshot)
```

### 3. 타임아웃 설정

긴 테스트는 타임아웃 설정:

```python
@pytest.mark.timeout(30)
async def test_long_operation():
    # ...
```

### 4. 명확한 테스트 이름

```python
# Good
def test_metrics_collector_records_inference_correctly():
    pass

# Bad
def test_metrics():
    pass
```

### 5. AAA 패턴 사용

```python
def test_example():
    # Arrange
    collector = MetricsCollector()

    # Act
    collector.record_inference(tokens=10, latency_ms=50.0)

    # Assert
    assert collector.get_snapshot().total_tokens_processed == 10
```

## 참고 자료

- [pytest 공식 문서](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Docker Compose](https://docs.docker.com/compose/)
- [Petals 문서](https://github.com/bigscience-workshop/petals)
