# 저장소 CSV를 BigQuery 3-Tier DW(스테이징→DW→DM)에 매일 무인 적재하는 배치
import logging
import os
from datetime import date

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bq_daily_load")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BQ_PROJECT_ID = os.getenv("BQ_PROJECT_ID", "")
BQ_DATASET = os.getenv("BQ_DATASET") or "carttiming"

# 지역 코드는 기상청 지점명을 그대로 쓴다. 별도 코드 체계를 만들면 매핑 테이블만 늘고 얻는 게 없다.
REGIONS = ["서울", "부산", "대구", "광주", "대전"]


def _item_code_map():
    # 표준 품목코드는 app.py의 ITEMS 하나만 쓴다. 여기서 따로 목록을 들고 있으면
    # 품목이 늘 때마다(11종→19종처럼) DW만 조용히 낡는다.
    from app import ITEMS
    return ITEMS


def build_staging():
    # 저장소 CSV·모델 산출물 → 스테이징 3종. 전량 재생성이라 재실행해도 결과가 같다.
    items = _item_code_map()

    veg = pd.read_csv(os.path.join(BASE_DIR, "kamis_veg_retail.csv"))
    extra = os.path.join(BASE_DIR, "kamis_all_retail.csv")
    if os.path.exists(extra):
        a = pd.read_csv(extra, dtype={"품목코드": str})
        a = a[a["품목명"].isin(items)]
        veg = pd.concat([veg, a[["날짜", "품목명", "단위", "가격"]]], ignore_index=True)
    veg = veg[veg["품목명"].isin(items)].drop_duplicates(subset=["날짜", "품목명"], keep="last")
    stg_price = veg.rename(columns={"날짜": "base_dt", "품목명": "item_nm",
                                    "단위": "unit_info", "가격": "price"})[
        ["base_dt", "item_nm", "unit_info", "price"]]

    w = pd.read_csv(os.path.join(BASE_DIR, "weather_asos_data.csv"))
    w = w[w["지점명"].isin(REGIONS)]
    stg_weather = w.rename(columns={"날짜": "base_dt", "지점명": "region_nm",
                                    "평균기온": "avg_temp", "일강수량": "rainfall"})[
        ["base_dt", "region_nm", "avg_temp", "rainfall"]]

    stg_predict = _build_predict()

    dim = pd.DataFrame([{"item_cd": _std_code(n), "api_item_cd": c, "item_nm": n,
                         "std_unit": _unit_of(veg, n)} for n, c in items.items()])

    return {"stg_price": stg_price, "stg_weather": stg_weather,
            "stg_predict": stg_predict, "stg_dim_item": dim}


def _std_code(name):
    # 표준코드는 API 코드에서 기계적으로 만든다. 영문 별칭을 손으로 관리하면 품목 추가 때마다 빠뜨린다.
    from app import ITEMS
    return f"ITM_{ITEMS[name]}"


def _unit_of(veg, name):
    s = veg[veg["품목명"] == name]["단위"]
    return s.mode().iloc[0] if len(s) else ""


def _build_predict():
    # predict_log.csv(누적 예측 이력) × intervals.json(품목별 예측 구간 비율) → DM 서빙용 예측
    log = pd.read_csv(os.path.join(BASE_DIR, "predict_log.csv"))
    import json
    ipath = os.path.join(BASE_DIR, "intervals.json")
    ratios = {}
    if os.path.exists(ipath):
        with open(ipath, encoding="utf-8") as f:
            ratios = json.load(f).get("items", {})

    rows = []
    for r in log.itertuples(index=False):
        v = ratios.get(r.품목, {}).get(f"h{r.호라이즌}")
        lo, hi = (v["lo"], v["hi"]) if v else (0.85, 1.15)
        diff = (r.예측가 - r.현재가) / r.현재가 * 100 if r.현재가 else 0
        rows.append({
            "predict_base_dt": r.예측일, "target_dt": r.목표일,
            "api_item_cd": _code_of(r.품목), "predicted_price": int(r.예측가),
            "confidence_interval_min": round(r.예측가 * lo),
            "confidence_interval_max": round(r.예측가 * hi),
            "trend_flag": "U" if diff > 3 else ("D" if diff < -3 else "S")})
    return pd.DataFrame(rows)


def _code_of(name):
    from app import ITEMS
    return ITEMS.get(name, "")


