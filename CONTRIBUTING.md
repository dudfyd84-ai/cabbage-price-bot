# 협업 가이드 (CartTiming)

기능을 하나씩 나눠 개발하기 위한 팀 규칙이다. **GitHub Flow**를 따른다 —
`main`은 항상 배포 가능한 상태로 두고, 모든 작업은 브랜치 + PR로 진행한다.

## 핵심 규칙 3가지
1. **`main`에 직접 push 금지.** 반드시 브랜치 → PR → 리뷰 → 병합.
2. **`main`에 병합되면 운영 서버에 자동 배포된다.** 그러므로 `main`엔 완성·검증된 것만 올린다.
3. **비밀키(API 키·비번)는 코드에 넣지 않는다.** 환경변수 / GitHub Secret으로만 관리한다.

## 작업 흐름
```bash
# 1. 최신 main 받기
git checkout main
git pull origin main

# 2. 기능 브랜치 생성 (feature/기능이름)
git checkout -b feature/kakao-alert

# 3. 개발 → 커밋 (논리 단위 1개당 1커밋, 한국어 메시지)
git add -A
git commit -m "카카오 급등 알림 발송 기능 추가"

# 4. 원격에 올리기
git push -u origin feature/kakao-alert

# 5. GitHub에서 Pull Request 생성 → 팀원 리뷰 → main 병합
```
병합된 브랜치는 삭제한다. 다음 기능은 다시 1번부터.

## 브랜치 이름 규칙
- `feature/기능이름` — 새 기능 (예: `feature/subscription`)
- `fix/버그이름` — 버그 수정 (예: `fix/retail-unit`)
- 한 브랜치 = 한 기능. 여러 기능을 한 브랜치에 섞지 않는다.

## 커밋 규칙
- 한 문장으로 설명되는 논리 단위가 완성되면 커밋한다.
- 좋은 예 `재고 최적화 화면 실데이터 연동` / 나쁜 예 `이것저것 수정`.
- 메시지는 한국어로, 무엇을 왜 바꿨는지 적는다.

## 손대지 말아야 할 것
- **데이터·모델 파일**(`*.csv`, `model_*.pkl`, `accuracy.json`)은 매일 도는 재학습 봇이
  자동으로 갱신·커밋한다. 수동으로 편집·커밋하지 않는다(충돌 원인).
- `run_retrain.bat`, `.env` 등 키가 담긴 파일은 `.gitignore` 처리돼 있다. 절대 커밋하지 않는다.

## 로컬 실행
```bash
pip install -r requirements.txt
python app.py            # http://localhost:8000  (앱: /app, 대시보드: /)
```
재학습을 직접 돌려볼 일은 거의 없다(클라우드가 매일 자동 실행). 필요 시 키를 환경변수로 넣고 `python retrain_pipeline.py`.

## 배포
- `main` 병합 → GitHub Actions(`deploy.yml`)가 Cloudtype에 자동 배포.
- 매일 06:00(KST) 재학습(`retrain.yml`)이 데이터·모델을 갱신 후 자동 배포.
- 개별 화면 변경은 배포 후 라이브에서 눈으로 확인한다.

## (예정) main 브랜치 보호
곧 `main`에 "PR 승인 1명 필수 / 직접 push 금지"를 건다. 이때 재학습 봇 계정은
예외(bypass) 처리하여 자동 커밋이 막히지 않게 한다.
