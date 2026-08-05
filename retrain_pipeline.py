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
# 고변동 확장 품목 — 가격은 kamis_all_retail.csv에서 조달(자체 수집 불필요)
EXTRA_ITEMS = {"619": "물오징어", "224": "호박", "225": "토마토", "233": "열무",
               "256": "파프리카", "255": "피망", "215": "얼갈이배추", "280": "브로콜리"}
ITEMS.update(EXTRA_ITEMS)
CAT_OF = {c: ("400" if c in ("411", "412") else "200") for c in ITEMS}
CATS = ["200", "400"]
INTAKE_ITEMS = {"배추": INTAKE}
ALL_RETAIL = os.path.join(DIR, "kamis_all_retail.csv")   # 전 품목(농축수산) 일별 시세
# 서울 외 지역 소매가. 서울은 VEG에 이미 있어 중복 저장하지 않는다(#6).
REGION_RETAIL = os.path.join(DIR, "kamis_region_retail.csv")
ALL_CATS = {"100": "식량", "200": "채소", "400": "과일", "500": "축산", "600": "수산"}

GARAK_URL = "http://www.garak.co.kr/homepage/publicdata/dataJsonOpen.do"
GARAK_BASE = {"id": os.getenv("GARAK_ID", ""), "passwd": os.getenv("GARAK_PASSWD", ""), "dataid": "data22",
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


# 한국 공공 API(KAMIS·ASOS)는 GitHub Actions의 해외 IP에서 차단·타임아웃된다.
# COLLECT_URL이 설정되면 국내 리전에 떠 있는 라이브 서버에 수집을 대신 요청한다.
COLLECT_URL = os.getenv("COLLECT_URL", "")
COLLECT_TOKEN = os.getenv("COLLECT_TOKEN", "")


def _remote_rows(kind, start, end, country="1101"):
    # 라이브 서버(/api/collect)에 수집을 위임해 행 목록만 받아온다.
    r = requests.get(COLLECT_URL, params={"kind": kind, "start": start.isoformat(),
                                          "end": end.isoformat(), "country": country},
                     headers={"X-Collect-Token": COLLECT_TOKEN}, timeout=300)
    r.raise_for_status()
    return r.json().get("rows", [])


def fetch_weather_rows(start, end):
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
    return rows


# KAMIS 소매 조사 지역 코드. 서울(1101)이 기본이고 나머지는 지역 확장(#6) 검증용이다.
REGION_CODES = {"서울": "1101", "부산": "2100", "대구": "2200", "광주": "2401", "대전": "2501"}


def fetch_veg_rows(days, country="1101"):
    rows = []
    for d in days:
        for cat in CATS:
            try:
                r = _kamis.get(KAMIS_URL, params={"action": "dailyPriceByCategoryList", "p_product_cls_code": "01",
                                                  "p_item_category_code": cat, "p_country_code": country,
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
    return rows


def incremental_weather():
    df = pd.read_csv(WEATHER)
    last = pd.to_datetime(df["날짜"]).max().date()
    start, end = last + timedelta(days=1), date.today() - timedelta(days=1)
    if start > end:
        log(f"날씨 최신 ({last}). 추가 없음."); return 0
    rows = _remote_rows("weather", start, end) if COLLECT_URL else fetch_weather_rows(start, end)
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
    rows = _remote_rows("veg", start, end) if COLLECT_URL else fetch_veg_rows(days)
    if rows:
        pd.concat([df, pd.DataFrame(rows)], ignore_index=True).to_csv(VEG, index=False, encoding="utf-8-sig")
    log(f"채소가격 {start}~{end} 추가 {len(rows)}행.")
    return len(rows)


def collect_region(start, end, regions=None):
    # 서울 외 지역 소매가를 수집해 kamis_region_retail.csv에 누적한다.
    # 백필·증분 겸용이며 (날짜, 지역, 품목명) 기준으로 중복을 제거해 재실행에 안전하다.
    regions = regions or {k: v for k, v in REGION_CODES.items() if k != "서울"}
    old = pd.read_csv(REGION_RETAIL) if os.path.exists(REGION_RETAIL) else         pd.DataFrame(columns=["날짜", "지역", "품목명", "단위", "가격"])
    days = list(weekdays(start, end))
    if not days:
        log("지역 시세: 대상 평일 없음."); return 0

    added = []
    for rname, code in regions.items():
        # /api/collect는 한 요청당 60일로 제한된다. 그보다 짧게 끊어야 타임아웃도 피한다.
        for i in range(0, len(days), 30):
            chunk = days[i:i + 30]
            s_dt, e_dt = chunk[0], chunk[-1]
            rows = _remote_rows("veg", s_dt, e_dt, code) if COLLECT_URL else fetch_veg_rows(chunk, code)
            for r in rows:
                added.append({"날짜": r["날짜"], "지역": rname, "품목명": r["품목명"],
                              "단위": r["단위"], "가격": r["가격"]})
            log(f"  {rname} {s_dt}~{e_dt} {len(rows)}행")

    if not added:
        log("지역 시세: 추가 없음."); return 0
    df = pd.concat([old, pd.DataFrame(added)], ignore_index=True)
    df = df.drop_duplicates(subset=["날짜", "지역", "품목명"], keep="last")
    df.to_csv(REGION_RETAIL, index=False, encoding="utf-8-sig")
    log(f"지역 시세 {start}~{end} 누적 {len(df)}행 (이번 {len(added)}행)")
    return len(added)


def incremental_region():
    # 지역 시세 증분. 파일이 없으면 백필 전이므로 건너뛴다(백필은 region_backfill.py로 따로 돌린다).
    if not os.path.exists(REGION_RETAIL):
        log("지역 시세 파일 없음 — 백필 전이라 건너뜀."); return 0
    df = pd.read_csv(REGION_RETAIL)
    last = pd.to_datetime(df["날짜"]).max().date()
    return collect_region(last + timedelta(days=1), date.today() - timedelta(days=1))


def fetch_all_retail_rows(days, country="1101"):
    rows = []
    for d in days:
        for cat, gname in ALL_CATS.items():
            try:
                r = _kamis.get(KAMIS_URL, params={"action": "dailyPriceByCategoryList", "p_product_cls_code": "01",
                                                  "p_item_category_code": cat, "p_country_code": country,
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
    return rows


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
    rows = _remote_rows("all_retail", start, end) if COLLECT_URL else fetch_all_retail_rows(days)
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


# 예측 구간용 분위수(10%/90%) 모델. 한 모델이 두 분위수를 동시에 내므로 학습 비용이 절반이다.
QUANTILES = [0.1, 0.9]
NOMINAL = 80          # 목표 포함률(%)


def _make_q():
    return XGBRegressor(objective="reg:quantileerror", quantile_alpha=QUANTILES,
                        n_estimators=300, max_depth=4, learning_rate=0.05,
                        subsample=0.8, colsample_bytree=0.8, random_state=42)


def _qbounds(model, X):
    # 다중 분위수 출력(n,2)을 로그 역변환해 (하한, 상한)으로 정렬해서 반환
    z = np.expm1(model.predict(X))
    return np.minimum(z[:, 0], z[:, 1]), np.maximum(z[:, 0], z[:, 1])


def _miscal(cov):
    # 보정 실패 점수. 포함률이 목표보다 '모자란' 쪽에 2배 벌점을 준다.
    # 구간이 넓어 과하게 담는 건 보수적일 뿐이지만, 모자라면 사용자가 범위를 믿고 틀린다.
    return (NOMINAL - cov) if cov < NOMINAL else (cov - NOMINAL) * 0.5


def _conformal_q(lo, hi, y):
    # 컨포멀 보정폭. 분위수 회귀만 쓰면 구간이 과하게 좁아 실제 포함률이 50%대로 떨어진다(검증됨).
    # 보정셋에서 구간 밖으로 벗어난 정도의 80% 분위수를 구해 양끝을 그만큼 넓힌다(CQR).
    e = np.maximum(lo - y, y - hi)
    k = min(1.0, np.ceil((len(e) + 1) * NOMINAL / 100) / len(e))
    return float(np.quantile(e, k))


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
    veg = pd.concat([veg, _extra_prices()], ignore_index=True)   # 확장 품목 가격 합류
    summary, acc_items, pred_rows, intervals = {}, {}, [], {}
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
            # ── 예측 구간(CQR) 검증: 학습 0~60% / 보정 60~80% / 평가 80~100% ──
            # 로그 타깃에서도 분위수는 단조변환에 불변이라 expm1로 되돌리면 그대로 원가격 분위수다.
            cal = int(len(d) * 0.6)
            qv = _make_q(); qv.fit(X.iloc[:cal], np.log1p(y.iloc[:cal]))
            lc, hc = _qbounds(qv, X.iloc[cal:split])
            Qv = _conformal_q(lc, hc, y.iloc[cal:split].values)
            lo_h, hi_h = _qbounds(qv, X.iloc[split:])
            lo_h, hi_h = lo_h - Qv, hi_h + Qv
            cov_q = round(float(((act >= lo_h) & (act <= hi_h)).mean()) * 100)
            mp = mapes[H] / 100                                        # 기존 근사: 예측치 ±MAPE
            cov_m = round(float(((act >= pred * (1 - mp)) & (act <= pred * (1 + mp))).mean()) * 100)

            final = _make(); final.fit(X, np.log1p(y))
            joblib.dump({"model": final, "features": fcols, "horizon": H, "log_target": True,
                         "item": name, "code": code, "unit": unit, "updated": str(date.today())},
                        os.path.join(DIR, f"model_{code}_h{H}.pkl"))

            # 오늘자 예측 기록: 최신 피처 행으로 D+H 예측 (target 불필요, predict_item과 동일 방식)
            dp = df.copy()
            dp["target_month"] = (dp["날짜"] + pd.Timedelta(days=H)).dt.month
            dp = dp.dropna(subset=fcols)
            if len(dp):
                yhat = float(np.expm1(final.predict(dp[fcols].iloc[[-1]])[0]))
                # 예측일은 '가격 데이터 기준일'이어야 한다. dp의 마지막 날짜는 날씨 기준이라,
                # 가격 수집이 밀리면(ffill) 실제로는 옛 가격으로 낸 예측이 최신 날짜로 기록돼
                # 실전 적중률이 오염된다(2026-07 수집 중단 때 실제로 발생).
                pdate = p["날짜"].max()
                pred_rows.append({
                    "예측일": str(pdate.date()), "품목": name, "호라이즌": H,
                    "목표일": str((pdate + pd.Timedelta(days=H)).date()),
                    "현재가": round(float(dp["price"].iloc[-1])), "예측가": round(yhat)})

                # 실제 서비스용 구간: 학습 0~80% / 보정은 가장 최근 20%(현 시세 국면 반영).
                # 구간은 '예측치 대비 비율'로 저장한다. 절대값으로 두면 재학습이 하루 밀렸을 때
                # 예측치만 갱신되고 구간은 옛 가격에 묶여 어긋난다.
                qf = _make_q(); qf.fit(X.iloc[:split], np.log1p(y.iloc[:split]))
                lf, hf = _qbounds(qf, X.iloc[split:])
                Qf = _conformal_q(lf, hf, y.iloc[split:].values)
                lo_t, hi_t = _qbounds(qf, dp[fcols].iloc[[-1]])
                lo, hi = float(lo_t[0]) - Qf, float(hi_t[0]) + Qf
                # 품목별로 홀드아웃 포함률이 목표에 더 가까운 쪽을 채택한다.
                # CQR이 항상 이기지는 않는다. 변동성이 큰 품목(파프리카·호박)에선 구간이
                # 예측치의 5배까지 벌어지면서 오히려 포함률이 떨어졌다.
                use_q = _miscal(cov_q) <= _miscal(cov_m)
                if yhat > 0 and lo < hi:
                    if use_q:
                        r_lo, r_hi = min(lo / yhat, 0.99), max(hi / yhat, 1.01)
                    else:
                        r_lo, r_hi = 1 - mapes[H] / 100, 1 + mapes[H] / 100
                    intervals.setdefault(name, {})[f"h{H}"] = {
                        "lo": round(r_lo, 4), "hi": round(r_hi, 4),
                        "method": "CQR" if use_q else "MAPE",
                        "coverage": cov_q if use_q else cov_m,
                        "coverage_cqr": cov_q, "coverage_mape": cov_m, "n": len(act)}
        summary[name] = mapes
    latest = str(veg["날짜"].max().date())
    _log_predictions(pred_rows)
    _write_intervals(intervals, latest)
    _write_accuracy(acc_items, latest, _live_accuracy(veg))
    return summary, latest


def _write_intervals(intervals, latest):
    # 품목·호라이즌별 80% 예측 구간 비율을 intervals.json에 기록 (app.py가 ci7/ci30 산출에 사용)
    if not intervals:
        return
    vals = [v for it in intervals.values() for v in it.values()]
    covs = [v["coverage"] for v in vals]
    cms = [v["coverage_mape"] for v in vals]
    n_q = sum(1 for v in vals if v["method"] == "CQR")
    doc = {"updated": latest, "quantiles": QUANTILES, "nominal": NOMINAL,
           "method": "CQR+MAPE", "cqr_picked": f"{n_q}/{len(vals)}",
           "coverage_avg": round(sum(covs) / len(covs)),
           "coverage_mape_avg": round(sum(cms) / len(cms)),
           "items": intervals}
    with open(os.path.join(DIR, "intervals.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    log(f"예측 구간 갱신: 채택 포함률 {doc['coverage_avg']}% vs 기존 근사 {doc['coverage_mape_avg']}% "
        f"(목표 {NOMINAL}%, CQR 채택 {doc['cqr_picked']})")


def _extra_prices():
    # 확장 품목(EXTRA_ITEMS) 가격을 전 품목 시세 CSV에서 가져와 veg와 같은 스키마로 반환
    if not os.path.exists(ALL_RETAIL):
        log("전품목 시세 파일 없음 — 확장 품목 건너뜀")
        return pd.DataFrame(columns=["날짜", "품목명", "가격", "단위"])
    a = pd.read_csv(ALL_RETAIL, dtype={"품목코드": str})
    a = a[a["품목명"].isin(EXTRA_ITEMS.values())].copy()
    a["날짜"] = pd.to_datetime(a["날짜"])
    a = a.drop_duplicates(subset=["날짜", "품목명"], keep="last")
    log(f"확장 품목 {a['품목명'].nunique()}종 가격 {len(a)}행 합류")
    return a[["날짜", "품목명", "가격", "단위"]]


def _log_predictions(rows):
    # 매일 낸 D+7/D+30 예측을 predict_log.csv에 누적 (예측일·품목·호라이즌 유일)
    if not rows:
        return 0
    path = os.path.join(DIR, "predict_log.csv")
    new = pd.DataFrame(rows)
    if os.path.exists(path):
        old = pd.read_csv(path)
        new = pd.concat([old, new], ignore_index=True)
    new = new.drop_duplicates(subset=["예측일", "품목", "호라이즌"], keep="last")
    new.to_csv(path, index=False, encoding="utf-8-sig")
    log(f"예측 로그 적재: 누적 {len(new)}행")
    return len(new)


def _live_accuracy(veg, window=90):
    # 만기(목표일 도래) 예측을 실측과 대조해 실전 WAPE·방향적중률 산출
    path = os.path.join(DIR, "predict_log.csv")
    if not os.path.exists(path):
        return None
    lg = pd.read_csv(path)
    if lg.empty:
        return None
    latest = veg["날짜"].max()
    lg["목표일_dt"] = pd.to_datetime(lg["목표일"])
    matured = lg[lg["목표일_dt"] <= latest]
    matured = matured[matured["목표일_dt"] >= latest - pd.Timedelta(days=window)]
    if matured.empty:
        first = pd.to_datetime(lg["목표일"]).min()
        days = max(0, (first - latest).days)
        return {"status": "집계중", "n": 0, "next_days": days}
    look = veg.rename(columns={"품목명": "품목", "날짜": "목표일_dt", "가격": "실측가"})
    m = matured.merge(look[["품목", "목표일_dt", "실측가"]], on=["품목", "목표일_dt"], how="left").dropna(subset=["실측가"])

    # 가격 수집이 밀린 날 만든 예측은 평가에서 제외한다.
    # 기록된 '현재가'가 그날 실측과 다르면 = 옛 가격(ffill)으로 낸 예측이므로 공정한 측정이 아니다.
    # (2026-07 수집 중단 때 3주치가 옛 가격 기준으로 쌓여 실전 오차가 4배로 부풀었다.)
    cur_look = veg.rename(columns={"품목명": "품목", "날짜": "예측일_dt", "가격": "기준일_실측가"})
    m["예측일_dt"] = pd.to_datetime(m["예측일"])
    m = m.merge(cur_look[["품목", "예측일_dt", "기준일_실측가"]], on=["품목", "예측일_dt"], how="left")
    stale = m["기준일_실측가"].isna() | ((m["현재가"] - m["기준일_실측가"]).abs() > 1)
    if stale.any():
        log(f"실전 적중률: 가격 지연 기간 예측 {int(stale.sum())}건 제외")
    m = m[~stale]
    if m.empty:
        return {"status": "집계중", "n": 0, "reason": "유효 성숙분 없음"}
    items = {}
    for (item, H), g in m.groupby(["품목", "호라이즌"]):
        act, pred, now = g["실측가"].values, g["예측가"].values, g["현재가"].values
        items.setdefault(item, {})[f"h{int(H)}"] = {
            "n": len(g),
            "wape": round(np.abs(act - pred).sum() / np.abs(act).sum() * 100, 1),
            "dir_acc": round((np.sign(pred - now) == np.sign(act - now)).mean() * 100)}
    overall = {}
    for H in ("h7", "h30"):
        rs = [v[H] for v in items.values() if H in v]
        if not rs:
            continue
        tot = sum(r["n"] for r in rs)
        overall[H] = {"n": tot,
                      "wape": round(sum(r["wape"] * r["n"] for r in rs) / tot, 1),
                      "dir_acc": round(sum(r["dir_acc"] * r["n"] for r in rs) / tot)}
    return {"status": "집계됨", "overall": overall, "items": items,
            "window_days": window, "as_of": str(latest.date())}


def _write_accuracy(acc_items, latest, live=None):
    # 품목별 out-of-sample 백테스트 성능 + 실전(live) 성능을 accuracy.json으로 저장
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
                   "overall": overall, "items": acc_items, "live": live},
                  f, ensure_ascii=False, indent=1)


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
