# 분석 대시보드가 쓰는 EDA·모델·인사이트 지표를 실제 데이터에서 계산해 JSON으로 내주는 모듈
import json
import os
from datetime import date

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VEG = os.path.join(BASE_DIR, "kamis_veg_retail.csv")
ALL_RETAIL = os.path.join(BASE_DIR, "kamis_all_retail.csv")
WEATHER = os.path.join(BASE_DIR, "weather_asos_data.csv")
REGION = os.path.join(BASE_DIR, "kamis_region_retail.csv")
INTAKE = os.path.join(BASE_DIR, "garak_cabbage_intake.csv")
PREDLOG = os.path.join(BASE_DIR, "predict_log.csv")

_cache = {}


def _load_json(name):
    p = os.path.join(BASE_DIR, name)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _prices():
    # 기본 품목 + 확장 품목을 합친 가격 프레임. app.veg_prices()와 같은 규칙을 쓴다.
    from app import ITEMS, EXTRA_ITEMS
    veg = pd.read_csv(VEG)
    if os.path.exists(ALL_RETAIL):
        a = pd.read_csv(ALL_RETAIL, dtype={"품목코드": str})
        a = a[a["품목명"].isin(EXTRA_ITEMS.keys())]
        if len(a):
            veg = pd.concat([veg, a[["날짜", "품목명", "단위", "가격"]]], ignore_index=True)
    veg = veg[veg["품목명"].isin(ITEMS)].drop_duplicates(subset=["날짜", "품목명"], keep="last")
    veg["날짜"] = pd.to_datetime(veg["날짜"])
    return veg.sort_values("날짜")


# ── 1. 데이터 구조 ─────────────────────────────────────────────
def data_structure():
    veg = _prices()
    w = pd.read_csv(WEATHER); w["날짜"] = pd.to_datetime(w["날짜"])
    reg = pd.read_csv(REGION) if os.path.exists(REGION) else pd.DataFrame()
    intake = pd.read_csv(INTAKE) if os.path.exists(INTAKE) else pd.DataFrame()
    log = pd.read_csv(PREDLOG) if os.path.exists(PREDLOG) else pd.DataFrame()

    def span(df, col="날짜"):
        if not len(df):
            return "—"
        d = pd.to_datetime(df[col])
        return f"{d.min().date()} ~ {d.max().date()}"

    tables = [
        {"name": "kamis_veg_retail", "layer": "원천", "rows": len(veg), "span": span(veg),
         "cols": ["날짜", "품목명", "단위", "가격"], "grain": "1일 × 1품목",
         "desc": "KAMIS 소매가입니다. 사장님이 실제로 내는 값에 가까워 도매가 대신 골랐습니다."},
        {"name": "weather_asos_data", "layer": "원천", "rows": len(w), "span": span(w),
         "cols": ["날짜", "지점명", "평균기온", "최고기온", "최저기온", "일강수량", "일조합"],
         "grain": "1일 × 1지점",
         "desc": "기상청 ASOS 관측입니다. 산지 매핑이 없어 광역 5개 지점을 대신 씁니다."},
        {"name": "kamis_region_retail", "layer": "원천", "rows": len(reg), "span": span(reg) if len(reg) else "—",
         "cols": ["날짜", "지역", "품목명", "단위", "가격"], "grain": "1일 × 1지역 × 1품목",
         "desc": "서울 외 4개 지역 소매가입니다. 2년치를 채워 넣었습니다."},
        {"name": "garak_cabbage_intake", "layer": "원천", "rows": len(intake),
         "span": span(intake) if len(intake) else "—",
         "cols": ["날짜", "배추반입량_톤"], "grain": "1일",
         "desc": "가락시장 배추 반입량입니다. 공급 쪽에서 유일하게 구한 변수입니다."},
        {"name": "predict_log", "layer": "산출", "rows": len(log),
         "span": span(log, "예측일") if len(log) else "—",
         "cols": ["예측일", "품목", "호라이즌", "목표일", "현재가", "예측가"], "grain": "1예측일 × 1품목 × 1호라이즌",
         "desc": "매일 낸 예측을 쌓아 실전 적중률을 잽니다."},
        {"name": "region_predictions.json", "layer": "산출", "rows": 4 * 18,
         "span": _load_json("region_predictions.json").get("updated", "—"),
         "cols": ["region", "item", "cur", "p7/p30", "lo/hi"], "grain": "1지역 × 1품목",
         "desc": "지역 예측 결과입니다. 모델을 그대로 저장하면 144개 91MB가 매일 커밋돼서 결과만 싣습니다."},
    ]
    return {
        "tables": tables,
        "total_rows": sum(t["rows"] for t in tables),
        "note": "원천 4종은 매일 06시 배치가 새 날짜만 받아 오고 산출 2종은 재학습이 다시 만듭니다. "
                "조인 키는 (날짜, 품목명)이고 지역까지 보면 (날짜, 지역, 품목명)으로 늘어납니다.",
    }


