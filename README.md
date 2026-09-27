# ONE PICK LEAGUE v6 — PWA Deploy Ready

주식모임 참가자가 각자 휴대폰으로 접속해 1인 1종목을 선택하고,
일주일 뒤 수익률을 비교하는 웹앱입니다.

## 핵심 기능

- 모임 방 생성
- 6자리 참가코드
- QR 입장
- 초대 링크
- 방장 PIN
- 비공개 종목 제출
- 동일 종목 중복 방지
- KOSPI/KOSDAQ 검색
- 전원 제출 후 동시 공개
- 방장 시작가·종료가 직접 입력
- 수동 가격 입력 백업
- LIVE 순위
- 주간 결과 확정
- 시즌 승점
- 월간 챔피언
- 배지
- 최근 12주 결과
- TOP3 결과 이미지 저장
- 자동 주차 전환
- Docker 배포
- Render Blueprint
- Railway 설정
- persistent SQLite 지원

## 로컬 실행

```bash
pip install -r requirements.txt
python app.py
```

## Docker

```bash
docker build -t one-pick-league .
docker run -p 8000:8000 one-pick-league
```

상세 배포 방법은 `DEPLOY.md`를 참고하세요.


## v6 추가
- PWA 설치 지원
- iPhone/Android 홈 화면 추가
- 앱 아이콘
- 서비스워커
- 오프라인 쉘 캐시
- `/healthz` 상태 확인 엔드포인트
