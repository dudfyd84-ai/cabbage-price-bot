# 스마트 장바구니 물가 예측 봇 — 카카오 스킬용 FastAPI 서버 (반입량 포함, 로컬 피처 기반)
import os
import ssl
from datetime import date, timedelta

import joblib
import numpy as np
import pandas as pd
import requests
import urllib3
from fastapi import FastAPI, Request
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

KAMIS_KEY = os.getenv("KAMIS_KEY", "")
KAMIS_ID = os.getenv("KAMIS_ID", "")
ASOS_KEY = os.getenv("ASOS_KEY", "")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEATHER = os.path.join(BASE_DIR, "weather_asos_data.csv")
PRICE = os.path.join(BASE_DIR, "kamis_cabbage_daily.csv")
INTAKE = os.path.join(BASE_DIR, "garak_cabbage_intake.csv")

app = FastAPI(title="내 지갑 방어 봇")

MODELS = {}
for H in (7, 30):
    path = os.path.join(BASE_DIR, f"cabbage_model_h{H}.pkl")
    MODELS[H] = joblib.load(path) if os.path.exists(path) else None


class _TLS(HTTPAdapter):
    # KAMIS 구형 TLS 호환
    def init_poolmanager(self, *a, **k):
        ctx = create_urllib3_context(); ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        k["ssl_context"] = ctx
        return super().init_poolmanager(*a, **k)


_kamis = requests.Session(); _kamis.mount("https://", _TLS())


def build_feature_frame():
    # 학습과 동일한 파이프라인으로 로컬 CSV에서 전체 피처 시계열을 구성 (retrain이 매일 갱신)
    w = pd.read_csv(WEATHER)
    w = w[w["지점명"] == "서울"].copy()
    w["날짜"] = pd.to_datetime(w["날짜"]); w = w.sort_values("날짜").reset_index(drop=True)
    for c in ["평균기온", "최고기온", "일강수량"]:
        w[c] = pd.to_numeric(w[c], errors="coerce")
    w["일강수량"] = w["일강수량"].fillna(0)
    for col in ["평균기온", "최고기온", "일강수량"]:
        for lag in [30, 45, 60]:
            w[f"{col}_lag{lag}"] = w[col].shift(lag)
        for win in [7, 14]:
            w[f"{col}_ma{win}"] = w[col].shift(1).rolling(win).mean()

    p = pd.read_csv(PRICE)
    p = p[(p["지역"] == "서울") & (p["품목명"] == "배추")].copy()
    p["날짜"] = pd.to_datetime(p["날짜"])
    p = p[["날짜", "가격"]].rename(columns={"가격": "배추가격"}).sort_values("날짜")

    df = pd.merge(w, p, on="날짜", how="left").sort_values("날짜").reset_index(drop=True)
    df["배추가격"] = df["배추가격"].ffill().bfill()
    for lag in [7, 14, 30]:
        df[f"가격_lag{lag}"] = df["배추가격"].shift(lag)

    intake = pd.read_csv(INTAKE); intake["날짜"] = pd.to_datetime(intake["날짜"])
    df = pd.merge(df, intake, on="날짜", how="left").sort_values("날짜").reset_index(drop=True)
    df["배추반입량_톤"] = df["배추반입량_톤"].ffill().bfill()
    for lag in [7, 14, 30]:
        df[f"반입량_lag{lag}"] = df["배추반입량_톤"].shift(lag)
    for win in [7, 14]:
        df[f"반입량_ma{win}"] = df["배추반입량_톤"].shift(1).rolling(win).mean()
    return df


def predict_all():
    # 두 모델 예측 + 로컬 최신 가격 반환
    df = build_feature_frame()
    preds = {}
    for H, meta in MODELS.items():
        if meta is None:
            continue
        d = df.copy()
        d["target_month"] = (d["날짜"] + pd.Timedelta(days=H)).dt.month
        d = d.dropna(subset=meta["features"])
        X = d[meta["features"]].iloc[[-1]]
        val = meta["model"].predict(X)[0]
        preds[H] = round(float(np.expm1(val)) if meta["log_target"] else float(val))
    local_price = int(df["배추가격"].iloc[-1])
    return preds, local_price


def fetch_current_price(itemcode="211"):
    # 현재가는 실시간 KAMIS (휴장이면 직전 평일, 실패 시 None). 211=배추 212=양배추 215=얼갈이배추
    d = date.today()
    for _ in range(6):
        try:
            resp = _kamis.get("https://www.kamis.or.kr/service/price/xml.do",
                              params={"action": "ItemInfo", "p_productclscode": "02",
                                      "p_regday": d.isoformat(), "p_itemcategorycode": "200",
                                      "p_itemcode": itemcode, "p_convert_kg_yn": "Y",
                                      "p_cert_key": KAMIS_KEY, "p_cert_id": KAMIS_ID,
                                      "p_returntype": "json"}, timeout=15, verify=False)
            for it in resp.json()["data"]["item"]:
                if it.get("countyname") == "서울":
                    raw = str(it.get("price", "")).replace(",", "").strip()
                    if raw not in ("", "-"):
                        return int(raw)
        except Exception:
            pass
        d -= timedelta(days=1)
    return None