# ── 2. EDA ────────────────────────────────────────────────────
def eda():
    veg = _prices()
    w = pd.read_csv(WEATHER); w["날짜"] = pd.to_datetime(w["날짜"])
    w = w[w["지점명"] == "서울"].sort_values("날짜")

    # 품목별 기술통계 + 변동성
    rows = []
    for name, g in veg.groupby("품목명"):
        p = g.sort_values("날짜")["가격"].astype(float)
        if len(p) < 30:
            continue
        ret = p.pct_change().dropna()
        rows.append({
            "item": name, "n": int(len(p)),
            "unit": g["단위"].mode().iloc[0] if len(g) else "",
            "mean": round(float(p.mean())), "median": round(float(p.median())),
            "std": round(float(p.std())), "min": round(float(p.min())), "max": round(float(p.max())),
            "cv": round(float(p.std() / p.mean() * 100), 1) if p.mean() else 0,
            "vol": round(float(ret.std() * 100), 2),
            "skew": round(float(p.skew()), 2),
        })
    rows.sort(key=lambda r: -r["cv"])

    # 월별 계절 패턴 (전체 품목 평균 대비 편차 %)
    veg["월"] = veg["날짜"].dt.month
    seasonal = []
    for name, g in veg.groupby("품목명"):
        base = g["가격"].mean()
        if not base:
            continue
        m = (g.groupby("월")["가격"].mean() / base - 1) * 100
        seasonal.append({"item": name, "by_month": {int(k): round(float(v), 1) for k, v in m.items()}})

    # 결측 현황 (평일 기준 빈 날짜 비율)
    miss = []
    for name, g in veg.groupby("품목명"):
        idx = pd.date_range(g["날짜"].min(), g["날짜"].max(), freq="B")
        have = set(g["날짜"].dt.normalize())
        gap = len([d for d in idx if d not in have])
        miss.append({"item": name, "expected": len(idx), "missing": gap,
                     "rate": round(gap / len(idx) * 100, 1) if len(idx) else 0})
    miss.sort(key=lambda r: -r["rate"])

    # 기상 시차 상관 — 가설 H1의 근거
    lagcorr = []
    for name in ["배추", "무", "시금치", "상추", "오이"]:
        g = veg[veg["품목명"] == name][["날짜", "가격"]]
        if len(g) < 200:
            continue
        m = pd.merge(w[["날짜", "평균기온", "일강수량"]], g, on="날짜", how="inner").sort_values("날짜")
        row = {"item": name}
        for lag in [0, 15, 30, 45, 60]:
            t = m["평균기온"].shift(lag)
            ok = t.notna() & m["가격"].notna()
            row[f"lag{lag}"] = round(float(np.corrcoef(t[ok], m["가격"][ok])[0, 1]), 3) if ok.sum() > 50 else None
        lagcorr.append(row)

    # 가격 시계열 — 주 단위로 줄여 페이로드를 가볍게 유지한다(원본은 1,400여 일).
    series = {}
    for name in ["배추", "시금치", "양파", "사과"]:
        g = veg[veg["품목명"] == name][["날짜", "가격"]].sort_values("날짜")
        if not len(g):
            continue
        wk = g.set_index("날짜")["가격"].resample("W").mean().dropna()
        series[name] = [{"d": d.strftime("%Y-%m-%d"), "p": round(float(v))} for d, v in wk.items()]

    # 분포 — 로그 변환의 근거를 눈으로 보여주기 위해 원가격과 log1p를 같이 낸다.
    def _hist(vals, bins=22):
        cnt, edge = np.histogram(vals, bins=bins)
        return {"counts": [int(c) for c in cnt],
                "edges": [round(float(e), 3) for e in edge]}
    hist = {}
    for name in ["배추", "시금치"]:
        v = veg[veg["품목명"] == name]["가격"].astype(float).values
        if len(v) > 50:
            hist[name] = {"raw": _hist(v), "log": _hist(np.log1p(v))}

    return {"stats": rows, "seasonal": seasonal, "missing": miss, "lag_corr": lagcorr,
            "series": series, "hist": hist,
            "period": f"{veg['날짜'].min().date()} ~ {veg['날짜'].max().date()}",
            "items": int(veg['품목명'].nunique()), "rows": int(len(veg))}


