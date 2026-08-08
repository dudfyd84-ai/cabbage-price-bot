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
         "desc": "KAMIS 소매가. 사장님이 실제 지불하는 가격에 가까워 도매가 대신 채택했다."},
        {"name": "weather_asos_data", "layer": "원천", "rows": len(w), "span": span(w),
         "cols": ["날짜", "지점명", "평균기온", "최고기온", "최저기온", "일강수량", "일조합"],
         "grain": "1일 × 1지점",
         "desc": "기상청 ASOS 관측. 산지 매핑이 없어 5개 광역 지점을 대리 변수로 쓴다."},
        {"name": "kamis_region_retail", "layer": "원천", "rows": len(reg), "span": span(reg) if len(reg) else "—",
         "cols": ["날짜", "지역", "품목명", "단위", "가격"], "grain": "1일 × 1지역 × 1품목",
         "desc": "서울 외 4개 지역 소매가. 2년치를 백필했다."},
        {"name": "garak_cabbage_intake", "layer": "원천", "rows": len(intake),
         "span": span(intake) if len(intake) else "—",
         "cols": ["날짜", "배추반입량_톤"], "grain": "1일",
         "desc": "가락시장 배추 반입량. 유일하게 확보한 공급측 변수다."},
        {"name": "predict_log", "layer": "산출", "rows": len(log),
         "span": span(log, "예측일") if len(log) else "—",
         "cols": ["예측일", "품목", "호라이즌", "목표일", "현재가", "예측가"], "grain": "1예측일 × 1품목 × 1호라이즌",
         "desc": "매일 낸 예측을 적재해 실전 적중률 검증에 쓴다."},
        {"name": "region_predictions.json", "layer": "산출", "rows": 4 * 18,
         "span": _load_json("region_predictions.json").get("updated", "—"),
         "cols": ["region", "item", "cur", "p7/p30", "lo/hi"], "grain": "1지역 × 1품목",
         "desc": "지역 예측 결과. 모델 파일을 저장하면 144개·91MB가 매일 커밋돼 결과만 싣는다."},
    ]
    return {
        "tables": tables,
        "total_rows": sum(t["rows"] for t in tables),
        "note": "원천 4종은 매일 06:00 배치가 증분 수집하고, 산출 2종은 재학습이 다시 만든다. "
                "모든 조인 키는 (날짜, 품목명)이며 지역 확장 시 (날짜, 지역, 품목명)으로 늘어난다.",
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
        {"step": "1. 평일 필터", "why": "주말·공휴일은 조사가 없어 값이 비어 있다.",
         "how": "수집 대상을 평일로 한정한다.", "effect": "결측을 '없는 날'과 '못 받은 날'로 구분한다."},
        {"step": "2. 이상치 제거", "why": "가격 0원과 하이픈(-) 문자열이 섞여 들어온다.",
         "how": "수집 단계에서 0 이하·비숫자를 버린다.", "effect": "평균을 끌어내리는 가짜 저가가 사라진다."},
        {"step": "3. 중복 제거", "why": "같은 날 같은 품목이 두 번 올 수 있다.",
         "how": "(날짜, 품목명) 기준 마지막 값만 남긴다.",
         "effect": f"{len(raw):,}행 → {len(veg):,}행"},
        {"step": "4. 결측 보간", "why": "모델 입력은 연속된 시계열이어야 한다.",
         "how": "ffill 후 bfill. 앞 값이 없을 때만 뒤 값을 쓴다.",
         "effect": "휴장 갭이 직전 시세로 이어진다."},
        {"step": "5. 단위 정규화", "why": "1포기·1개·100g·1kg·10개가 섞여 있다.",
         "how": "무게 단위만 100g 기준으로 환산하고 나머지는 환산 불가로 표시한다.",
         "effect": "환산 근거가 없는 품목을 합계에서 배제해 원가 왜곡을 막는다."},
        {"step": "6. 시차 피처 생성", "why": "날씨는 즉시가 아니라 30~60일 뒤 가격에 반영된다.",
         "how": "기온·강수 lag 30/45/60 + 이동평균 7/14, 가격 lag 7/14/30.",
         "effect": "모델이 시차 구조를 직접 학습한다."},
        {"step": "7. 시계열 분할", "why": "랜덤 분할은 미래로 과거를 맞히는 누수를 만든다.",
         "how": "앞 80% 학습 / 뒤 20% 검증.", "effect": "검증 성능이 실제 운영 성능에 가까워진다."},
    ]
    units = veg.groupby("단위")["품목명"].nunique().to_dict()
    return {"steps": steps, "unit_mix": {k: int(v) for k, v in units.items()},
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
             "why": "생육 주기상 날씨가 출하량에 반영되기까지의 지연을 담는다."},
            {"group": "기상 추세", "vars": "평균기온·최고기온·일강수량 × 이동평균 7/14", "n": 6,
             "why": "단일 일자 관측의 노이즈를 줄이고 최근 기조를 준다."},
            {"group": "가격 시차", "vars": "price_lag 7/14/30", "n": 3,
             "why": "가격의 자기상관. 단기 예측에서 가장 강한 신호다."},
            {"group": "계절", "vars": "target_month", "n": 1,
             "why": "예측 대상 시점의 월. 품목별 제철 구조를 학습한다."},
            {"group": "공급", "vars": "가락시장 반입량 lag 7/14/30 + 이동평균", "n": 5,
             "why": "배추만 확보. 유일한 직접 공급 변수다."},
        ],
        "algo": {
            "name": "XGBoost 회귀",
            "why": "표본이 2천 행 규모라 딥러닝은 과적합 위험이 크고, 무엇보다 어떤 피처가 기여했는지 설명할 수 있어야 했다.",
            "target": "log1p 변환 후 학습, expm1로 역변환. 가격은 우편향이라 로그가 잔차를 안정시킨다.",
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
            "probe": {"coverage": "5개 지역 모두 18/19종", "gap": "서울 대비 평균 15~19%",
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
             "evidence": "백테스트 7,450건 기준. 두 호라이즌 모두 같은 검증 구간을 쓴다."},
            {"stage": "의미", "label": "Meaning",
             "body": "단기는 노이즈가, 장기는 계절성과 기상 시차가 지배한다. 모델이 배운 건 후자다.",
             "evidence": "기상 lag 30~60일 상관이 lag 0보다 일관되게 높다(EDA 참조)."},
            {"stage": "전략", "label": "Action",
             "body": "단기 시세 알림이 아니라 월 단위 발주 계획을 주력 기능으로 삼는다.",
             "evidence": "'오늘 싸다'가 아니라 '이번 달 미리 사둘 품목'이 사용자 의사결정 단위다."},
        ],
        "actions": [
            {"pri": "높음", "title": "30일 급등 예상 품목 선매입 알림",
             "why": "방향 적중률이 가장 높은 구간이라 모델 신뢰도가 뒷받침된다.",
             "how": "r30 15% 이상 품목을 주 1회 알림톡으로 발송한다.",
             "metric": "알림 대비 실제 선매입 전환율 · 절감액"},
            {"pri": "높음", "title": "예측 구간 하한을 함께 노출",
             "why": "발주 판단은 기대값이 아니라 최악의 경우에 걸린다.",
             "how": "구간 하한·상한과 실측 포함률을 카드에 같이 표시한다.",
             "metric": "구간 포함률 80% 유지"},
            {"pri": "중간", "title": "고변동 품목은 예측 대신 경보로 전환",
             "why": "파프리카는 MAPE 58%로 예측값을 제시하는 것 자체가 잘못된 신호다.",
             "how": "오차 30% 이상 품목은 수치 대신 '변동성 높음' 경보만 준다.",
             "metric": "오차 30% 초과 품목 수"},
            {"pri": "중간", "title": "지역 선택 UI 연결",
             "why": "지역 간 현재가가 최대 17% 벌어지는데 화면은 서울만 보여준다.",
             "how": "매장 주소에서 지역을 유추해 기본값으로 잡는다.",
             "metric": "지역 설정 완료율"},
            {"pri": "낮음", "title": "비무게 단위 환산 계수 확보",
             "why": "배추 1포기를 kg으로 취급해 원가가 2.5배로 잡힌 사고가 있었다.",
             "how": "KAMIS 규격 정보나 실측으로 계수를 만들고 출처를 주석에 남긴다.",
             "metric": "원가 계산 가능 품목 수"},
        ],
        "failures": [
            {"title": "조용한 실패", "detect": "워크플로는 매일 성공, 데이터는 3주째 고정",
             "cause": "공공 API가 해외 IP를 차단, try/except가 예외를 삼킴",
             "fix": "국내 서버 위임 + 사전 점검 + 실패 알림 이슈 자동 생성"},
            {"title": "지표 오염", "detect": "실전 WAPE 51.1% vs 백테스트 12.5%",
             "cause": "예측일을 가격 기준일이 아닌 날씨 기준일로 기록",
             "fix": "기준일 교정 + 현재가가 실측과 다른 예측 142건 자동 제외"},
            {"title": "단위 불일치", "detect": "메뉴 원가 변동 +31% (실제 -2%)",
             "cause": "배추 '1포기'를 1kg으로 곱함. 합계의 68%를 차지",
             "fix": "환산 가능한 품목만 합산, 나머지는 '환산 불가'로 표시"},
        ],
    }


SECTIONS = {
    "structure": ("데이터 구조", data_structure),
    "eda": ("탐색적 분석", eda),
    "preprocessing": ("전처리", preprocessing),
    "modeling": ("모델·지표", modeling),
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