RETRY_BTN = {"action": "message", "label": "다시 확인", "messageText": "배추 가격"}


def build_outputs(cur, p7, p30):
    # 위험도 판정 + 카드형 응답(textCard). 비쌀 땐 대체재 카드 추가.
    r7 = (p7 - cur) / cur * 100 if cur else 0
    r30 = (p30 - cur) / cur * 100 if cur else 0
    if r30 > 15:
        head, pricey = f"🚨 위험! 한 달 내 폭등 예상 (+{r30:.0f}%)\n지금 사두세요!", True
    elif r7 > 10:
        head, pricey = f"⚠️ 이번 주 상승세 (+{r7:.0f}%)\n미리 구매를 권장합니다.", True
    elif r7 < -10:
        head, pricey = f"🟢 곧 내려갑니다 ({r7:.0f}%)\n며칠 기다리세요!", False
    else:
        head, pricey = "🟢 안정적입니다\n필요한 만큼만 구매하세요.", False

    desc = f"{head}\n\n현재 {cur:,}원/kg\n→ 7일후 {p7:,}원\n→ 30일후 {p30:,}원 (예상)"
    outputs = [{"textCard": {"title": "🥬 배추 가격 예측", "description": desc, "buttons": [RETRY_BTN]}}]

    if pricey:  # 비쌀 때 대체재 추천 (가격은 best-effort, 실패해도 이름은 표시)
        alts = []
        for name, code in [("양배추", "212"), ("얼갈이배추", "215")]:
            pr = fetch_current_price(code)
            alts.append(f"· {name} {pr:,}원/kg" if pr else f"· {name}")
        outputs.append({"textCard": {
            "title": "💡 대체재 추천",
            "description": "배추가 비싼 시기예요. 이런 대안은 어때요?\n\n" + "\n".join(alts),
            "buttons": [RETRY_BTN]}})
    return outputs


@app.get("/health")
def health():
    return {"status": "ok", "models": [h for h, m in MODELS.items() if m]}


@app.get("/debug/net")
def debug_net():
    # 클라우드에서 한국 공공 API 3종 연결 가능 여부 진단 (배포 경로 결정용, 추후 제거)
    res = {}
    day = (date.today() - timedelta(days=2)).strftime("%Y%m%d")
    try:
        r = requests.get("http://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList",
                         params={"serviceKey": ASOS_KEY, "pageNo": 1, "numOfRows": 1, "dataType": "JSON",
                                 "dataCd": "ASOS", "dateCd": "DAY", "startDt": day, "endDt": day, "stnIds": 108},
                         timeout=10)
        res["asos"] = r.json().get("response", {}).get("header", {}).get("resultCode", "?")
    except Exception as e:
        res["asos"] = "ERR:" + type(e).__name__
    try:
        r = _kamis.get("https://www.kamis.or.kr/service/price/xml.do",
                       params={"action": "ItemInfo", "p_productclscode": "02", "p_regday": (date.today()-timedelta(days=3)).isoformat(),
                               "p_itemcategorycode": "200", "p_itemcode": "211", "p_convert_kg_yn": "Y",
                               "p_cert_key": KAMIS_KEY, "p_cert_id": KAMIS_ID, "p_returntype": "json"},
                       timeout=10, verify=False)
        res["kamis"] = r.json().get("data", {}).get("error_code", "?")
    except Exception as e:
        res["kamis"] = "ERR:" + type(e).__name__
    try:
        r = requests.get("http://www.garak.co.kr/homepage/publicdata/dataJsonOpen.do",
                         params={"id": "9015", "passwd": "***REMOVED***", "dataid": "data22",
                                 "pagesize": "10", "pageidx": "1", "portal.templet": "false", "date": day},
                         timeout=10)
        res["garak"] = "ok:" + str(len(r.json().get("resultData", [])))
    except Exception as e:
        res["garak"] = "ERR:" + type(e).__name__
    # 환경변수 주입 여부 (값이 아니라 길이만 — 보안)
    res["env_len"] = {"ASOS_KEY": len(ASOS_KEY), "KAMIS_KEY": len(KAMIS_KEY), "KAMIS_ID": len(KAMIS_ID)}
    return res


@app.post("/api/predict")
async def predict(request: Request):
    body = await request.json()
    utter = body.get("userRequest", {}).get("utterance", "")
    if "배추" not in utter or not MODELS.get(7):
        return {"version": "2.0", "template": {"outputs": [
            {"simpleText": {"text": "현재 '배추' 가격 예측만 지원합니다."}}]}}
    try:
        preds, local_price = predict_all()
        cur = fetch_current_price() or local_price
        outputs = build_outputs(cur, preds[7], preds[30])
    except Exception as e:
        outputs = [{"simpleText": {"text": f"일시적으로 예측을 가져오지 못했어요. 잠시 후 다시 시도해주세요. ({type(e).__name__})"}}]
    return {"version": "2.0", "template": {"outputs": outputs}}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
