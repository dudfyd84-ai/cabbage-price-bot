// 홈 대시보드의 하드코딩 수치를 /api/dashboard 실데이터로 교체하는 연동 스크립트
document.addEventListener('DOMContentLoaded', () => {
  const fmt = n => n.toLocaleString();

  fetch('/api/dashboard').then(r => r.json()).then(data => {
    const items = [...data.items].sort((a, b) => b.r30 - a.r30);
    const risers = items.filter(i => i.r30 > 5);
    const top = items[0];

    // 1) 상단 경보: 다음 달 예상 비용 분석
    try {
      const p = document.querySelector('.bg-error-container p.font-headline-md');
      const h = document.querySelector('.bg-error-container h2');
      if (top && top.r30 > 5) {
        p.textContent = `+${top.r30}% 지출 증가 예상`;
        h.textContent = `다음 달 예상 비용 분석 · 상승 품목 ${risers.length}개 (${data.date} 기준)`;
      } else {
        p.textContent = '지출 안정 예상';
        h.textContent = `다음 달 예상 비용 분석 (${data.date} 기준)`;
      }
    } catch (e) {}

    // 2) 재고 확보 알림 카드: 최대 상승 품목으로 교체
    try {
      const card = document.querySelector('.bg-secondary');
      if (top && top.r30 > 5) {
        card.querySelector('p.font-headline-md').textContent =
          `${top.name} 가격 30일 뒤 ${top.r30}% 상승 예상!`;
        card.querySelector('p.font-body-sm').textContent =
          `현재 ${fmt(top.cur)}원/${top.unit} → 30일 뒤 ${fmt(top.p30)}원 예상` +
          ` (범위 ${fmt(top.ci30[0])}~${fmt(top.ci30[1])}원). 상승 전 필요 물량 선구매를 검토하세요.`;
      }
    } catch (e) {}

    // 3) 핵심 식자재 가격 추이: 상승률 상위 2개 품목의 실제 추이로 SVG 재생성
    try {
      const [a, b] = [items[0], items[1]];
      const trendH3 = [...document.querySelectorAll('h3')].find(h => h.textContent.includes('가격 추이'));
      const headRow = trendH3.parentElement.parentElement;           // h3 래퍼의 상위 flex 행
      const chipSpans = headRow.querySelectorAll('.flex.gap-sm > span');
      if (chipSpans.length >= 2) { chipSpans[0].textContent = a.name; chipSpans[1].textContent = b.name; }

      const paths = document.querySelectorAll('svg path');
      const toPath = it => {
        const vals = it.trend.slice(-60).map(t => t.p);
        const mn = Math.min(...vals), mx = Math.max(...vals);
        return vals.map((v, i) => {
          const x = Math.round(i * 1000 / (vals.length - 1));
          const y = mx === mn ? 100 : Math.round(180 - (v - mn) / (mx - mn) * 160);
          return (i === 0 ? 'M' : 'L') + x + ',' + y;
        }).join(' ');
      };
      if (paths.length >= 2 && a.trend && b.trend) {
        paths[0].setAttribute('d', toPath(a));
        paths[1].setAttribute('d', toPath(b));
      }
      const xlabels = document.querySelectorAll('.relative.z-10 span');
      const L = ['-60일', '-45일', '-30일', '-15일', '오늘'];
      xlabels.forEach((s, i) => { if (i < L.length) s.textContent = L[i]; });
      const sub = document.querySelector('h3 + p.font-body-sm, .font-body-sm.text-on-surface-variant');
      const subEl = document.evaluate("//h3[contains(text(),'가격 추이')]/following-sibling::p", document, null, 9, null).singleNodeValue;
      if (subEl) subEl.textContent = '최근 60일 실측 추이 (소매가, 서울)';
    } catch (e) {}

    // 4) BOM 섹션: 샘플임을 명시 (BOM 등록 연동 전)
    try {
      const h3s = [...document.querySelectorAll('h3')];
      const bomH = h3s.find(h => h.textContent.includes('메뉴별 원가'));
      if (bomH) {
        const tag = document.createElement('span');
        tag.textContent = ' 샘플';
        tag.style.cssText = 'font-size:12px;font-weight:600;color:#92400e;background:#fef3c7;border-radius:9999px;padding:2px 8px;vertical-align:middle;margin-left:6px;';
        bomH.appendChild(tag);
      }
    } catch (e) {}
  }).catch(() => {});
});
