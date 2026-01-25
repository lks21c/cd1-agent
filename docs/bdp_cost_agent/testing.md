# BDP Compact Agent - 테스트 가이드

## 단위 테스트

### 전체 테스트 실행

```bash
pytest tests/agents/bdp_cost/ -v
```

### 개별 모듈 테스트

```bash
# 탐지 알고리즘 테스트
pytest tests/agents/bdp_cost/test_anomaly_detector.py -v

# 패턴 인식기 테스트
pytest tests/agents/bdp_cost/test_pattern_recognizers.py -v

# Summary 생성 테스트
pytest tests/agents/bdp_cost/test_summary_generator.py -v

# Handler 테스트
pytest tests/agents/bdp_cost/test_handler.py -v
```

## Mock 모드 테스트

### 환경 변수 설정

```bash
export BDP_PROVIDER=mock
export EVENT_PROVIDER=mock
export RDS_PROVIDER=mock
```

### Handler 테스트

```python
from src.agents.bdp_cost.handler import handler

result = handler({'days': 14}, None)
print(result)
```

### Python 스크립트

```bash
python -c "
from src.agents.bdp_cost.handler import handler

result = handler({'days': 14}, None)
print(result)
"
```

## LocalStack 통합 테스트

### 1. LocalStack 시작

```bash
docker-compose -f docker/localstack/docker-compose.yml up -d
```

### 2. 환경 변수 설정

```bash
export BDP_PROVIDER=localstack
export LOCALSTACK_ENDPOINT=http://localhost:4566
```

### 3. 테스트 데이터 로드

```bash
python scripts/load_localstack_data.py
```

### 4. 통합 테스트 실행

```bash
pytest tests/agents/bdp_cost/test_integration.py -v
pytest tests/agents/bdp_cost/test_localstack_integration.py -v
```

## API 테스트

### 서버 시작

```bash
# Background로 실행
python -m src.agents.bdp_cost.server &
```

### API 호출 테스트

```bash
# 상태 확인
curl http://localhost:8005/api/v1/status

# 탐지 실행
curl -X POST http://localhost:8005/api/v1/detect \
  -H "Content-Type: application/json" \
  -d '{"days": 14}'

# 계정 정보 조회
curl http://localhost:8005/api/v1/account
```

## 패턴 인식기 테스트

### 요일 패턴 테스트

```python
def test_weekday_pattern_reduces_confidence():
    """월요일 비용 증가가 평일 평균 범위 내면 confidence 하향"""
    # 평일 데이터 생성 (월~금)
    # 월요일 비용이 평일 평균 대비 정상 범위
    # → confidence_adjustment = -0.20
```

### 추세 패턴 테스트

```python
def test_trend_pattern_reduces_confidence():
    """점진적 증가가 추세선 내면 confidence 하향"""
    # 점진적 증가 데이터 생성
    # 현재 비용이 추세선 기반 예상 범위 내
    # → confidence_adjustment = -0.15
```

### 복합 패턴 테스트

```python
def test_multiple_patterns_combine():
    """여러 패턴 동시 인식 시 조정값 합산 (최대 제한)"""
    # 요일 패턴 + 추세 패턴 동시 적용
    # → total_adjustment = max(-0.35, -0.4)
```

## 테스트 커버리지

```bash
# 커버리지 측정
pytest tests/agents/bdp_cost/ --cov=src/agents/bdp_cost --cov-report=html

# 리포트 확인
open htmlcov/index.html
```

## 성능 테스트

### 대용량 데이터 테스트

```python
def test_large_dataset_performance():
    """100개 서비스 × 30일 데이터 처리 성능"""
    import time

    detector = CostDriftDetector()
    large_data = generate_large_mock_data(services=100, days=30)

    start = time.time()
    results = detector.analyze_batch(large_data)
    elapsed = time.time() - start

    assert elapsed < 10  # 10초 이내 처리
    assert len(results) == 100
```

## CI/CD 통합

### GitHub Actions 예시

```yaml
name: BDP Compact Tests

on:
  push:
    paths:
      - 'src/agents/bdp_cost/**'
      - 'tests/agents/bdp_cost/**'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install -e .[dev]

      - name: Run tests
        run: |
          pytest tests/agents/bdp_cost/ -v --cov=src/agents/bdp_cost

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## 트러블슈팅

### PyOD 설치 실패

Lambda 환경에서 PyOD 설치가 실패하면 LightweightECOD가 자동으로 사용됩니다:

```python
# 로그 확인
# "PyOD not available, using lightweight ECOD implementation"
```

### LocalStack 연결 실패

```bash
# LocalStack 상태 확인
docker ps | grep localstack

# 로그 확인
docker logs localstack

# 재시작
docker-compose -f docker/localstack/docker-compose.yml restart
```

### 테스트 데이터 불일치

```bash
# 테이블 초기화
python scripts/reset_localstack_data.py

# 데이터 재로드
python scripts/load_localstack_data.py
```
