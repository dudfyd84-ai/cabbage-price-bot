# Cloudtype 배포 가이드 (한국 리전 — ASOS/KAMIS 차단 회피)

Railway에서 ASOS·KAMIS가 해외 IP 차단으로 실패해, 한국 PaaS인 [클라우드타입](https://cloudtype.io)으로 배포합니다. 같은 GitHub repo를 그대로 씁니다.

## 1. 가입 & 프로젝트 생성

1. [cloudtype.io](https://cloudtype.io) → **GitHub로 시작하기**(로그인)
2. 대시보드 → **+ 새 프로젝트** → **GitHub** 선택
3. `dudfyd84-ai/cabbage-price-bot` 선택
   - 안 보이면 **Configure GitHub App**으로 이 repo 접근 권한 부여 후 새로고침

## 2. 빌드/실행 설정

배포 설정 화면에서.

| 항목 | 값 |
|------|-----|
| 빌드 타입 | **Python** (자동 감지) |
| 설치 명령 | `pip install -r requirements.txt` (자동) |
| 시작 명령어 | `uvicorn app:app --host 0.0.0.0 --port 8000` |
| 포트 | `8000` |

## 3. 환경변수 등록

| Key | Value |
|-----|-------|
| `KAMIS_KEY` | ***REMOVED*** |
| `KAMIS_ID` | dudfyd84@gmail.com |
| `ASOS_KEY` | ***REMOVED*** |

## 4. 배포 & 검증

1. **배포하기** 클릭 → 빌드 로그 확인
2. 발급된 도메인으로 접속 확인.
   - `https://<도메인>/health` → `{"status":"ok","models":[7,30]}`
   - **`https://<도메인>/debug/net`** → `asos`, `kamis`가 `00`/`000` 으로 나오면 **한국 IP로 차단 회피 성공** ✅
3. 성공 시 카카오 i 오픈빌더 스킬 URL을 새 도메인 `/api/predict`로 교체

## 5. (성공 시) 완전 무인 자동화 — Cron

ASOS/KAMIS가 클라우드에서 되면, 재학습도 클라우드에서 돌릴 수 있어 **PC 없이 24시간 자동**이 됩니다.

1. Cloudtype에서 **스케줄(Cron) 작업** 추가
   - 명령: `python retrain_pipeline.py`
   - 스케줄: `0 22 * * *` (UTC 22시 = 한국 07시)
2. 데이터 영구 보존을 위해 **볼륨**을 web 서비스와 공유 (CSV·pkl 경로를 볼륨으로)

> 단, `/debug/net`에서 ASOS·KAMIS가 여전히 실패하면 한국 PaaS도 막힌 것이므로 로컬 주도(로컬 수집 + git push)로 전환합니다.
