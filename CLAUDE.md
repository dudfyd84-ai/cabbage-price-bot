# CLAUDE.md — CartTiming 프로젝트 규칙 (에이전트 공통)

이 저장소에서 Claude Code로 작업하는 모든 팀원의 에이전트가 따르는 규칙이다. Claude Code는
이 파일을 자동으로 읽는다.

## 프로젝트
식자재 가격 예측 B2B 서비스. FastAPI 모놀리식 앱(`app.py`) + 매일 재학습 파이프라인
(`retrain_pipeline.py`) + 앱 화면(`app_screens/`). 배포는 Cloudtype 자동.

## 로컬 실행
```
pip install -r requirements.txt
python app.py     # http://localhost:8000  (앱 /app, 대시보드 /)
```
로컬엔 개발자 로그인 게이트가 없다(라이브만 적용). 자유롭게 개발한다.

## 협업 규칙 (필수)
- **`main` 직접 push 금지.** 반드시 `feature/*` 브랜치 → PR → 리뷰 → 병합. 자세한 흐름은 `CONTRIBUTING.md`.
- 브랜치명은 `feature/트랙-기능` (예: `feature/C-bom-manual-price`).
- **작업이 끝나면 push에서 멈추지 말고 PR까지 올린다.** 브랜치에만 있으면 리뷰가 가지 않는다.
- PR 본문에 `Closes #이슈번호`를 넣어 이슈와 연결한다.
- **한 PR엔 한 이슈만.** 여러 기능이 섞였으면 나눠서 올린다.
- 리뷰 지적을 반영할 땐 **새 PR을 열지 말고 같은 브랜치에 커밋·push**한다(PR이 자동 갱신됨).
- 커밋은 논리 단위 1개당 1개, 한국어 메시지로 무엇을 왜 바꿨는지 적는다.

## 트랙별 담당 (기능 담당제 — 맡은 기능은 화면까지 끝까지 책임)
- **A 데이터/ML**: 예측 엔진·데이터 수집 (`retrain_pipeline.py`, `kamis_all_collect.py`, 모델·데이터)
- **B 계정/결제**: 로그인·구독·결제 — `app.py` 인증·과금, `supabase_schema.sql`, `onboarding.html`, `plan.html`
- **C 핵심 화면/공용**: 홈·재고·BOM·품목상세·딜·주문 화면 + 공용 모듈 관리
- **D 알림/리포트**: `notify_kakao.py`, 리포트 모듈, `alerts.html`, BigQuery 쿼리

### ⚠️ 공용 파일 — 수정 시 절차 필수
`nav.js` · `ct-store.js` · `home-live.js` · `dashboard.html` · `app.py`
1. PR 본문에 **"공용 파일 수정: 파일명 — 이유"** 명시.
2. **@kjw0106을 리뷰어로 지정**.
3. **최소 범위**로만 수정(리팩터링은 별도 PR).
> 트랙 배정은 `ROADMAP.md` 참고.

## 손대지 말 것
- **데이터·모델 파일**(`*.csv`, `model_*.pkl`, `accuracy.json`)은 재학습 봇이 자동 관리한다. 수동 편집·커밋 금지.
- **비밀키·비밀번호는 코드에 넣지 않는다.** 환경변수 / GitHub Secret만 사용(`os.getenv`).

## 코딩 원칙
- **생각 먼저, 코드는 나중.** 구현 전 가정을 명시하고, 불확실하면 묻는다.
- **최소한의 코드로 해결한다.** 요청하지 않은 기능·추상화는 추가하지 않는다.
- 새 소스 파일 첫 줄에 파일 역할을 한국어 한 줄 주석으로 적는다(config 제외).
  - Python: `# KIS API를 비동기로 래핑하는 클라이언트`
- 한국어 문장은 `.` `?` `!`로 끝낸다.
- 코드를 건드렸으면 로컬 실행(`python app.py`)으로 최소한 동작을 확인하고 보고한다.
