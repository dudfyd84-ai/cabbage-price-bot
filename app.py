# 스마트 장바구니 물가 예측 봇 — 카카오 스킬 FastAPI (다품목: 배추·무·양파·대파·마늘)
import os
import ssl
from datetime import date, timedelta

import joblib
import numpy as np
import pandas as pd
import requests
import urllib3
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
KAMIS_KEY = os.getenv("KAMIS_KEY", "")
KAMIS_ID = os.getenv("KAMIS_ID", "")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEATHER = os.path.join(BASE_DIR, "weather_asos_data.csv")
VEG = os.path.join(BASE_DIR, "kamis_veg_retail.csv")  # 소매(체감) 기준

# 지원 품목 {표시명: KAMIS item_code}
ITEMS = {"배추": "211", "무": "231", "양파": "245", "대파": "246", "마늘": "258",
         "당근": "232", "오이": "223", "시금치": "213", "상추": "214",
         "사과": "411", "배": "412"}
# 반입량(공급) 보유 품목만
INTAKE_FILE = {"배추": os.path.join(BASE_DIR, "garak_cabbage_intake.csv")}
# 비쌀 때 대체재 추천 (품목별)
ALT = {"배추": [("양배추", "212"), ("얼갈이배추", "215")]}
# 신뢰구간 근사용 백테스트 MAPE(%) — (H7, H30). 2026-07-04 retrain_log 홀드아웃 기준
MAPE_PCT = {"배추": (14.4, 18.1), "무": (12.2, 15.7), "양파": (10.4, 11.9),
            "대파": (10.4, 10.1), "마늘": (8.5, 9.4), "당근": (9.6, 12.0),
            "오이": (16.4, 21.6), "시금치": (12.4, 16.4), "상추": (10.3, 15.0),
            "사과": (9.0, 9.4), "배": (12.4, 16.4)}

app = FastAPI(title="내 지갑 방어 봇")

# 품목별 H7/H30 모델 로드: MODELS[code][H], 학습 시 저장한 소매 단위도 함께 로드
MODELS = {}
UNITS = {}
for name, code in ITEMS.items():
    MODELS[code] = {}
    for H in (7, 30):
        p = os.path.join(BASE_DIR, f"model_{code}_h{H}.pkl")
        if os.path.exists(p):
            meta = joblib.load(p)
            MODELS[code][H] = meta
            UNITS[name] = meta.get("unit") or "kg"


def _weather_with_lags():
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
    return w


def build_feature_frame(item):
    # 학습(train_veg_models)과 동일한 피처 시계열을 로컬 CSV에서 구성
    w = _weather_with_lags()
    veg = pd.read_csv(VEG); veg["날짜"] = pd.to_datetime(veg["날짜"])
    p = veg[veg["품목명"] == item][["날짜", "가격"]].rename(columns={"가격": "price"}).sort_values("날짜")
    df = pd.merge(w, p, on="날짜", how="left").sort_values("날짜").reset_index(drop=True)
    df["price"] = df["price"].ffill().bfill()
    for lag in [7, 14, 30]:
        df[f"price_lag{lag}"] = df["price"].shift(lag)
    if item in INTAKE_FILE:
        intake = pd.read_csv(INTAKE_FILE[item]); intake["날짜"] = pd.to_datetime(intake["날짜"])
        icol = [c for c in intake.columns if c != "날짜"][0]
        df = pd.merge(df, intake, on="날짜", how="left").sort_values("날짜").reset_index(drop=True)
        df[icol] = df[icol].ffill().bfill()
        for lag in [7, 14, 30]:
            df[f"intake_lag{lag}"] = df[icol].shift(lag)
        for win in [7, 14]:
            df[f"intake_ma{win}"] = df[icol].shift(1).rolling(win).mean()
    return df


def predict_item(item):
    code = ITEMS[item]
    df = build_feature_frame(item)
    preds = {}
    for H, meta in MODELS[code].items():
        d = df.copy()
        d["target_month"] = (d["날짜"] + pd.Timedelta(days=H)).dt.month
        d = d.dropna(subset=meta["features"])
        X = d[meta["features"]].iloc[[-1]]
        val = meta["model"].predict(X)[0]
        preds[H] = round(float(np.expm1(val)) if meta["log_target"] else float(val))
    cur = int(df["price"].iloc[-1])
    return preds, cur


def build_outputs(item, cur, p7, p30):
    unit = UNITS.get(item, "kg")
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

    btn = {"action": "message", "label": "다시 확인", "messageText": f"{item} 가격"}
    desc = f"{head}\n\n현재 {cur:,}원/{unit}\n→ 7일후 {p7:,}원\n→ 30일후 {p30:,}원 (예상)"
    outputs = [{"textCard": {"title": f"🥬 {item} 가격 예측", "description": desc, "buttons": [btn]}}]

    if pricey and item in ALT:
        alts = [f"· {n}" for n, _ in ALT[item]]
        outputs.append({"textCard": {
            "title": "💡 대체재 추천",
            "description": f"{item}가 비싼 시기예요. 이런 대안은 어때요?\n\n" + "\n".join(alts),
            "buttons": [btn]}})
    return outputs


class _TLS(HTTPAdapter):
    def init_poolmanager(self, *a, **k):
        ctx = create_urllib3_context(); ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        k["ssl_context"] = ctx
        return super().init_poolmanager(*a, **k)


