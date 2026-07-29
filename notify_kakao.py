# 급등 예상 품목을 /api/dashboard에서 조회해 카카오 알림톡으로 발송하는 모듈 (1품목 시범)
import os
import logging

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("notify_kakao")

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:8000/api/dashboard")
KAKAO_BIZ_API_KEY = os.getenv("KAKAO_BIZ_API_KEY", "")
KAKAO_SENDER_KEY = os.getenv("KAKAO_SENDER_KEY", "")
# 대행사/채널 API가 아직 미확정이라 엔드포인트·템플릿 코드도 계약 후에나 채워짐 — 그전까진 더미 발송 유지
KAKAO_ALIMTALK_ENDPOINT = os.getenv("KAKAO_ALIMTALK_ENDPOINT", "")
KAKAO_TEMPLATE_CODE = os.getenv("KAKAO_TEMPLATE_CODE", "")
ALERT_RECEIVER_PHONE = os.getenv("ALERT_RECEIVER_PHONE", "")

ALERT_LEVEL = "위험"  # app.py dashboard_data()의 급등 판정(D+30 상승률 15% 초과)을 그대로 재사용


def fetch_alert_item():
    # 급등(위험) 품목 중 30일 상승률이 가장 높은 1개를 시범 발송 대상으로 선택.
    # /api/dashboard는 비로그인 조회 시 구독 게이팅으로 p30/r30/ci30을 null로 마스킹함(app.py 참고) —
    # 이 스크립트는 인증 헤더 없이 호출하므로 그 경우엔 공개된 r7로 대신 순위를 매김.
    res = requests.get(DASHBOARD_URL, timeout=10)
    res.raise_for_status()
    items = res.json().get("items", [])
    candidates = [i for i in items if i.get("level") == ALERT_LEVEL]
    if not candidates:
        return None
    return max(candidates, key=lambda i: i["r30"] if i.get("r30") is not None else i.get("r7", 0))


def build_alert_message(item):
    if item.get("r30") is not None and item.get("p30") is not None:
        return (
            f"🚨 {item['name']} 가격 급등 예상\n"
            f"30일 뒤 {item['r30']}% 상승 예상\n"
            f"현재 {item['cur']:,}원 → 예측 {item['p30']:,}원"
        )
    # r30/p30이 마스킹된 경우(비로그인 조회) 공개된 7일 예측으로 대체
    return (
        f"🚨 {item['name']} 가격 급등 예상 (위험 등급)\n"
        f"7일 뒤 {item['r7']:+d}% 변동 예상\n"
        f"현재 {item['cur']:,}원 → 7일 뒤 예측 {item['p7']:,}원"
    )


def send_alimtalk(phone, message):
    if not phone:
        logger.info("[발송 생략] 수신 번호(ALERT_RECEIVER_PHONE) 미설정")
        return {"status": "skipped", "reason": "no_phone"}

    configured = KAKAO_BIZ_API_KEY and KAKAO_SENDER_KEY and KAKAO_ALIMTALK_ENDPOINT and KAKAO_TEMPLATE_CODE
    if not configured:
        logger.info("[더미 발송] 카카오 알림톡 자격증명/엔드포인트/템플릿 코드 미설정 — 콘솔 출력만 수행")
        logger.info("수신: %s\n%s", phone, message)
        return {"status": "dummy", "phone": phone, "message": message}

    # 대행사(예: NHN Cloud Bizmessage, 알리고 등)가 아직 확정되지 않아, 아래는 흔한 REST 발송 규격으로
    # 짜둔 스켈레톤임. 실제 계약한 대행사 문서에 맞춰 엔드포인트 URL·요청 바디 필드명을 조정해야 함.
    payload = {
        "senderKey": KAKAO_SENDER_KEY,
        "templateCode": KAKAO_TEMPLATE_CODE,
        "receiver": phone,
        "message": message,
    }
    headers = {"Authorization": f"Bearer {KAKAO_BIZ_API_KEY}", "Content-Type": "application/json"}
    try:
        res = requests.post(KAKAO_ALIMTALK_ENDPOINT, json=payload, headers=headers, timeout=10)
        res.raise_for_status()
        logger.info("알림톡 발송 성공: %s", phone)
        return {"status": "sent", "phone": phone, "response": res.json() if res.content else None}
    except requests.RequestException as e:
        logger.error("알림톡 발송 실패: %s", e)
        return {"status": "error", "phone": phone, "error": str(e)}


def main():
    item = fetch_alert_item()
    if not item:
        logger.info("급등(위험) 품목 없음 — 발송 생략")
        return
    message = build_alert_message(item)
    send_alimtalk(ALERT_RECEIVER_PHONE, message)


if __name__ == "__main__":
    main()
