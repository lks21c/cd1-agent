# KakaoTalk Setup Guide

KakaoTalk "나에게 보내기" API를 통한 알림 설정 가이드입니다.

## 사전 요구사항

1. Kakao Developers 계정
2. 등록된 Kakao 앱
3. Python 3.9+

## Step 1: Kakao 앱 생성

1. [Kakao Developers](https://developers.kakao.com) 접속
2. 로그인 후 "내 애플리케이션" → "애플리케이션 추가하기"
3. 앱 이름 입력 (예: "CD1 Agent Alerts")
4. 앱 생성 완료

## Step 2: REST API 키 확인

1. 생성된 앱 클릭
2. "앱 키" 섹션에서 **REST API 키** 복사
3. 환경 변수에 설정:
   ```bash
   export KAKAO_REST_API_KEY="your_rest_api_key"
   ```

## Step 3: 카카오 로그인 활성화

1. 앱 설정 → "카카오 로그인" 메뉴
2. "활성화 설정" ON
3. "Redirect URI" 추가:
   - 개발용: `https://localhost:5000`
   - 운영용: 실제 콜백 URL

## Step 4: 동의 항목 설정

1. 앱 설정 → "카카오 로그인" → "동의 항목"
2. "talk_message" 권한 활성화 (선택 동의)

## Step 5: 토큰 발급

### 방법 1: CLI 도구 사용 (권장)

```bash
# bdp_common 토큰 설정 도구 실행
python -m src.agents.bdp_common.kakao.notifier
```

실행 후:
1. 표시되는 인증 URL을 브라우저에서 열기
2. 카카오 로그인 및 동의
3. 리다이렉트된 URL에서 `code=` 값 복사
4. 터미널에 코드 입력
5. 토큰 발급 완료!

### 방법 2: 수동 발급

1. 인증 URL 생성:
   ```
   https://kauth.kakao.com/oauth/authorize?
     client_id={REST_API_KEY}&
     redirect_uri=https://localhost:5000&
     response_type=code&
     scope=talk_message
   ```

2. URL 접속 → 로그인 → 동의

3. 리다이렉트 URL에서 `code` 파라미터 추출

4. 토큰 요청:
   ```bash
   curl -X POST "https://kauth.kakao.com/oauth/token" \
     -d "grant_type=authorization_code" \
     -d "client_id={REST_API_KEY}" \
     -d "redirect_uri=https://localhost:5000" \
     -d "code={AUTH_CODE}"
   ```

5. 응답에서 `access_token`, `refresh_token` 저장

## Step 6: 토큰 저장

토큰을 JSON 파일로 저장:

```json
// conf/kakao_tokens.json
{
  "access_token": "your_access_token",
  "refresh_token": "your_refresh_token"
}
```

위치: `src/agents/bdp_common/conf/kakao_tokens.json`

## Step 7: 테스트

```python
from src.agents.bdp_common.kakao.notifier import KakaoNotifier

notifier = KakaoNotifier()
notifier.load_tokens()

success = notifier.send_text_message(
    "🎉 HDSP Monitoring 테스트 메시지입니다!"
)

if success:
    print("카카오톡 발송 성공!")
```

## 환경 변수 요약

```bash
# 필수
export KAKAO_REST_API_KEY="your_rest_api_key"

# 선택 (Client Secret 사용 시)
export KAKAO_CLIENT_SECRET="your_client_secret"

# 알림 활성화
export KAKAO_ENABLED="true"
```

## 토큰 자동 갱신

- Access Token: 12시간 유효 → 자동 갱신
- Refresh Token: 2개월 유효 → 갱신 시 함께 갱신
- KakaoNotifier가 자동으로 토큰 갱신 처리

## 문제 해결

### "Invalid client" 오류
- REST API 키 확인
- Redirect URI 설정 확인

### "token expired" 오류
- 토큰 재발급 필요
- CLI 도구로 재설정: `python -m src.agents.bdp_common.kakao.notifier`

### "talk_message scope required" 오류
- 동의 항목에서 "talk_message" 활성화 확인
- 사용자 동의 다시 받기

### 메시지 발송 실패
- 토큰 파일 경로 확인
- 네트워크 연결 확인
- API 호출 제한 확인 (일 1,000건)

## 보안 주의사항

1. **토큰 파일 Git 제외**: `.gitignore`에 추가
   ```
   **/kakao_tokens.json
   **/kakao_config.json
   ```

2. **프로덕션 환경**: AWS Secrets Manager 또는 Parameter Store 사용 권장

3. **Refresh Token**: 절대 로그에 노출되지 않도록 주의
