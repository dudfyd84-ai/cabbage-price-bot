# 샘플 매장 BOM 원가 시나리오를 산출해 BigQuery DM 테이블에 적재하는 모듈 (1매장 시범)
import logging
import os
from datetime import date, datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bom_cost_simulation")

BQ_PROJECT_ID = os.getenv("BQ_PROJECT_ID", "")
BQ_DATASET = os.getenv("BQ_DATASET", "carttiming")  # 실제 스키마: carttiming 데이터셋 하나(오너 확인)
BQ_TABLE = os.getenv("BQ_TABLE", "dm_store_bom_cost_simulation")
HORIZONS = (0, 7, 30)

# dm_store_bom_cost_simulation 스키마(신규 제안 — Track A/B 예측·매장 데이터와 합의 전이라 가변적):
#   sim_date STRING, store_id STRING, menu_name STRING, horizon_days INTEGER,
#   total_cost INTEGER, created_at TIMESTAMP
SCHEMA = [
    ("sim_date", "STRING"),
    ("store_id", "STRING"),
    ("menu_name", "STRING"),
    ("horizon_days", "INTEGER"),
    ("total_cost", "INTEGER"),
    ("created_at", "TIMESTAMP"),
]

# 실제 매장별 BOM은 브라우저 localStorage/Supabase에만 있어 서버에서 못 읽음(이슈 #11과 동일한 제약) →
# report_weekly.py의 1품목 시범과 같은 방식으로, 데모 매장의 샘플 메뉴 1개로 시범 구현.
DEMO_STORE_ID = "demo-store-1"
SAMPLE_MENU = {
    "name": "배추김치찌개",
    "ings": [
        {"item": "배추", "qty_kg": 0.3},
        {"item": "대파", "qty_kg": 0.05},
        {"item": "마늘", "qty_kg": 0.02},
        {"item": "양파", "qty_kg": 0.1},
    ],
}


def fetch_dashboard():
    # /api/dashboard는 비로그인 요청에 p30/r30/ci30을 null로 마스킹함(구독 게이팅) —
    # 이 스크립트는 서버와 같은 레포에서 도는 내부 배치라 HTTP 대신 app.py의 원본 함수를 직접 호출해
    # 마스킹 없는 전체 데이터를 씀 — app.py는 읽기만 하고 수정하지 않음.
    from app import dashboard_data
    return dashboard_data()


def build_scenarios(data):
    items_by_name = {i["name"]: i for i in data.get("items", [])}
    sim_date = data.get("date", date.today().isoformat())
    created_at = datetime.now(timezone.utc).isoformat()

    price_by_horizon = {0: "cur", 7: "p7", 30: "p30"}
    rows = []
    for h in HORIZONS:
        field = price_by_horizon[h]
        total = 0
        missing = False
        for ing in SAMPLE_MENU["ings"]:
            it = items_by_name.get(ing["item"])
            price = it.get(field) if it else None
            if price is None:
                missing = True
                break
            total += price * ing["qty_kg"]
        if missing:
            logger.warning("품목 데이터 부족으로 horizon=%s일 시나리오 생략", h)
            continue
        rows.append({
            "sim_date": sim_date,
            "store_id": DEMO_STORE_ID,
            "menu_name": SAMPLE_MENU["name"],
            "horizon_days": h,
            "total_cost": int(round(total)),
            "created_at": created_at,
        })
    return rows


def load_to_bigquery(rows):
    if not rows:
        logger.info("적재할 시나리오가 없습니다.")
        return {"status": "empty"}

    if not BQ_PROJECT_ID:
        logger.info("[dry-run] BQ_PROJECT_ID 미설정 — BigQuery 적재 대신 결과만 출력")
        for r in rows:
            logger.info("  %s", r)
        return {"status": "dry_run", "rows": rows}

    table_id = f"{BQ_PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE}"
    try:
        from google.cloud import bigquery
        client = bigquery.Client(project=BQ_PROJECT_ID)
        # 스트리밍 삽입(insert_rows_json)은 BigQuery 샌드박스(무료)에서 금지된다
        # ("Streaming insert is not allowed in the free tier"). 로드 잡은 허용되므로 그쪽을 쓴다.
        job = client.load_table_from_json(
            rows,
            table_id,
            job_config=bigquery.LoadJobConfig(
                write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            ),
        )
        job.result()   # 완료 대기 (실패 시 예외)
        logger.info("BigQuery 적재 완료: %s행 → %s", len(rows), table_id)
        return {"status": "loaded", "rows": len(rows), "table": table_id}
    except Exception as e:
        logger.error("BigQuery 적재 실패: %s", e)
        return {"status": "error", "error": str(e)}


def main():
    data = fetch_dashboard()
    rows = build_scenarios(data)
    load_to_bigquery(rows)


if __name__ == "__main__":
    main()