# 스테이징을 전량 덮어쓰고(WRITE_TRUNCATE) DW·DM은 CREATE OR REPLACE로 다시 만든다.
# 샌드박스는 스트리밍 삽입과 대부분의 DML을 막지만 로드 잡과 CTAS는 허용한다.
# 전량 재생성이라 몇 번을 돌려도 결과가 같다 — 멱등성을 MERGE 조건이 아니라 구조로 보장한다.
DW_SQL = """
-- conversion_rate·main_region_cd는 아직 채울 원천이 없지만 DDL 스키마를 지켜 자리를 남긴다.
-- 스테이징 4컬럼으로 dim_item을 덮으면 이 컬럼들이 조용히 사라져 기존 쿼리가 깨진다.
CREATE OR REPLACE TABLE `{ds}.dim_item`
OPTIONS (description = '[DW-DIM] 농산물 표준 마스터.') AS
-- 품목코드는 '211' 같은 숫자 문자열이라 autodetect가 INT64로 추론한다.
-- 그대로 두면 dm_price_predict 조인에서 STRING vs INT64로 깨진다(실제로 겪음).
SELECT item_cd, CAST(api_item_cd AS STRING) AS api_item_cd, item_nm, std_unit,
  CAST(NULL AS NUMERIC) AS conversion_rate, CAST(NULL AS STRING) AS main_region_cd
FROM `{ds}.stg_dim_item`;

CREATE OR REPLACE TABLE `{ds}.fact_daily_price`
PARTITION BY base_dt CLUSTER BY item_cd
OPTIONS (description = '[DW-FACT] 정제된 일별 표준 시세(소매, dim_item.std_unit 기준).') AS
WITH src AS (
  SELECT CAST(s.base_dt AS DATE) AS base_dt, d.item_cd, CAST(s.price AS NUMERIC) AS avg_price_per_std_unit
  FROM `{ds}.stg_price` s JOIN `{ds}.dim_item` d ON s.item_nm = d.item_nm
)
SELECT base_dt, item_cd, avg_price_per_std_unit,
  CAST(AVG(avg_price_per_std_unit) OVER (
    PARTITION BY item_cd ORDER BY UNIX_DATE(base_dt)
    RANGE BETWEEN 6 PRECEDING AND CURRENT ROW) AS NUMERIC) AS moving_avg_7d
FROM src;

CREATE OR REPLACE TABLE `{ds}.fact_daily_weather`
PARTITION BY base_dt CLUSTER BY region_cd
OPTIONS (description = '[DW-FACT] 산지별 일별 기상 정제 데이터.') AS
SELECT CAST(base_dt AS DATE) AS base_dt, region_nm AS region_cd,
  CAST(avg_temp AS NUMERIC) AS avg_temp, CAST(rainfall AS NUMERIC) AS rainfall,
  CAST(SUM(rainfall) OVER (
    PARTITION BY region_nm ORDER BY UNIX_DATE(CAST(base_dt AS DATE))
    RANGE BETWEEN 6 PRECEDING AND CURRENT ROW) AS NUMERIC) AS cumulative_rainfall_7d
FROM `{ds}.stg_weather`;

CREATE OR REPLACE TABLE `{ds}.dm_price_predict`
PARTITION BY target_dt CLUSTER BY item_cd
OPTIONS (description = '[DM] AI 시세 예측 결과. 대시보드 Buy/Wait 시그널 원천.') AS
SELECT CAST(s.predict_base_dt AS DATE) AS predict_base_dt, CAST(s.target_dt AS DATE) AS target_dt,
  d.item_cd, CAST(s.predicted_price AS NUMERIC) AS predicted_price,
  CAST(s.confidence_interval_min AS NUMERIC) AS confidence_interval_min,
  CAST(s.confidence_interval_max AS NUMERIC) AS confidence_interval_max, s.trend_flag
FROM `{ds}.stg_predict` s JOIN `{ds}.dim_item` d ON CAST(s.api_item_cd AS STRING) = d.api_item_cd
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY predict_base_dt, target_dt, item_cd ORDER BY predicted_price) = 1;
"""


def run(tables):
    if not BQ_PROJECT_ID:
        logger.info("[dry-run] BQ_PROJECT_ID 미설정 — 적재 없이 산출물만 확인")
        for name, df in tables.items():
            logger.info("  %-14s %6d행  %s", name, len(df), list(df.columns))
        return "dry_run"

    from google.cloud import bigquery
    client = bigquery.Client(project=BQ_PROJECT_ID)
    ds = f"{BQ_PROJECT_ID}.{BQ_DATASET}"
    for name, df in tables.items():
        # DataFrame 직접 적재는 pyarrow를 요구한다. 배치 의존성을 늘리지 않으려고 JSON 로드 잡을 쓴다.
        # NaN은 JSON으로 직렬화되지 않으므로 None(null)으로 바꾼다.
        rows = df.astype(object).where(pd.notna(df), None).to_dict("records")
        job = client.load_table_from_json(
            rows, f"{ds}.{name}",
            job_config=bigquery.LoadJobConfig(
                autodetect=True,
                write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE))
        job.result()
        logger.info("스테이징 적재 %-14s %6d행", name, len(df))

    client.query(DW_SQL.format(ds=ds)).result()
    logger.info("DW·DM 재생성 완료 (dim_item / fact_daily_price / fact_daily_weather / dm_price_predict)")
    return "loaded"


def main():
    logger.info("===== BigQuery 일배치 시작 (%s) =====", date.today())
    tables = build_staging()
    status = run(tables)
    logger.info("===== 종료 (%s) =====", status)


if __name__ == "__main__":
    main()
