# 샘플 매장 BOM 원가 시나리오를 산출해 BigQuery DM 테이블에 적재하는 모듈 (1매장 시범)
import logging
import os
from datetime import date, datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bom_cost_simulation")

BQ_PROJECT_ID = os.getenv("BQ_PROJECT_ID", "")
BQ_DATASET = os.getenv("BQ_DATASET", "carttiming")  # 실제 스키마: carttiming 데이터셋 하나(오너 확인)
BQ_TABLE = os.getenv("BQ_TABLE", "dm_store_bom_cost_simulation")
HORIZONS = (0, 7, 30)

# 적재 대상 테이블은 이미 DW 설계에 정의돼 있다(carttiming_bigquery_ddl.sql).
# 이 스크립트는 그 스키마를 따른다 — 임의로 컬럼을 만들면 적재가 거부된다.
#   store_id STRING NOT NULL / menu_id STRING NOT NULL
#   target_dt DATE NOT NULL (파티션 키) / simulated_total_cost NUMERIC

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
        # DW 스키마(carttiming.dm_store_bom_cost_simulation)에 맞춘 컬럼명·타입:
        #   store_id STRING / menu_id STRING / target_dt DATE / simulated_total_cost NUMERIC
        # horizon(0·7·30일)은 별도 컬럼 없이 target_dt로 표현한다.
        target_dt = (date.fromisoformat(sim_date) + timedelta(days=h)).isoformat()
        rows.append({
            "store_id": DEMO_STORE_ID,
            "menu_id": SAMPLE_MENU["name"],     # 메뉴 ID 체계 도입 전까지는 메뉴명을 키로 사용
            "target_dt": target_dt,
            "simulated_total_cost": int(round(total)),
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
    result = load_to_bigquery(rows)
    # 적재 실패를 워크플로 실패로 드러낸다(전에는 조용히 성공으로 끝나 알림이 안 갔음).
    # dry_run·empty는 정상 종료로 취급.
    if result.get("status") == "error":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
