# 급등 예상 품목을 /api/dashboard에서 조회해 카카오 알림톡으로 발송하는 모듈 (1품목 시범)
import os
import logging

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("notify_kakao")

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:8000/api/dashboard")
KAKAO_BIZ_API_KEY = os.getenv("KAKAO_BIZ_API_KEY", "")
KAKAO_SENDER_KEY = os.getenv("KAKAO_SENDER_KEY", "")
ALERT_RECEIVER_PHONE = os.getenv("ALERT_RECEIVER_PHONE", "")

ALERT_LEVEL = "위험"  # app.py dashboard_data()의 급등 판정(D+30 상승률 15% 초과)을 그대로 재사용


def fetch_alert_item():
    # 급등(위험) 품목 중 30일 상승률이 가장 높은 1개를 시범 발송 대상으로 선택
    res = requests.get(DASHBOARD_URL, timeout=10)
    res.raise_for_status()
    items = res.json().get("items", [])
    candidates = [i for i in items if i.get("level") == ALERT_LEVEL]
    if not candidates:
        return None
    return max(candidates, key=lambda i: i["r30"])


def build_alert_message(item):
    return (
        f"🚨 {item['name']} 가격 급등 예상\n"
        f"30일 뒤 {item['r30']}% 상승 예상\n"
        f"현재 {item['cur']:,}원 → 예측 {item['p30']:,}원"
    )


def send_alimtalk(phone, message):
    # 카카오 비즈메시지 발송 방식(대행사/채널 API) 미확정 → 더미 발송으로 로그만 남김.
    # 자격증명(KAKAO_BIZ_API_KEY 등) 확정 후 이 함수 내부만 실제 API 호출로 교체.
    if not (KAKAO_BIZ_API_KEY and KAKAO_SENDER_KEY and phone):
        logger.info("[더미 발송] KAKAO_BIZ_API_KEY/KAKAO_SENDER_KEY/ALERT_RECEIVER_PHONE 미설정 — 콘솔 출력만 수행")
        logger.info("수신: %s\n%s", phone or "(미설정)", message)
        return {"status": "dummy", "phone": phone, "message": message}

    # TODO: 카카오 비즈메시지 발송 방식 확정 후 실제 API 호출로 교체
    logger.info("[더미 발송] 실제 API 연동 전 — 콘솔 출력만 수행")
    logger.info("수신: %s\n%s", phone, message)
    return {"status": "dummy", "phone": phone, "message": message}


def main():
    item = fetch_alert_item()
    if not item:
        logger.info("급등(위험) 품목 없음 — 발송 생략")
        return
    message = build_alert_message(item)
    send_alimtalk(ALERT_RECEIVER_PHONE, message)


if __name__ == "__main__":
    main()