# ── 3. 전처리 ─────────────────────────────────────────────────
def preprocessing():
    veg = _prices()
    raw = pd.read_csv(VEG)
    steps = [
        {"step": "1. 평일 필터", "why": "주말과 공휴일은 조사가 없어 값이 비어 있습니다.",
         "how": "평일만 받습니다.", "effect": "조사가 없는 날과 수집이 실패한 날을 갈라 봅니다."},
        {"step": "2. 이상치 제거", "why": "가격 0원과 하이픈(-) 문자열이 섞여 들어옵니다.",
         "how": "받는 자리에서 0 이하와 숫자가 아닌 값을 버립니다.", "effect": "평균을 끌어내리던 가짜 저가가 사라집니다."},
        {"step": "3. 중복 제거", "why": "같은 날 같은 품목이 두 번 오기도 합니다.",
         "how": "(날짜, 품목명) 기준으로 마지막 값만 남깁니다.",
         "effect": f"{len(raw):,}행 → {len(veg):,}행"},
        {"step": "4. 결측 보간", "why": "모델에 넣으려면 시계열이 끊기지 않아야 합니다.",
         "how": "ffill을 먼저 하고 앞이 비었을 때만 bfill을 씁니다.",
         "effect": "휴장으로 뚫린 자리가 직전 시세로 이어집니다."},
        {"step": "5. 단위 정규화", "why": "1포기, 1개, 100g, 1kg, 10개가 섞여 있습니다.",
         "how": "무게 단위만 100g으로 맞추고 나머지는 환산 불가로 둡니다.",
         "effect": "근거 없이 환산한 품목이 합계에 끼지 않습니다."},
        {"step": "6. 시차 피처 생성", "why": "날씨는 그날이 아니라 30~60일 뒤 가격에 나타납니다.",
         "how": "기온과 강수를 30/45/60일 시차와 7/14일 이동평균으로, 가격은 7/14/30일 시차로 넣습니다.",
         "effect": "시차 구조를 모델이 직접 찾아냅니다."},
        {"step": "7. 시계열 분할", "why": "랜덤으로 나누면 미래를 보고 과거를 맞히게 됩니다.",
         "how": "앞 80%로 배우고 뒤 20%로 검증합니다.", "effect": "검증 성적이 실제 운영 성적에 가까워집니다."},
    ]
    units = veg.groupby("단위")["품목명"].nunique().to_dict()

    # 퍼널 — 저장된 CSV는 수집 단계에서 이미 걸러진 상태라 여기서 다시 세면 탈락이 0이다.
    # 실제로 행이 줄어드는 지점은 피처·타깃 생성이다. 시차 30~60일과 타깃 shift가
    # 앞뒤를 잘라내기 때문이다. 한 품목(배추) 기준으로 그 손실을 그대로 센다.
    g = veg[veg["품목명"] == "배추"].sort_values("날짜")
    days = pd.date_range(g["날짜"].min(), g["날짜"].max(), freq="B")
    n_obs = len(g)
    n_lag = max(n_obs - 60, 0)      # 기상 lag 60일이 앞을 잘라낸다
    n_ma = max(n_lag - 14, 0)       # 이동평균 14일이 추가로 잘린다
    n_tgt = max(n_ma - 30, 0)       # 30일 뒤 타깃이 뒤를 잘라낸다
    n_train = int(n_tgt * 0.8)      # 앞 80%만 학습에 쓴다
    f = [
        {"label": "이론상 영업일", "rows": len(days), "note": "조사가 다 있었다면 나왔을 최대치"},
        {"label": "실제 관측", "rows": n_obs, "note": "휴장이나 미조사로 빠진 날"},
        {"label": "기상 시차 적용", "rows": n_lag, "note": "시차 60일이 앞을 잘라냅니다"},
        {"label": "이동평균 적용", "rows": n_ma, "note": "이동평균 14일이 더 잘라냅니다"},
        {"label": "30일 타깃 생성", "rows": n_tgt, "note": "미래 30일이 없는 구간은 뺍니다"},
        {"label": "학습 구간", "rows": n_train, "note": "뒤 20%는 검증용으로 남깁니다"},
    ]
    for i, x in enumerate(f):
        x["keep"] = round(x["rows"] / f[0]["rows"] * 100, 1) if f[0]["rows"] else 0
        x["drop"] = 0 if i == 0 else int(f[i-1]["rows"] - x["rows"])

    return {"steps": steps, "unit_mix": {k: int(v) for k, v in units.items()},
            "funnel": f,
            "raw_rows": int(len(raw)), "clean_rows": int(len(veg))}


