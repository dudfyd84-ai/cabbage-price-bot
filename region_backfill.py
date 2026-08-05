# 서울 외 4개 지역 소매가 과거 이력을 채우는 백필 스크립트 (#6, 기본 2년)
import logging
import os
import sys
from datetime import date, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("region_backfill")


def main():
    import retrain_pipeline as rp

    years = float(os.getenv("BACKFILL_YEARS", "2"))
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=int(365 * years))
    logger.info("지역 백필 %s ~ %s (%.1f년)", start, end, years)

    # 한 번에 다 돌리면 중간에 끊겼을 때 처음부터 다시다.
    # 분기(90일) 단위로 끊어 collect_region을 부르면 매 구간이 파일에 누적된다.
    cur = start
    total = 0
    while cur <= end:
        chunk_end = min(cur + timedelta(days=89), end)
        try:
            total += rp.collect_region(cur, chunk_end)
        except Exception as e:
            # 한 구간 실패로 전체를 버리지 않는다. 이미 받은 구간은 파일에 남아 있고
            # 다시 돌리면 중복 제거되므로 이어받기가 된다.
            logger.error("구간 %s~%s 실패: %s — 계속 진행", cur, chunk_end, e)
        cur = chunk_end + timedelta(days=1)

    logger.info("백필 완료: 이번 실행 %d행", total)
    if total == 0:
        logger.error("한 행도 못 받았다 — 수집 경로를 확인해야 한다")
        sys.exit(1)


if __name__ == "__main__":
    main()
