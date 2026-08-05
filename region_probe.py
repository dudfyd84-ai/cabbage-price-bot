# KAMIS 지역별 소매가 커버리지를 확인하는 일회성 조사 스크립트 (#6 지역 확장 판단용)
import logging
import os
from datetime import date, timedelta

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("region_probe")

COLLECT_URL = os.getenv("COLLECT_URL", "")
COLLECT_TOKEN = os.getenv("COLLECT_TOKEN", "")


def probe(day):
    # KAMIS·ASOS는 해외 IP를 막아 GitHub 러너에서 직접 못 부른다.
    # 이미 쓰고 있는 /api/collect 위임 경로를 그대로 재사용한다.
    from retrain_pipeline import ITEMS, REGION_CODES

    logger.info("조사일 %s · 대상 품목 %d종", day, len(ITEMS))
    result = {}
    for name, code in REGION_CODES.items():
        r = requests.get(COLLECT_URL, params={"kind": "veg", "start": day.isoformat(),
                                              "end": day.isoformat(), "country": code},
                         headers={"X-Collect-Token": COLLECT_TOKEN}, timeout=180)
        r.raise_for_status()
        rows = r.json().get("rows", [])
        got = {x["품목명"]: x["가격"] for x in rows}
        result[name] = got
        logger.info("%-4s(%s) %2d/%d종 수집", name, code, len(got), len(ITEMS))

    seoul = result.get("서울", {})
    logger.info("--- 서울 대비 가격 차이 ---")
    for name, got in result.items():
        if name == "서울" or not got:
            continue
        diffs = [abs(got[k] - seoul[k]) / seoul[k] * 100 for k in got if k in seoul and seoul[k]]
        same = sum(1 for k in got if k in seoul and got[k] == seoul[k])
        if diffs:
            logger.info("%-4s 공통 %2d종 · 평균 차이 %4.1f%% · 서울과 완전히 같은 값 %d종",
                        name, len(diffs), sum(diffs) / len(diffs), same)
    return result


def main():
    if not COLLECT_URL or not COLLECT_TOKEN:
        logger.error("COLLECT_URL/COLLECT_TOKEN 미설정 — 조사 불가")
        raise SystemExit(1)
    # KAMIS는 발표까지 이틀쯤 걸리고 주말은 조사가 없어, 최근 평일 중 데이터가 있는 날을 찾는다.
    d = date.today() - timedelta(days=3)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    probe(d)


if __name__ == "__main__":
    main()