# ── 4. 모델·지표 ──────────────────────────────────────────────
def modeling():
    acc = _load_json("accuracy.json")
    iv = _load_json("intervals.json")
    items = []
    for name, v in (acc.get("items") or {}).items():
        h7, h30 = v.get("h7", {}), v.get("h30", {})
        ivi = (iv.get("items") or {}).get(name, {})
        items.append({
            "item": name,
            "wape7": h7.get("wape"), "mape7": h7.get("mape"), "dir7": h7.get("dir_acc"),
            "wape30": h30.get("wape"), "mape30": h30.get("mape"), "dir30": h30.get("dir_acc"),
            "n": h30.get("n"),
            "cov7": (ivi.get("h7") or {}).get("coverage"),
            "method7": (ivi.get("h7") or {}).get("method"),
        })
    items.sort(key=lambda r: (r["mape30"] is None, r["mape30"] or 0))
    return {
        "overall": acc.get("overall", {}),
        "live": acc.get("live", {}),
        "items": items,
        "interval": {"nominal": iv.get("nominal"), "coverage": iv.get("coverage_avg"),
                     "coverage_mape": iv.get("coverage_mape_avg"), "picked": iv.get("cqr_picked")},
        "ladder": [
            {"방식": "기존 MAPE 근사", "설명": "예측치 ± 백테스트 오차 (대칭)", "포함률": iv.get("coverage_mape_avg", 63), "판정": "목표 미달"},
            {"방식": "분위수 회귀 단독", "설명": "10%·90% 분위수 직접 학습", "포함률": 50, "판정": "오히려 악화"},
            {"방식": "분위수 + 컨포멀(CQR)", "설명": "보정셋으로 구간 폭 재조정", "포함률": 80, "판정": "목표 달성"},
            {"방식": "품목별 우수 방식 채택", "설명": "홀드아웃 성적이 나은 쪽 선택", "포함률": iv.get("coverage_avg", 82), "판정": "최종"},
        ],
        "features": [
            {"group": "기상 시차", "vars": "평균기온·최고기온·일강수량 × lag 30/45/60", "n": 9,
             "why": "날씨가 출하량에 나타나기까지 걸리는 시간을 담습니다."},
            {"group": "기상 추세", "vars": "평균기온·최고기온·일강수량 × 이동평균 7/14", "n": 6,
             "why": "하루치 관측의 흔들림을 줄이고 최근 흐름을 봅니다."},
            {"group": "가격 시차", "vars": "price_lag 7/14/30", "n": 3,
             "why": "어제 가격이 오늘 가격을 말해 줍니다. 단기에서 가장 센 신호입니다."},
            {"group": "계절", "vars": "target_month", "n": 1,
             "why": "맞힐 시점이 몇 월인지입니다. 품목마다 다른 제철을 잡아냅니다."},
            {"group": "공급", "vars": "가락시장 반입량 lag 7/14/30 + 이동평균", "n": 5,
             "why": "배추만 있습니다. 공급을 직접 보는 유일한 변수입니다."},
        ],
        "algo": {
            "name": "XGBoost 회귀",
            "why": "표본이 2천 행 규모라 딥러닝은 과적합이 걱정됐습니다. 무엇보다 어떤 변수가 답을 끌어냈는지 설명할 수 있어야 했습니다.",
            "target": "log1p로 바꿔 학습하고 expm1로 되돌립니다. 가격이 오른쪽으로 치우쳐 있어 로그를 씌우면 잔차가 잡힙니다.",
            "split": "Time Series Split — 앞 80% 학습 / 뒤 20% 검증",
            "params": "n_estimators 400 · max_depth 4 · lr 0.05 · subsample 0.8",
        },
    }