_kamis = requests.Session(); _kamis.mount("https://", _TLS())
RETAIL_CATS = {"채소": "200", "과일": "400", "축산": "500", "수산": "600", "식량": "100"}
_retail_cache = {}


def _recent_weekday(offset=2):
    d = date.today() - timedelta(days=offset)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def retail_data():
    # KAMIS 소매 부류별 현재가 + 전년대비 등락 (실시간, 당일 캐싱)
    key = date.today().isoformat()
    if key in _retail_cache:
        return _retail_cache[key]
    regday = _recent_weekday(2)
    out = {}
    for gname, cat in RETAIL_CATS.items():
        rows, seen = [], set()
        try:
            r = _kamis.get("https://www.kamis.or.kr/service/price/xml.do",
                           params={"action": "dailyPriceByCategoryList", "p_product_cls_code": "01",
                                   "p_item_category_code": cat, "p_country_code": "1101",
                                   "p_regday": regday.isoformat(), "p_convert_kg_yn": "Y",
                                   "p_cert_key": KAMIS_KEY, "p_cert_id": KAMIS_ID, "p_returntype": "json"},
                           timeout=(8, 15), verify=False)
            data = r.json().get("data", {})
            its = data.get("item", []) if isinstance(data, dict) else []
            if isinstance(its, dict):
                its = [its]
            for it in its:
                code = str(it.get("item_code", ""))
                if not code or code in seen:
                    continue
                cur = str(it.get("dpr1", "")).replace(",", "").strip()
                if cur in ("", "-"):
                    cur = str(it.get("dpr2", "")).replace(",", "").strip()
                if cur in ("", "-"):
                    continue
                try:
                    cur_i = int(cur)
                except ValueError:
                    continue
                if cur_i <= 0:   # 결측(0원) 제외
                    continue
                seen.add(code)
                yr = None
                y = str(it.get("dpr6", "")).replace(",", "").strip()
                try:
                    if y not in ("", "-") and int(y) > 0:
                        yr = round((cur_i - int(y)) / int(y) * 100)
                        if abs(yr) > 150:   # KAMIS 1년전 값 이상치 방어
                            yr = None
                except ValueError:
                    pass
                rows.append({"name": it.get("item_name"), "unit": it.get("unit"), "cur": cur_i, "yr": yr})
        except Exception:
            pass
        if rows:
            out[gname] = rows
    result = {"date": regday.isoformat(), "groups": out}
    _retail_cache.clear(); _retail_cache[key] = result
    return result


@app.get("/api/retail")
def api_retail():
    return retail_data()


@app.get("/health")
def health():
    return {"status": "ok", "items": [i for i in ITEMS if MODELS.get(ITEMS[i])]}


@app.post("/api/predict")
async def predict(request: Request):
    body = await request.json()
    utter = body.get("userRequest", {}).get("utterance", "")
    target = next((i for i in ITEMS if i in utter), None)
    if not target or not MODELS.get(ITEMS[target]):
        names = ", ".join(ITEMS.keys())
        return {"version": "2.0", "template": {"outputs": [
            {"simpleText": {"text": f"지원 품목: {names}\n예) \"배추 가격 어때?\""}}]}}
    try:
        preds, cur = predict_item(target)
        outputs = build_outputs(target, cur, preds[7], preds[30])
    except Exception as e:
        outputs = [{"simpleText": {"text": f"일시적으로 예측을 가져오지 못했어요. 잠시 후 다시 시도해주세요. ({type(e).__name__})"}}]
    return {"version": "2.0", "template": {"outputs": outputs}}


def dashboard_data():
    # 5품목 현재가·예측·위험도·최근 추세를 한 번에 산출
    veg = pd.read_csv(VEG); veg["날짜"] = pd.to_datetime(veg["날짜"])
    items = []
    for name in ITEMS:
        if not MODELS.get(ITEMS[name]):
            continue
        preds, cur = predict_item(name)
        p7, p30 = preds.get(7, cur), preds.get(30, cur)
        r7 = round((p7 - cur) / cur * 100) if cur else 0
        r30 = round((p30 - cur) / cur * 100) if cur else 0
        level = "위험" if r30 > 15 else ("주의" if r7 > 10 else ("하락" if r7 < -10 else "안정"))
        sub = veg[veg["품목명"] == name].sort_values("날짜").tail(90)
        trend = [{"d": d.strftime("%m/%d"), "p": int(p)} for d, p in zip(sub["날짜"], sub["가격"])]
        m7, m30 = MAPE_PCT.get(name, (15.0, 20.0))
        items.append({"name": name, "unit": UNITS.get(name, "kg"), "cur": cur, "p7": p7, "p30": p30,
                      "r7": r7, "r30": r30, "level": level, "trend": trend,
                      "ci7": [round(p7 * (1 - m7 / 100)), round(p7 * (1 + m7 / 100))],
                      "ci30": [round(p30 * (1 - m30 / 100)), round(p30 * (1 + m30 / 100))]})
    latest = veg["날짜"].max().strftime("%Y-%m-%d")
    return {"date": latest, "items": items}


@app.get("/api/dashboard")
def api_dashboard():
    return dashboard_data()


@app.get("/", response_class=HTMLResponse)
def dashboard_page():
    return DASHBOARD_HTML


with open(os.path.join(BASE_DIR, "dashboard.html"), encoding="utf-8") as _f:
    DASHBOARD_HTML = _f.read()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
