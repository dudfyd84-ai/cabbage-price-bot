# 매일 최신 데이터를 증분 수집하고 채소·과일 11품목 소매가 예측 모델(H7/H30)을 재학습하는 자동화 파이프라인
import os
import ssl
import json
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
VEG = os.path.join(DIR, "kamis_veg_retail.csv")  # 소매(체감) 기준
INTAKE = os.path.join(DIR, "garak_cabbage_intake.csv")
LOG = os.path.join(DIR, "retrain_log.txt")

ASOS_KEY = os.getenv("ASOS_KEY", "")
KAMIS_KEY = os.getenv("KAMIS_KEY", "")
KAMIS_ID = os.getenv("KAMIS_ID", "")
STATIONS = {108: "서울", 159: "부산", 143: "대구", 156: "광주", 133: "대전"}
ITEMS = {"211": "배추", "231": "무", "245": "양파", "246": "대파", "258": "마늘",
         "232": "당근", "223": "오이", "213": "시금치", "214": "상추",
         "411": "사과", "412": "배"}  # code: name
CAT_OF = {c: ("400" if c in ("411", "412") else "200") for c in ITEMS}
CATS = ["200", "400"]
INTAKE_ITEMS = {"배추": INTAKE}
ALL_RETAIL = os.path.join(DIR, "kamis_all_retail.csv")   # 전 품목(농축수산) 일별 시세
ALL_CATS = {"100": "식량", "200": "채소", "400": "과일", "500": "축산", "600": "수산"}

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
    # dailyPriceByCategoryList로 채소·과일 11품목 서울 소매가 증분 수집 (체감 기준)
    df = pd.read_csv(VEG)
    last = pd.to_datetime(df["날짜"]).max().date()
    start, end = last + timedelta(days=1), date.today() - timedelta(days=1)
    days = list(weekdays(start, end))
    if not days:
        log(f"채소가격 최신 ({last}). 추가 없음."); return 0
    rows = []
    for d in days:
        for cat in CATS:
            try:
                r = _kamis.get(KAMIS_URL, params={"action": "dailyPriceByCategoryList", "p_product_cls_code": "01",
                                                  "p_item_category_code": cat, "p_country_code": "1101",
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
                    if code in ITEMS and CAT_OF[code] == cat and code not in seen:
                        raw = str(it.get("dpr1", "")).replace(",", "").strip()
                        if raw not in ("", "-"):
                            try:
                                rows.append({"날짜": d.isoformat(), "품목명": ITEMS[code],
                                             "단위": it.get("unit", ""), "가격": int(raw)})
                                seen.add(code)
                            except ValueError:
                                pass
            except Exception as e:
                log(f"  채소가격 {d} {cat} 실패: {e}")
            time.sleep(0.2)
    if rows:
        pd.concat([df, pd.DataFrame(rows)], ignore_index=True).to_csv(VEG, index=False, encoding="utf-8-sig")
    log(f"채소가격 {start}~{end} 추가 {len(rows)}행.")
    return len(rows)


def incremental_all_retail():
    # 농축수산 전 품목 소매가 증분 수집 (BOM 원가·예측 확장용 히스토리 축적)
    if not os.path.exists(ALL_RETAIL):
        log("전품목 시세 파일 없음(백필 전). 건너뜀."); return 0
    df = pd.read_csv(ALL_RETAIL, dtype={"품목코드": str})
    last = pd.to_datetime(df["날짜"]).max().date()
    start, end = last + timedelta(days=1), date.today() - timedelta(days=1)
    days = list(weekdays(start, end))
    if not days:
        log(f"전품목 시세 최신 ({last}). 추가 없음."); return 0
    rows = []
    for d in days:
        for cat, gname in ALL_CATS.items():
            try:
                r = _kamis.get(KAMIS_URL, params={"action": "dailyPriceByCategoryList", "p_product_cls_code": "01",
                                                  "p_item_category_code": cat, "p_country_code": "1101",
                                                  "p_regday": d.isoformat(), "p_convert_kg_yn": "Y",
                                                  "p_cert_key": KAMIS_KEY, "p_cert_id": KAMIS_ID, "p_returntype": "json"},
                               timeout=(8, 15), verify=False)
                data = r.json().get("data", {})
                its = data.get("item", []) if isinstance(data, dict) else []
                if isinstance(its, dict):
                    its = [its]
                seen = set()
                for it in its:
                    code = str(it.get("item_code", ""))
                    raw = str(it.get("dpr1", "")).replace(",", "").strip()
                    if not code or code in seen or raw in ("", "-"):
                        continue
                    try:
                        price = int(raw)
                    except ValueError:
                        continue
                    if price <= 0:
                        continue
                    seen.add(code)
                    rows.append({"날짜": d.isoformat(), "부류": gname, "품목코드": code,
                                 "품목명": it.get("item_name", ""), "단위": it.get("unit", ""), "가격": price})
            except Exception as e:
                log(f"  전품목 {d} {cat} 실패: {e}")
            time.sleep(0.15)
    if rows:
        pd.concat([df, pd.DataFrame(rows)], ignore_index=True).to_csv(ALL_RETAIL, index=False, encoding="utf-8-sig")
    log(f"전품목 시세 {start}~{end} 추가 {len(rows)}행.")
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
    summary, acc_items = {}, {}
    for code, name in ITEMS.items():
        sub = veg[veg["품목명"] == name]
        p = sub[["날짜", "가격"]].rename(columns={"가격": "price"}).sort_values("날짜")
        if len(p) < 200:
            log(f"  {name}: 데이터 부족, 건너뜀"); continue
        unit = sub["단위"].mode().iloc[0] if "단위" in sub.columns and len(sub) else ""
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
            pred = np.expm1(m.predict(X.iloc[split:]))
            act = y.iloc[split:].values
            now = d["price"].iloc[split:].values                       # 예측 시점 현재가
            mapes[H] = round(mean_absolute_percentage_error(act, pred) * 100, 1)
            wape = round(np.abs(act - pred).sum() / np.abs(act).sum() * 100, 1)
            dir_ok = int((np.sign(pred - now) == np.sign(act - now)).sum())
            acc_items.setdefault(name, {})[f"h{H}"] = {
                "n": len(act), "wape": wape, "mape": mapes[H],
                "dir_acc": round(dir_ok / len(act) * 100) if len(act) else 0,
                "period": [str(d["날짜"].iloc[split].date()), str(d["날짜"].iloc[-1].date())]}
            final = _make(); final.fit(X, np.log1p(y))
            joblib.dump({"model": final, "features": fcols, "horizon": H, "log_target": True,
                         "item": name, "code": code, "unit": unit, "updated": str(date.today())},
                        os.path.join(DIR, f"model_{code}_h{H}.pkl"))
        summary[name] = mapes
    latest = str(veg["날짜"].max().date())
    _write_accuracy(acc_items, latest)
    return summary, latest


def _write_accuracy(acc_items, latest):
    # 품목별 out-of-sample 백테스트 성능을 accuracy.json으로 저장 (전체 가중집계 포함)
    overall = {}
    for H in ("h7", "h30"):
        rows = [v[H] for v in acc_items.values() if H in v]
        if not rows:
            continue
        tot_n = sum(r["n"] for r in rows)
        overall[H] = {
            "n": tot_n,
            "wape": round(sum(r["wape"] * r["n"] for r in rows) / tot_n, 1),
            "mape": round(sum(r["mape"] * r["n"] for r in rows) / tot_n, 1),
            "dir_acc": round(sum(r["dir_acc"] * r["n"] for r in rows) / tot_n)}
    with open(os.path.join(DIR, "accuracy.json"), "w", encoding="utf-8") as f:
        json.dump({"generated": str(date.today()), "data_latest": latest,
                   "overall": overall, "items": acc_items}, f, ensure_ascii=False, indent=1)


def main():
    log("===== 재학습 파이프라인 시작 =====")
    incremental_weather()
    incremental_veg()
    incremental_all_retail()
    incremental_intake()
    summary, latest = retrain_all()
    perf = " | ".join(f"{n} H7:{m[7]}% H30:{m[30]}%" for n, m in summary.items())
    log(f"재학습 완료. 데이터 최신일 {latest} | {perf}")
    log("===== 종료 =====\n")


if __name__ == "__main__":
    main()