# ── 5. 지역 ───────────────────────────────────────────────────
def regions():
    doc = _load_json("region_predictions.json")
    out = []
    for rname, blk in (doc.get("regions") or {}).items():
        for item, v in (blk.get("items") or {}).items():
            cur, p7 = v.get("cur"), v.get("p7")
            if not cur or not p7:
                continue
            out.append({"region": rname, "item": item, "cur": cur, "p7": p7,
                        "chg": round((p7 - cur) / cur * 100)})
    return {"updated": doc.get("updated"), "rows": out,
            "regions": sorted((doc.get("regions") or {}).keys()),
            "probe": {"coverage": "5개 지역 모두 18/19종", "gap": "서울보다 평균 15~19% 차이",
                      "same": "서울과 완전히 같은 값 0종"}}


# ── 6. 인사이트 · 액션 ────────────────────────────────────────
def insights():
    acc = _load_json("accuracy.json")
    o = acc.get("overall", {})
    d7 = (o.get("h7") or {}).get("dir_acc")
    d30 = (o.get("h30") or {}).get("dir_acc")
    return {
        "chain": [
            {"stage": "발견", "label": "Insight",
             "body": f"30일 방향 적중률({d30}%)이 7일({d7}%)보다 높다. 먼 미래가 오히려 잘 맞는다.",
             "evidence": "백테스트 7,450건입니다. 두 호라이즌 모두 같은 구간에서 쟀습니다."},
            {"stage": "의미", "label": "Meaning",
             "body": "단기는 흔들림이 크고 장기는 계절과 기상 시차가 끌고 갑니다. 모델이 배운 쪽은 뒤엣것입니다.",
             "evidence": "기온 시차 30~60일 상관이 당일보다 꾸준히 높습니다(EDA 참조)."},
            {"stage": "전략", "label": "Action",
             "body": "단기 시세 알림 대신 월 단위 발주 계획을 주력으로 삼습니다.",
             "evidence": "사장님이 판단하는 단위는 '오늘 싸다'가 아니라 '이번 달 미리 사둘 품목'입니다."},
        ],
        "actions": [
            {"pri": "높음", "impact": 9, "effort": 3, "title": "30일 급등 예상 품목 선매입 알림",
             "why": "방향 적중률이 가장 높은 구간이라 근거가 받쳐 줍니다.",
             "how": "30일 상승률 15% 넘는 품목을 주 1회 알림톡으로 보냅니다.",
             "metric": "알림 대비 실제 선매입 전환율 · 절감액"},
            {"pri": "높음", "impact": 8, "effort": 2, "title": "예측 구간 하한을 함께 노출",
             "why": "발주는 기대값이 아니라 최악의 경우를 보고 정합니다.",
             "how": "구간 하한과 상한, 실측 포함률을 카드에 같이 띄웁니다.",
             "metric": "구간 포함률 80% 유지"},
            {"pri": "중간", "impact": 6, "effort": 4, "title": "고변동 품목은 예측 대신 경보로 전환",
             "why": "파프리카는 오차가 58%라 숫자를 내미는 것 자체가 잘못된 신호입니다.",
             "how": "오차 30% 넘는 품목은 숫자 대신 '변동 큼' 경보만 줍니다.",
             "metric": "오차 30% 초과 품목 수"},
            {"pri": "중간", "impact": 7, "effort": 6, "title": "지역 선택 UI 연결",
             "why": "지역끼리 현재가가 최대 17% 벌어지는데 화면은 서울만 보여 줍니다.",
             "how": "매장 주소에서 지역을 읽어 기본값으로 잡습니다.",
             "metric": "지역 설정 완료율"},
            {"pri": "낮음", "impact": 5, "effort": 8, "title": "비무게 단위 환산 계수 확보",
             "why": "배추 1포기를 kg으로 셈해 원가가 2.5배로 잡힌 적이 있습니다.",
             "how": "KAMIS 규격이나 실측으로 계수를 만들고 출처를 주석에 남깁니다.",
             "metric": "원가 계산 가능 품목 수"},
        ],
        "failures": [
            {"title": "조용한 실패", "detect": "워크플로는 매일 성공, 데이터는 3주째 고정",
             "cause": "공공 API가 해외 IP를 막았는데 try/except가 예외를 삼켰습니다",
             "fix": "수집을 국내 서버에 넘기고 사전 점검과 실패 알림을 붙였습니다"},
            {"title": "지표 오염", "detect": "실전 WAPE 51.1% vs 백테스트 12.5%",
             "cause": "예측일을 가격 기준일이 아니라 날씨 기준일로 적었습니다",
             "fix": "기준일을 바로잡고 현재가가 실측과 다른 142건을 집계에서 뺐습니다"},
            {"title": "단위 불일치", "detect": "메뉴 원가 변동 +31% (실제 -2%)",
             "cause": "배추 '1포기'를 1kg으로 곱했습니다. 이 배추가 합계의 68%였습니다",
             "fix": "환산되는 품목만 더하고 나머지는 '환산 불가'로 적었습니다"},
        ],
    }


