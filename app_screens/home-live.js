// 홈 대시보드의 하드코딩 수치를 /api/dashboard 실데이터 + 등록 BOM(localStorage)으로 교체
document.addEventListener('DOMContentLoaded', () => {
  const fmt = n => Math.round(n).toLocaleString();

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
      const headRow = trendH3.parentElement.parentElement;
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
      const subEl = document.evaluate("//h3[contains(text(),'가격 추이')]/following-sibling::p",
        document, null, 9, null).singleNodeValue;
      if (subEl) subEl.textContent = '최근 60일 실측 추이 (소매가, 서울)';
    } catch (e) {}

    // 4) BOM 섹션: 등록 메뉴가 있으면 실데이터 원가 카드로 교체, 없으면 샘플 배지
    try {
      const h3s = [...document.querySelectorAll('h3')];
      const bomH = h3s.find(h => h.textContent.includes('메뉴별 원가'));
      const boms = JSON.parse(localStorage.getItem('ct_bom') || '[]');

      if (!boms.length) {
        const tag = document.createElement('span');
        tag.textContent = ' 샘플';
        tag.style.cssText = 'font-size:12px;font-weight:600;color:#92400e;background:#fef3c7;border-radius:9999px;padding:2px 8px;vertical-align:middle;margin-left:6px;';
        bomH.appendChild(tag);
        return;
      }

      // 재료 단가 헬퍼: 우리 11품목 소매 단위 → g/ea 기준 단가 환산
      const byName = Object.fromEntries(items.map(i => [i.name, i]));
      const unitPrice = it => {
        const u = it.unit || '';
        if (u.includes('100g')) return { type: 'g', now: it.cur / 100, fut: it.p30 / 100 };
        if (u.includes('kg'))   return { type: 'g', now: it.cur / 1000, fut: it.p30 / 1000 };
        if (u.includes('10개')) return { type: 'ea', now: it.cur / 10, fut: it.p30 / 10 };
        if (u.includes('개') || u.includes('포기')) return { type: 'ea', now: it.cur, fut: it.p30 };
        return null;
      };
      const calc = bom => {
        let now = 0, fut = 0, missed = [], topRise = null;
        bom.ings.forEach(g => {
          const it = byName[g.name];
          const up = it && unitPrice(it);
          const qty = g.unit === 'kg' ? g.qty * 1000 : (g.unit === 'l' ? g.qty * 1000 : g.qty);
          const isEa = g.unit === 'ea';
          if (up && ((up.type === 'g' && !isEa) || (up.type === 'ea' && isEa))) {
            const q = up.type === 'g' ? qty : g.qty;
            now += up.now * q; fut += up.fut * q;
            const d = (up.fut - up.now) * q;
            if (!topRise || d > topRise.d) topRise = { name: g.name, d };
          } else missed.push(g.name);
        });
        return { now, fut, missed, topRise };
      };

      // 카드 그리드: 첫 카드를 템플릿으로 등록 메뉴 수만큼 재생성
      const grid = bomH.parentElement.parentElement.querySelector('.grid');
      const tpl = grid.firstElementChild.cloneNode(true);
      grid.innerHTML = '';
      boms.forEach(bom => {
        const c = calc(bom);
        const card = tpl.cloneNode(true);
        const img = card.querySelector('[style*="background-image"]');
        if (img) {
          img.style.backgroundImage = 'none';
          img.style.cssText += 'display:flex;align-items:center;justify-content:center;background:#e5eeff;font-weight:700;font-size:20px;color:#003527;';
          img.textContent = bom.menu[0];
        }
        card.querySelector('h4').textContent = bom.menu;

        const pct = c.now > 0 ? Math.round((c.fut - c.now) / c.now * 100) : 0;
        const diff = Math.round(c.fut - c.now);
        const chip = card.querySelector('span.rounded-full');
        if (pct > 5) {
          chip.textContent = `+${pct}% 위험 (+${fmt(diff)}원/인분)`;
          chip.className = 'font-label-sm text-label-sm px-sm py-xs bg-error-container text-error rounded-full';
        } else if (pct < -5) {
          chip.textContent = `${pct}% 안정 (${fmt(diff)}원/인분)`;
          chip.className = 'font-label-sm text-label-sm px-sm py-xs bg-tertiary-container text-on-tertiary-container rounded-full';
        } else {
          chip.textContent = `변동 미미 (${diff >= 0 ? '+' : ''}${fmt(diff)}원/인분)`;
          chip.className = 'font-label-sm text-label-sm px-sm py-xs bg-surface-container text-on-surface-variant rounded-full';
        }

        const cause = card.querySelector('p.font-body-sm');
        cause.textContent = c.topRise
          ? `주요 원인: ${c.topRise.name} 가격 변동` + (c.missed.length ? ` · 미연동 재료 ${c.missed.length}개` : '')
          : (c.missed.length ? `연동 가능한 재료 없음 (${c.missed.join(', ')})` : '재료 변동 없음');

        const priceEl = card.querySelector('.font-data-mono');
        priceEl.textContent = c.now > 0 ? `₩${fmt(c.fut)}` : '—';
        const icon = card.querySelector('.pt-sm span.material-symbols-outlined');
        icon.textContent = pct > 5 ? 'trending_up' : (pct < -5 ? 'trending_down' : 'horizontal_rule');
        icon.className = 'material-symbols-outlined ' + (pct > 5 ? 'trend-up' : (pct < -5 ? 'trend-down' : 'text-outline-variant'));

        card.addEventListener('click', () => { location.href = '/app/bom-register'; });
        grid.appendChild(card);
      });
    } catch (e) {}
  }).catch(() => {});
});
