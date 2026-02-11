# Plumise Petals

**[English](README.md) | [Korean](README.ko.md)**

Plumise 체인 기반 분산 LLM 추론 -- [Petals](https://github.com/bigscience-workshop/petals) 포크에 블록체인 통합을 추가한 프로젝트입니다.

노드들이 트랜스포머 모델의 샤드를 서빙하고, 함께 분산 추론 네트워크를 구성합니다. 각 노드는 Plumise 체인으로 인증하고, Oracle에 추론 메트릭을 보고하며, 기여도에 비례하여 PLM 보상을 받습니다.

## 아키텍처

```
+------------------+       +------------------+       +------------------+
|   Petals Node A  |       |   Petals Node B  |       |   Petals Node C  |
|  (blocks 0-3)    | <---> |  (blocks 4-7)    | <---> |  (blocks 8-11)   |
+--------+---------+       +--------+---------+       +--------+---------+
         |                          |                          |
         |   서명된 메트릭           |   서명된 메트릭           |   서명된 메트릭
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

## 주요 기능

- **체인 인증** -- 에이전트가 이더리움 프라이빗 키로 메시지를 서명하여 신원을 증명하고, 온체인 AgentRegistry에서 등록 여부를 검증합니다.
- **메트릭 수집** -- Petals 서버 파이프라인에서 추론 메트릭(처리된 토큰, 레이턴시, 업타임)을 스레드 안전하게 수집합니다.
- **Oracle 보고** -- 서명된 메트릭 리포트를 주기적으로 Plumise Oracle API에 전송합니다.
- **보상 추적** -- RewardPool 컨트랙트에서 대기 중인 보상을 모니터링하고, 임계값에 도달하면 자동으로 클레임합니다.
- **CLI 인터페이스** -- 서버 시작 및 상태 확인을 위한 간단한 커맨드라인 인터페이스를 제공합니다.

## 최소 요구사항

- **RAM**: 2GB 이상 (경량 모델 사용 시 ~300MB)
- **디스크**: 1GB 여유 공간
- **Python**: 3.10+
- **네트워크**: Plumise 체인 RPC 엔드포인트
- **지갑**: AgentRegistry에 등록된 이더리움 호환 프라이빗 키

> **GPU 불필요!** Petals는 CPU 추론을 지원합니다. Apple Silicon Mac, 저사양 PC에서도 참여하여 PLM 보상을 받을 수 있습니다.

### 모델 티어

| 티어 | 모델 | 2블록 기준 RAM | 전체 모델 크기 | 적합 환경 |
|------|------|----------------|----------------|-----------|
| **Lite** | `bigscience/bloom-560m` | ~300MB | ~1.1GB | 저사양 PC, 백그라운드 실행 |
| **Standard** | `bigscience/bloom-7b1` | ~1.5GB | ~14GB | RAM 16GB PC |
| **Pro** | `meta-llama/Llama-3.1-8B` | ~2GB | ~16GB (FP16) | RAM 32GB+ / Apple Silicon |
| **Ultra** | `meta-llama/Llama-3.1-70B` | ~10GB | ~140GB | GPU 서버 |

기본 모델은 **bloom-560m** (Lite 티어)입니다 -- 최소한의 하드웨어로 누구나 PLM 보상을 시작할 수 있습니다.

## 설치

```bash
# 저장소 클론
git clone https://github.com/mikusnuz/plumise-petals.git
cd plumise-petals

# 가상환경 생성
python -m venv .venv
source .venv/bin/activate

# 의존성 설치
pip install -e ".[dev]"
```

## 설정

환경 변수 예시 파일을 복사하고 수정합니다:

```bash
cp .env.example .env
```

| 변수 | 기본값 | 설명 |
|---|---|---|
| `PLUMISE_RPC_URL` | `http://localhost:26902` | Plumise 체인 RPC 엔드포인트 |
| `PLUMISE_CHAIN_ID` | `41956` | Plumise 체인 ID |
| `PLUMISE_PRIVATE_KEY` | -- | 에이전트 지갑 프라이빗 키 (hex) |
| `ORACLE_API_URL` | `http://localhost:3100` | Oracle API 기본 URL |
| `REPORT_INTERVAL` | `60` | 메트릭 보고 주기 (초) |
| `MODEL_NAME` | `bigscience/bloom-560m` | 서빙할 HuggingFace 모델 (모델 티어 참조) |
| `NUM_BLOCKS` | `2` | 서빙할 트랜스포머 블록 수 (많을수록 보상 증가) |
| `PETALS_HOST` | `0.0.0.0` | 서버 리슨 주소 |
| `PETALS_PORT` | `31330` | 서버 리슨 포트 |

## 사용법

### Docker로 빠르게 시작하기

```bash
# 환경 변수 파일 복사
cp .env.example .env

# 설정 편집 (프라이빗 키 설정)
nano .env

# 빌드 및 시작
docker compose up -d

# 로그 확인
docker compose logs -f

# 상태 확인
curl http://localhost:31330/health
```

자세한 Docker 배포 가이드는 [DEPLOYMENT.md](DEPLOYMENT.md)를 참조하세요.

### 수동 설치

```bash
# 환경 변수 / .env 사용
plumise-petals serve

# 명시적 옵션 사용
plumise-petals serve \
    --model bigscience/bloom-560m \
    --private-key 0xYOUR_PRIVATE_KEY \
    --rpc-url http://localhost:26902 \
    --oracle-url http://localhost:3100 \
    --num-blocks 2

# 더 무거운 모델로 더 많은 보상 받기
plumise-petals serve \
    --model meta-llama/Llama-3.1-8B \
    --num-blocks 4

# 상세 로깅
plumise-petals serve -v
```

### 상태 확인

```bash
plumise-petals status
```

출력:
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

## 프로젝트 구조

```
plumise-petals/
├── src/plumise_petals/
│   ├── chain/            # Plumise 체인 통합
│   │   ├── auth.py       # 에이전트 인증
│   │   ├── config.py     # 설정 관리
│   │   ├── reporter.py   # Oracle 메트릭 리포터
│   │   └── rewards.py    # 보상 추적 및 클레임
│   ├── server/           # Petals 서버 통합
│   │   ├── metrics.py    # 추론 메트릭 수집
│   │   └── plumise_server.py  # 체인 통합 서버
│   └── cli/              # 커맨드라인 인터페이스
│       └── run_server.py
├── contracts/            # 컨트랙트 ABI
│   ├── AgentRegistry.json
│   └── RewardPool.json
└── tests/                # 테스트 스위트
```

## 테스트 실행

```bash
pytest tests/ -v
```

## 스마트 컨트랙트

시스템은 두 개의 온체인 컨트랙트와 상호작용합니다:

### AgentRegistry
- `isRegistered(address)` -- 에이전트 등록 여부 확인
- `isActive(address)` -- 에이전트 활성 상태 확인
- `getAgent(address)` -- 전체 에이전트 레코드 조회
- `register(name, metadata)` -- 새 에이전트 등록

### RewardPool
- `getPendingReward(address)` -- 미청구 보상 조회
- `claimReward()` -- 누적된 보상 클레임
- `getContribution(address)` -- 기여 메트릭 조회
- `getCurrentEpoch()` -- 현재 보상 에포크 조회

## 라이선스

MIT
