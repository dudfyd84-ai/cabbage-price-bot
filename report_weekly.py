# 주간 가격 동향·예측·메뉴 원가 변동을 PDF 리포트로 자동 생성하는 모듈 (1개 매장 시범)
import io
import logging
import os
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer,
                                 Table, TableStyle)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("report_weekly")

OUTPUT_DIR = os.getenv("REPORT_OUTPUT_DIR", "reports")
ALERT_LEVEL = "위험"
KEY_ITEM_COUNT = 4

# 실제 매장별 BOM(메뉴 재료 목록)은 브라우저 localStorage/Supabase에만 저장되어 있어
# 서버에서 읽을 방법이 없음 → 카카오 알림 1품목 시범과 같은 방식으로, 데모 매장의
# 샘플 메뉴 1개를 고정해 원가 변동을 계산함(리포트에도 "샘플 메뉴"로 명시).
SAMPLE_MENU = {
    "name": "배추김치찌개",
    "ings": [
        {"item": "배추", "qty_kg": 0.3},
        {"item": "대파", "qty_kg": 0.05},
        {"item": "마늘", "qty_kg": 0.02},
        {"item": "양파", "qty_kg": 0.1},
    ],
}

pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))


def fetch_dashboard():
    # /api/dashboard는 무료 플랜(비로그인 포함) 요청에 p30/r30/ci30을 null로 마스킹함(구독 게이팅).
    # 이 스크립트는 서버와 같은 레포에서 도는 내부 배치라 HTTP 대신 app.py의 원본 함수를 그대로 호출해
    # 마스킹 없는 전체 데이터를 씀 — app.py는 읽기만 하고 수정하지 않음.
    from app import dashboard_data
    return dashboard_data()


def pick_key_items(items, n=KEY_ITEM_COUNT):
    # 위험 등급 중 30일 상승률이 높은 순으로 우선 담고, 모자라면 나머지 품목에서 채움
    danger = sorted((i for i in items if i.get("level") == ALERT_LEVEL),
                     key=lambda i: i.get("r30") or 0, reverse=True)
    picked = list(danger[:n])
    ranked = sorted(items, key=lambda i: (i.get("r30") or -999), reverse=True)
    for i in ranked:
        if len(picked) >= n:
            break
        if i not in picked:
            picked.append(i)
    return picked[:n]


def render_trend_chart(item):
    trend = item.get("trend", [])
    if not trend:
        return None
    dates = [t["d"] for t in trend]
    prices = [t["p"] for t in trend]
    fig, ax = plt.subplots(figsize=(3.2, 1.6))
    ax.plot(dates, prices, color="#2563eb", linewidth=1.6)
    step = max(1, len(dates) // 5)
    ax.set_xticks(dates[::step])
    ax.tick_params(axis="x", labelrotation=45, labelsize=6)
    ax.tick_params(axis="y", labelsize=6)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf


def bom_cost_summary(items_by_name):
    rows = [["재료", "수량", "현재 원가", "7일 뒤 예측", "30일 뒤 예측"]]
    total_now = total_p7 = total_p30 = 0
    for ing in SAMPLE_MENU["ings"]:
        it = items_by_name.get(ing["item"])
        if not it:
            continue
        qty = ing["qty_kg"]
        c_now, c_p7, c_p30 = it["cur"] * qty, it["p7"] * qty, it["p30"] * qty
        total_now += c_now
        total_p7 += c_p7
        total_p30 += c_p30
        rows.append([ing["item"], f"{qty}kg", f"{int(c_now):,}원", f"{int(c_p7):,}원", f"{int(c_p30):,}원"])
    rows.append(["합계", "", f"{int(total_now):,}원", f"{int(total_p7):,}원", f"{int(total_p30):,}원"])
    return rows, total_now, total_p30


def build_pdf(data, out_path):
    items = data.get("items", [])
    items_by_name = {i["name"]: i for i in items}
    report_date = data.get("date", date.today().isoformat())

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontName="HYGothic-Medium", fontSize=18)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="HYGothic-Medium", fontSize=13, spaceBefore=14)
    body = ParagraphStyle("body", parent=styles["Normal"], fontName="HYSMyeongJo-Medium", fontSize=9, leading=13)
    note = ParagraphStyle("note", parent=body, textColor=colors.grey, fontSize=8)

    story = [
        Paragraph("주간 가격 동향 리포트", h1),
        Paragraph(f"기준일: {report_date}", body),
        Spacer(1, 6 * mm),
    ]

    story.append(Paragraph("1. 핵심 품목 시세 추이·예측", h2))
    key_items = pick_key_items(items)
    if not key_items:
        story.append(Paragraph("표시할 품목 데이터가 없습니다.", body))
    for it in key_items:
        chart = render_trend_chart(it)
        row = [
            Paragraph(
                f"<b>{it['name']}</b><br/>현재 {it['cur']:,}원<br/>"
                f"7일 뒤 {it['p7']:,}원({it['r7']:+d}%)<br/>"
                f"30일 뒤 {it['p30']:,}원({it['r30']:+d}%)<br/>등급: {it['level']}",
                body,
            ),
            Image(chart, width=70 * mm, height=35 * mm) if chart else Paragraph("차트 없음", body),
        ]
        t = Table([row], colWidths=[60 * mm, 75 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story.append(t)
        story.append(Spacer(1, 3 * mm))

    story.append(Paragraph("2. 급등 경보 (위험 등급)", h2))
    danger_items = [i for i in items if i.get("level") == ALERT_LEVEL]
    if danger_items:
        danger_items.sort(key=lambda i: i.get("r30") or 0, reverse=True)
        rows = [["품목", "현재가", "30일 뒤 예측", "상승률"]]
        for it in danger_items:
            rows.append([it["name"], f"{it['cur']:,}원", f"{it['p30']:,}원", f"{it['r30']:+d}%"])
        t = Table(rows, colWidths=[35 * mm, 35 * mm, 35 * mm, 25 * mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "HYSMyeongJo-Medium"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fee2e2")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("이번 주 위험 등급 품목이 없습니다.", body))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("3. 메뉴 원가 변동", h2))
    story.append(Paragraph(
        f"* 매장별 실제 BOM 대신 데모 매장의 샘플 메뉴({SAMPLE_MENU['name']})로 계산한 시범 결과입니다.", note))
    rows, total_now, total_p30 = bom_cost_summary(items_by_name)
    t = Table(rows, colWidths=[25 * mm, 20 * mm, 27 * mm, 27 * mm, 27 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "HYSMyeongJo-Medium"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0e7ff")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f3f4f6")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
    ]))
    story.append(t)
    if total_now:
        delta_pct = round((total_p30 - total_now) / total_now * 100)
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(f"30일 뒤 예상 원가 변동: {delta_pct:+d}%", body))

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    doc = SimpleDocTemplate(out_path, pagesize=A4,
                             leftMargin=18 * mm, rightMargin=18 * mm, topMargin=15 * mm, bottomMargin=15 * mm)
    doc.build(story)
    return out_path


def main():
    data = fetch_dashboard()
    report_date = data.get("date", date.today().isoformat())
    out_path = os.path.join(OUTPUT_DIR, f"weekly_{report_date}.pdf")
    build_pdf(data, out_path)
    logger.info("주간 리포트 생성 완료: %s", out_path)


if __name__ == "__main__":
    main()
