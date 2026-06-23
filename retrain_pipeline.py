# 매일 최신 데이터를 증분 수집하고 채소 5품목 예측 모델(H7/H30)을 재학습하는 자동화 파이프라인
import os
import ssl
import time
from datetime import date, timedelta, datetime

import joblib
import numpy as np
import pandas as pd
import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_percentage_error

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DIR = os.path.dirname(os.path.abspath(__file__))
WEATHER = os.path.join(DIR, "weather_asos_data.csv")
VEG = os.path.join(DIR, "kamis_veg_daily.csv")
INTAKE = os.path.join(DIR, "garak_cabbage_intake.csv")
LOG = os.path.join(DIR, "retrain_log.txt")

ASOS_KEY = os.getenv("ASOS_KEY", "")
KAMIS_KEY = os.getenv("KAMIS_KEY", "")
KAMIS_ID = os.getenv("KAMIS_ID", "")
STATIONS = {108: "서울", 159: "부산", 143: "대구", 156: "광주", 133: "대전"}
ITEMS = {"211": "배추", "231": "무", "245": "양파", "246": "대파", "258": "마늘"}  # code: name
INTAKE_ITEMS = {"배추": INTAKE}

GARAK_URL = "http://www.garak.co.kr/homepage/publicdata/dataJsonOpen.do"
GARAK_BASE = {"id": "9015", "passwd": "***REMOVED***", "dataid": "data22",
              "pagesize": "1000", "pageidx": "1", "portal.templet": "false"}
KAMIS_URL = "https://www.kamis.or.kr/service/price/xml.do"


class _TLS(HTTPAdapter):
    def init_poolmanager(self, *a, **k):
        ctx = create_urllib3_context(); ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        k["ssl_context"] = ctx
        return super().init_poolmanager(*a, **k)


_kamis = requests.Session(); _kamis.mount("https://", _TLS())


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def weekdays(start, end):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def incremental_weather():
    df = pd.read_csv(WEATHER)
    last = pd.to_datetime(df["날짜"]).max().date()
    start, end = last + timedelta(days=1), date.today() - timedelta(days=1)
    if start > end:
        log(f"날씨 최신 ({last}). 추가 없음."); return 0
    rows = []
    for stn, name in STATIONS.items():
        try:
            r = requests.get("http://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList",
                             params={"serviceKey": ASOS_KEY, "pageNo": 1, "numOfRows": 999, "dataType": "JSON",
                                     "dataCd": "ASOS", "dateCd": "DAY", "startDt": start.strftime("%Y%m%d"),
                                     "endDt": end.strftime("%Y%m%d"), "stnIds": stn}, timeout=30)
            body = r.json()["response"]["body"]
            if int(body["totalCount"]) == 0:
                continue
            for it in body["items"]["item"]:
                rows.append({"날짜": it.get("tm", ""), "지점명": name,
                             "평균기온": it.get("avgTa", ""), "최고기온": it.get("maxTa", ""),
                             "최저기온": it.get("minTa", ""), "일강수량": it.get("sumRn", ""),
                             "일조합": it.get("sumSsHr", "")})
        except Exception as e:
            log(f"  날씨 {name} 실패: {e}")
        time.sleep(0.5)
    if rows:
        pd.concat([df, pd.DataFrame(rows)], ignore_index=True).to_csv(WEATHER, index=False, encoding="utf-8-sig")
    log(f"날씨 {start}~{end} 추가 {len(rows)}행.")
    return len(rows)


def incremental_veg():
    # dailyPriceByCategoryList로 채소 5품목 서울 도매가 증분 수집
    df = pd.read_csv(VEG)
    last = pd.to_datetime(df["날짜"]).max().date()
    start, end = last + timedelta(days=1), date.today() - timedelta(days=1)
    days = list(weekdays(start, end))
    if not days:
        log(f"채소가격 최신 ({last}). 추가 없음."); return 0
    rows = []
    for d in days:
        try:
            r = _kamis.get(KAMIS_URL, params={"action": "dailyPriceByCategoryList", "p_product_cls_code": "02",
                                              "p_item_category_code": "200", "p_country_code": "1101",
                                              "p_regday": d.isoformat(), "p_convert_kg_yn": "Y",
                                              "p_cert_key": KAMIS_KEY, "p_cert_id": KAMIS_ID, "p_returntype": "json"},
                           timeout=(8, 15), verify=False)
            data = r.json().get("data", {})
            items = data.get("item", []) if isinstance(data, dict) else []
            if isinstance(items, dict):
                items = [items]
            seen = set()
            for it in items:
                code = str(it.get("item_code", ""))
                if code in ITEMS and code not in seen:
                    raw = str(it.get("dpr1", "")).replace(",", "").strip()
                    if raw not in ("", "-"):
                        rows.append({"날짜": d.isoformat(), "품목명": ITEMS[code], "가격": int(raw)})
                        seen.add(code)
        except Exception as e:
            log(f"  채소가격 {d} 실패: {e}")
        time.sleep(0.25)
    if rows:
        pd.concat([df, pd.DataFrame(rows)], ignore_index=True).to_csv(VEG, index=False, encoding="utf-8-sig")
    log(f"채소가격 {start}~{end} 추가 {len(rows)}행.")
    return len(rows)