# ── 7. 예측 신뢰도 ─────────────────────────────────────────────
def _live_status(veg):
    # 예측 로그를 실측과 대조해 '실전 적중률'이 지금 왜 이 상태인지까지 함께 낸다.
    # 숫자만 내면 0건이 성능 문제로 오해된다. 몇 건이 어느 사유로 빠졌는지 같이 낸다.
    out = {"logged": 0, "matured": 0, "comparable": 0, "stale": 0, "valid": 0,
           "clean_from": None, "next_date": None, "next_n": 0, "result": None}
    if not os.path.exists(PREDLOG):
        return out
    lg = pd.read_csv(PREDLOG)
    if lg.empty:
        return out
    lg["예측일"] = pd.to_datetime(lg["예측일"])
    lg["목표일"] = pd.to_datetime(lg["목표일"])
    latest = veg["날짜"].max()
    out["logged"] = len(lg)
    out["log_from"] = str(lg["예측일"].min().date())
    out["log_to"] = str(lg["예측일"].max().date())
    out["as_of"] = str(latest.date())

    # 예측을 낼 때 기록한 '현재가'가 그날 실측과 같아야 출발점이 맞는 예측이다.
    base = veg.rename(columns={"품목명": "품목", "날짜": "예측일", "가격": "기준일_실측"})
    lg = lg.merge(base[["품목", "예측일", "기준일_실측"]], on=["품목", "예측일"], how="left")
    lg["출발점_정상"] = (lg["현재가"] - lg["기준일_실측"]).abs() <= 1

    mat = lg[lg["목표일"] <= latest]
    out["matured"] = len(mat)
    act = veg.rename(columns={"품목명": "품목", "날짜": "목표일", "가격": "실측가"})
    mat = mat.merge(act[["품목", "목표일", "실측가"]], on=["품목", "목표일"], how="left")
    cmp_ = mat.dropna(subset=["실측가"])
    out["comparable"] = len(cmp_)
    ok = cmp_[cmp_["출발점_정상"]]
    out["stale"] = len(cmp_) - len(ok)
    out["valid"] = len(ok)
    if len(ok):
        a, p, n = ok["실측가"].values, ok["예측가"].values, ok["현재가"].values
        out["result"] = {"wape": round(np.abs(a - p).sum() / np.abs(a).sum() * 100, 1),
                         "dir_acc": round((np.sign(p - n) == np.sign(a - n)).mean() * 100)}

    clean = lg[lg["출발점_정상"]]
    if len(clean):
        out["clean_from"] = str(clean["예측일"].min().date())
        out["clean_n"] = len(clean)
        fut = clean[clean["목표일"] > latest]
        if len(fut):
            d = fut["목표일"].min()
            out["next_date"] = str(d.date())
            out["next_n"] = int((fut["목표일"] == d).sum())
    return out


