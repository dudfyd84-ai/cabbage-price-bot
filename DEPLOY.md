# 내 지갑 방어 봇 — Railway 배포 가이드

배추 가격 예측 카카오 챗봇 백엔드(FastAPI)를 Railway에 배포하는 절차입니다.

## 0. 구성 파일 (이미 준비됨)

| 파일 | 역할 |
|------|------|
| `app.py` | FastAPI 서버 (카카오 스킬 `/api/predict`) |
| `retrain_pipeline.py` | 일일 증분 수집 + 모델 재학습 (cron용) |
| `cabbage_model_h7/h30.pkl` | 예측 모델 (24피처) |
| `*.csv` | 날씨·가격·반입량 데이터 (초기 시드) |
| `requirements.txt` / `Procfile` / `railway.json` | 배포 설정 |
| `.env.example` | 환경변수 템플릿 (실제 키는 Railway에 등록) |

## 1. GitHub 저장소 (반드시 Private)

키는 환경변수로 분리돼 코드엔 없지만, 안전을 위해 **Private 저장소**를 권장합니다.

```bash
# 이 폴더에서 (git 커밋은 이미 1회 생성돼 있음)
gh repo create cabbage-price-bot --private --source=. --push
# 또는 GitHub에서 빈 repo 생성 후
git remote add origin https://github.com/<계정>/cabbage-price-bot.git
git push -u origin main
```

## 2. Railway 웹 서비스 배포

1. [railway.app](https://railway.app) 로그인 → **New Project → Deploy from GitHub repo** → `cabbage-price-bot` 선택
2. Railway가 `railway.json`/`Procfile`을 읽어 자동 빌드·배포
3. **Variables 탭**에서 환경변수 3개 등록 (`.env.example` 참고)
   - `KAMIS_KEY`, `KAMIS_ID`, `ASOS_KEY`
4. **Settings → Networking → Generate Domain** 으로 공개 URL 발급
5. 확인: `https://<도메인>/health` → `{"status":"ok","models":[7,30]}`

## 3. 일일 재학습 자동화 (택1)

**옵션 A — 간단 (권장 시작점):** cron 없이 운영하고, 로컬 PC의 작업 스케줄러(`CabbageRetrain`)가 데이터·모델을 갱신하면 주기적으로 `git push`. Railway가 자동 재배포하며 최신 모델 반영.

**옵션 B — 완전 자동 (cron):**
1. Railway 프로젝트에 **서비스 추가** (같은 repo) → Settings에서
   - Start Command: `python retrain_pipeline.py`
   - **Cron Schedule**: `0 22 * * *` (UTC 22시 = 한국 07시)
2. 데이터 영구 보존을 위해 두 서비스에 **Volume** 마운트 (예: `/data`)
   - 이 경우 `app.py`/`retrain_pipeline.py`의 `BASE_DIR`/`DIR`을 `/data`로 바꿔 CSV·pkl을 볼륨에 두어야 재배포 후에도 유지됩니다.

## 4. 카카오 i 오픈빌더 연결

1. 오픈빌더 → 스킬 → **스킬 URL**에 `https://<도메인>/api/predict` 등록
2. 블록 발화에 "배추" 포함 시 스킬 호출되도록 설정
3. 응답: `{"version":"2.0","template":{"outputs":[{"simpleText":{"text":...}}]}}` (이미 규격 준수)

## 참고

- ASOS는 전날 자료까지 제공 → 추론 피처는 로컬 CSV(전일까지) 기반, 현재가만 실시간 KAMIS.
- 모델 재학습 결과는 `retrain_log.txt`에 기록됩니다(.gitignore 처리).