def incremental_intake():
    df = pd.read_csv(INTAKE)
    last = pd.to_datetime(df["날짜"]).max().date()
    start, end = last + timedelta(days=1), date.today() - timedelta(days=1)
    days = list(weekdays(start, end))
    if not days:
        log(f"반입량 최신 ({last}). 추가 없음."); return 0
    rows = []
    for d in days:
        try:
            r = requests.get(GARAK_URL, params=dict(GARAK_BASE, date=d.strftime("%Y%m%d")), timeout=(8, 15))
            for it in r.json().get("resultData", []):
                if str(it.get("PUM_CD", "")) == "21100":
                    try:
                        rows.append({"날짜": d.isoformat(), "배추반입량_톤": round(float(it.get("SUM_TOT", 0)), 3)})
                    except (TypeError, ValueError):
                        pass
                    break
        except Exception as e:
            log(f"  반입량 {d} 실패: {e}")
        time.sleep(0.25)
    if rows:
        pd.concat([df, pd.DataFrame(rows)], ignore_index=True).to_csv(INTAKE, index=False, encoding="utf-8-sig")
    log(f"반입량 {start}~{end} 추가 {len(rows)}행.")
    return len(rows)


def _make():
    return XGBRegressor(n_estimators=400, max_depth=4, learning_rate=0.05,
                        subsample=0.8, colsample_bytree=0.8, random_state=42)


def retrain_all():
    # 갱신된 데이터로 5품목 H7/H30 모델 재학습
    w = pd.read_csv(WEATHER)
    w = w[w["지점명"] == "서울"].copy()
    w["날짜"] = pd.to_datetime(w["날짜"]); w = w.sort_values("날짜").reset_index(drop=True)
    for c in ["평균기온", "최고기온", "일강수량"]:
        w[c] = pd.to_numeric(w[c], errors="coerce")
    w["일강수량"] = w["일강수량"].fillna(0)
    wf = []
    for col in ["평균기온", "최고기온", "일강수량"]:
        for lag in [30, 45, 60]:
            n = f"{col}_lag{lag}"; w[n] = w[col].shift(lag); wf.append(n)
        for win in [7, 14]:
            n = f"{col}_ma{win}"; w[n] = w[col].shift(1).rolling(win).mean(); wf.append(n)

    veg = pd.read_csv(VEG); veg["날짜"] = pd.to_datetime(veg["날짜"])
    summary = {}
    for code, name in ITEMS.items():
        p = veg[veg["품목명"] == name][["날짜", "가격"]].rename(columns={"가격": "price"}).sort_values("날짜")
        if len(p) < 200:
            log(f"  {name}: 데이터 부족, 건너뜀"); continue
        df = pd.merge(w, p, on="날짜", how="left").sort_values("날짜").reset_index(drop=True)
        df["price"] = df["price"].ffill().bfill()
        for lag in [7, 14, 30]:
            df[f"price_lag{lag}"] = df["price"].shift(lag)
        feats = wf + ["price_lag7", "price_lag14", "price_lag30"]
        if name in INTAKE_ITEMS:
            intake = pd.read_csv(INTAKE_ITEMS[name]); intake["날짜"] = pd.to_datetime(intake["날짜"])
            icol = [c for c in intake.columns if c != "날짜"][0]
            df = pd.merge(df, intake, on="날짜", how="left").sort_values("날짜").reset_index(drop=True)
            df[icol] = df[icol].ffill().bfill()
            for lag in [7, 14, 30]:
                n = f"intake_lag{lag}"; df[n] = df[icol].shift(lag); feats.append(n)
            for win in [7, 14]:
                n = f"intake_ma{win}"; df[n] = df[icol].shift(1).rolling(win).mean(); feats.append(n)

        mapes = {}
        for H in [7, 30]:
            d = df.copy()
            d["target"] = d["price"].shift(-H)
            d["target_month"] = (d["날짜"] + pd.Timedelta(days=H)).dt.month
            fcols = feats + ["target_month"]
            d = d.dropna(subset=fcols + ["target"]).reset_index(drop=True)
            X, y = d[fcols], d["target"]
            split = int(len(d) * 0.8)
            m = _make(); m.fit(X.iloc[:split], np.log1p(y.iloc[:split]))
            mapes[H] = round(mean_absolute_percentage_error(y.iloc[split:], np.expm1(m.predict(X.iloc[split:]))) * 100, 1)
            final = _make(); final.fit(X, np.log1p(y))
            joblib.dump({"model": final, "features": fcols, "horizon": H, "log_target": True,
                         "item": name, "code": code, "updated": str(date.today())},
                        os.path.join(DIR, f"model_{code}_h{H}.pkl"))
        summary[name] = mapes
    latest = str(veg["날짜"].max().date())
    return summary, latest


def main():
    log("===== 재학습 파이프라인 시작 =====")
    incremental_weather()
    incremental_veg()
    incremental_intake()
    summary, latest = retrain_all()
    perf = " | ".join(f"{n} H7:{m[7]}% H30:{m[30]}%" for n, m in summary.items())
    log(f"재학습 완료. 데이터 최신일 {latest} | {perf}")
    log("===== 종료 =====\n")


if __name__ == "__main__":
    main()
