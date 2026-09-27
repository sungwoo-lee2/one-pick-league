# ONE PICK LEAGUE v5 배포 가이드

## 가장 쉬운 방법: Render

1. 이 폴더 전체를 GitHub 저장소에 업로드합니다.
2. Render에서 `New +` → `Blueprint`를 선택합니다.
3. 방금 올린 GitHub 저장소를 연결합니다.
4. `render.yaml`을 자동 인식하게 둡니다.
5. 배포가 끝나면 `https://xxxx.onrender.com` 형태 주소가 생깁니다.
6. 그 주소를 모임 사람들에게 공유하면 됩니다.

이 설정은 `/var/data/league.db`에 SQLite DB를 보관하도록 작성되어 있습니다.
따라서 Render에서는 반드시 persistent disk가 포함된 플랜을 사용해야 데이터가 유지됩니다.

---

## Railway

1. GitHub에 이 프로젝트를 올립니다.
2. Railway → `New Project` → `Deploy from GitHub repo`
3. 저장소를 선택합니다.
4. Variables에 아래 값을 추가합니다.

- `SECRET_KEY`: 길고 랜덤한 문자열
- `DB_PATH`: `/data/league.db`

5. Railway에서 Volume을 추가하고 `/data`에 마운트합니다.
6. Public Networking을 켜면 공개 URL이 생성됩니다.

---

## Docker로 직접 실행

```bash
docker build -t one-pick-league .
docker run --rm -p 8000:8000 \
  -e SECRET_KEY="change-me" \
  -e DB_PATH="/data/league.db" \
  -v "$(pwd)/data:/data" \
  one-pick-league
```

브라우저:
`http://localhost:8000`

---

## 배포 후 체크

- 방 생성
- QR 열기
- 휴대폰 2대에서 서로 다른 이름으로 입장
- 동일 종목 중복 선택 방지 확인
- 전원 제출 후 방장 공개
- 방장 시작가·종료가 직접 입력
- 결과 확정
- 시즌 랭킹 유지 확인
- 서버 재시작 후 기존 데이터 유지 확인

---

## 주의

현재 로그인은 이름 기반 참가 + 방장 PIN 구조입니다.
소규모 주식 스터디용으로 단순화한 버전입니다.

공개 서비스로 확대하려면 다음이 필요합니다.

- 회원 로그인
- 비밀번호 해시
- CSRF 보호
- 요청 제한(rate limit)
- 관리자 권한 강화
- PostgreSQL
- 정기 백업
- 로그/오류 모니터링


---

# PWA 설치

배포 URL을 휴대폰에서 연 뒤:

## iPhone
1. Safari로 앱 주소 열기
2. 공유 버튼
3. `홈 화면에 추가`
4. `추가`

## Android
1. Chrome으로 앱 주소 열기
2. 우측 상단 메뉴
3. `앱 설치` 또는 `홈 화면에 추가`

설치 후에는 일반 앱 아이콘처럼 실행됩니다.

---

# 배포 후 추천 운영 방식

- 일요일 모임 시작 전: QR 화면 띄우기
- 참가자 입장
- 종목 비공개 제출
- 전원 제출 후 방장 공개
- 금요일 종가를 확인한 뒤 방장이 직접 입력
- 결과 확정
- TOP3 결과 이미지 저장
- 카카오톡 단체방에 공유
