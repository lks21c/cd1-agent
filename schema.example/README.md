# Schema Example Templates

이 디렉토리는 스키마 작성을 위한 템플릿 예시를 제공합니다.

## 사용 방법

1. 이 디렉토리의 내용을 `schema/` 디렉토리로 복사
2. 실제 환경에 맞게 스키마 파일 수정

```bash
# 템플릿 복사
cp -r schema.example/* schema/

# 또는 특정 파일만 복사
cp schema.example/tables/anomaly_logs.json schema/tables/
```

## 포함된 템플릿

### tables/
- `anomaly_logs.json` - 이상 징후 로그 테이블 예시
- `service_metrics.json` - 서비스 메트릭 테이블 예시
- `remediation_history.json` - 조치 이력 테이블 예시

## 스키마 형식

자세한 형식은 `schema/README.md`를 참조하세요.

## 주의사항

- 이 디렉토리는 Git에서 추적됩니다
- 민감한 실제 스키마 정보를 포함하지 마세요
- Mock 데이터 용도로만 사용하세요