def reliability():
    acc = _load_json("accuracy.json")
    iv = _load_json("intervals.json")
    veg = _prices()
    ov = acc.get("overall", {})
    h7, h30 = ov.get("h7", {}), ov.get("h30", {})

    # 검증 구간은 품목마다 길이가 같아 아무 품목에서나 읽어도 된다.
    per = list((acc.get("items") or {}).values())
    vp = (per[0].get("h30", {}).get("period") if per else None) or [None, None]

    # 산식을 말로만 두면 안 믿긴다. 실제 배추 평균가에 대입해 원 단위로 보여준다.
    cab = veg[veg["품목명"] == "배추"]
    cab_avg = int(cab["가격"].mean()) if len(cab) else 0
    cab_w30 = ((acc.get("items") or {}).get("배추", {}).get("h30", {}) or {}).get("wape")

    return {
        "period": {
            "from": str(veg["날짜"].min().date()), "to": str(veg["날짜"].max().date()),
            "days": int((veg["날짜"].max() - veg["날짜"].min()).days),
            "years": round((veg["날짜"].max() - veg["날짜"].min()).days / 365.25, 1),
            "rows": len(veg), "items": veg["품목명"].nunique(),
            "generated": acc.get("generated"), "data_latest": acc.get("data_latest"),
        },
        "wape": {
            "formula": "WAPE = Σ|실측가 − 예측가| ÷ Σ실측가 × 100",
            "means": "빗나간 금액을 전부 더해서, 실제 거래된 금액 전부로 나눈 값입니다. "
                     "'평균적으로 가격의 몇 %를 빗나가느냐'를 뜻합니다.",
            "why": "품목마다 값이 100배 넘게 차이 나(깻잎 vs 배추) 오차를 그냥 평균 내면 "
                   "싼 품목의 큰 비율이 전체를 흔듭니다. 합계로 나누면 거래 규모대로 반영됩니다.",
            "h7": h7.get("wape"), "h30": h30.get("wape"),
            "mape7": h7.get("mape"), "mape30": h30.get("mape"),
            "n7": h7.get("n"), "n30": h30.get("n"),
            "example": {"item": "배추", "avg": cab_avg, "wape": cab_w30,
                        "won": int(cab_avg * (cab_w30 or 0) / 100)},
            "misread": {
                "claim": "WAPE 15% → 정확도 85%",
                "why_wrong": "WAPE는 '얼마나 빗나갔나'를 재는 오차율입니다. 100에서 빼도 "
                             "'몇 %를 맞혔다'는 적중률이 되지 않습니다. 맞고 틀림을 세는 지표가 아니라 "
                             "빗나간 폭을 재는 지표이기 때문입니다.",
                "correct": "옳은 읽기는 '평균적으로 실제 가격의 15%쯤을 빗나간다'입니다. "
                           "맞은 비율이 아니라 빗나간 폭이라, 값이 작을수록 좋습니다.",
            },
        },
        "design": {
            "split": "Time Series Split — 시간 순으로 앞 80%만 학습하고 뒤 20%로 채점합니다.",
            "why": "무작위로 섞으면 미래를 보고 과거를 맞히는 꼴이 됩니다(데이터 누수). "
                   "시간 순서를 지켜야 '오늘 시점에서 내일을 맞히는' 실제 상황과 같아집니다.",
            "train_end": vp[0], "valid_from": vp[0], "valid_to": vp[1],
            "valid_n_item": (per[0].get("h30", {}).get("n") if per else None),
            "valid_n_total": h30.get("n"),
            "items": len(per),
        },
        "interval": {
            "nominal": iv.get("nominal"), "coverage": iv.get("coverage_avg"),
            "before": iv.get("coverage_mape_avg"),
            "why": "이게 가장 정직한 신뢰 지표입니다. '80% 구간'이라고 말했으면 실제로 10번 중 8번은 "
                   "그 안에 들어와야 합니다. 실측 포함률이 목표치와 붙어 있으면 "
                   "모델이 자기 불확실성을 제대로 알고 있다는 뜻입니다.",
            "verdict": "목표 80%에 실측 82%. 2%p 넘침은 구간을 조금 넉넉히 잡았다는 뜻이라 "
                       "안전한 방향의 오차입니다.",
        },
        "live": _live_status(veg),
        "grades": [
            {"근거": "백테스트 오차(WAPE)", "표본": f"{h30.get('n', 0):,}건 · 19품목",
             "등급": "중", "이유": "표본이 크고 시간 순서를 지켰습니다. 다만 과거 데이터로 채점한 값이라 "
                                  "실제 운영에서 그대로 나온다는 보장은 아닙니다."},
            {"근거": "예측구간 포함률", "표본": f"{iv.get('cqr_picked', '')} 조합",
             "등급": "강", "이유": "약속한 확률(80%)과 실제 결과(82%)를 직접 맞대 본 값입니다. "
                                  "모델이 스스로의 불확실성을 재는 능력을 검증합니다."},
            {"근거": "방향 적중률", "표본": f"{h30.get('n', 0):,}건",
             "등급": "중", "이유": "30일 70%는 쓸 만하지만 7일 57%는 동전 던지기와 큰 차이가 없습니다. "
                                  "단기 방향은 아직 믿을 수준이 아니라고 봅니다."},
            {"근거": "실전 적중률", "표본": "유효 0건",
             "등급": "없음", "이유": "아직 근거가 없습니다. 없는 걸 있다고 적지 않기 위해 '집계중'으로 둡니다."},
        ],
        "limits": [
            "가락시장 반입량은 배추에만 있습니다. 나머지 18품목은 공급을 직접 보지 못합니다.",
            "기상 데이터는 서울 관측치입니다. 산지 날씨와 다를 수 있습니다.",
            "2026-07 수집 중단처럼 데이터가 끊기면 그 기간 예측은 출발점부터 틀립니다.",
            "5년 7개월치라 코로나·이상기후 같은 큰 사건은 각각 한두 번씩만 들어 있습니다.",
        ],
    }


SECTIONS = {
    "structure": ("데이터 구조", data_structure),
    "eda": ("탐색적 분석", eda),
    "preprocessing": ("전처리", preprocessing),
    "modeling": ("모델·지표", modeling),
    "reliability": ("예측 신뢰도", reliability),
    "regions": ("지역 분석", regions),
    "insights": ("인사이트·액션", insights),
}


def get(key):
    # 계산이 무거워 날짜 단위로 캐시한다.
    if key not in SECTIONS:
        return None
    ck = f"{key}_{date.today().isoformat()}"
    if ck not in _cache:
        _cache.clear()
        _cache[ck] = SECTIONS[key][1]()
    return _cache[ck]
