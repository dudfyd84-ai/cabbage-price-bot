"""
결제 연동 모듈 (Mock)
이 파일은 정기결제(PG) 연동을 위한 모의(Mock) 결제 모듈입니다.
실제 토스페이먼츠(Toss Payments)나 포트원 API 연동 전, 프론트엔드와 백엔드의
구독 결제 흐름을 테스트하기 위해 사용됩니다.
작성자: @ryong9797
"""
import uuid
import time
from datetime import datetime, timedelta

def request_billing_key(auth_key: str, customer_key: str):
    """
    고객의 인증 키를 받아 정기결제용 빌링키(Billing Key)를 발급받는 모의 함수.
    실제 환경에서는 PG사 API를 호출하여 빌링키를 받아옵니다.
    """
    if not auth_key:
        return {"success": False, "error": "인증 키가 없습니다."}
    
    # 모의 빌링키 생성
    mock_billing_key = f"bln_{uuid.uuid4().hex[:10]}"
    return {
        "success": True,
        "billing_key": mock_billing_key,
        "customer_key": customer_key
    }

def process_subscription_payment(billing_key: str, amount: int, order_id: str):
    """
    발급받은 빌링키를 이용해 실제 결제(승인)를 요청하는 모의 함수.
    """
    if not billing_key or amount <= 0:
        return {"success": False, "error": "유효하지 않은 결제 정보입니다."}
    
    # 90% 확률로 결제 성공 시뮬레이션
    time.sleep(0.5) # 네트워크 지연 모의
    if int(time.time() * 1000) % 10 == 0:
        return {"success": False, "error": "카드 잔액 부족으로 결제가 거절되었습니다."}
        
    payment_key = f"pay_{uuid.uuid4().hex[:12]}"
    next_billing_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    
    return {
        "success": True,
        "payment_key": payment_key,
        "order_id": order_id,
        "amount": amount,
        "next_billing_date": next_billing_date
    }

def cancel_subscription(billing_key: str):
    """
    구독(정기결제) 해지를 요청하는 모의 함수.
    """
    if not billing_key:
        return {"success": False, "error": "빌링키가 없습니다."}
        
    return {
        "success": True,
        "message": "구독이 정상적으로 해지되었습니다."
    }
