// 재고 최적화 제안 화면을 /api/dashboard 실데이터로 재구성 (템플릿 카드 복제 방식)
// + 보유 재고 일수 입력 → 소진 시점 예상가·선매입 절감액 실계산 (기획 원칙 ④)
document.addEventListener('DOMContentLoaded', async () => {
  const fmt = n => Math.round(n).toLocaleString();
  const stock = window.ctStore ? await window.ctStore.getStock() : JSON.parse(localStorage.getItem('ct_stock') || '{}');
  // 소진 시점 예상가: 오늘~7일(cur→p7), 7~30일(p7→p30) 선형보간, 30일 초과는 p30
  const priceAt = (it, d) => d <= 0 ? it.cur
    : d <= 7 ? it.cur + (it.p7 - it.cur) * d / 7
    : d <= 30 ? it.p7 + (it.p30 - it.p7) * (d - 7) / 23
    : it.p30;

  fetch('/api/dashboard').then(r => r.json()).then(data => {
    const items = [...data.items].sort((a, b) => b.r30 - a.r30);
    const risers = items.filter(i => i.r30 > 5);

    // 1) 히어로: 단위당 절감 여력 합계 (상승 품목: 지금 사면 30일 뒤 대비 아끼는 금액)
    try {
      const save = risers.reduce((s, i) => s + (i.p30 - i.cur), 0);
      const hero = document.querySelector('.bg-primary-container .font-headline-lg-mobile, .bg-primary-container span[class*="headline-lg"]');
      hero.textContent = '₩' + fmt(save);
      const sub = document.querySelector('.bg-primary-container p.font-body-sm');
      if (sub) sub.textContent = `상승 예상 ${risers.length}개 품목 기준단위당 합계 (${data.date} 기준) · 사용량 입력(BOM) 시 매장별 실제 절감액이 산출됩니다.`;
    } catch (e) {}

    // 2) 품목 카드: 첫 카드를 템플릿으로 전체 품목 재생성
    try {
      const list = document.querySelector('article').parentElement;
      const tpl = document.querySelector('article').cloneNode(true);
      list.innerHTML = '';

      items.forEach(it => {
        const card = tpl.cloneNode(true);
        const rise = it.r30 > 5, drop = it.r7 < -5;

        // 이미지 → 품목 이니셜 블록 (템플릿 사진 오매칭 방지)
        const img = card.querySelector('[style*="background-image"]');
        if (img) {
          img.style.backgroundImage = 'none';
          img.style.cssText += 'display:flex;align-items:center;justify-content:center;background:#e5eeff;font-weight:700;font-size:24px;color:#003527;';
          img.textContent = it.name[0];
        }
        card.querySelector('h3').textContent = it.name;

        const badge = card.querySelector('span.rounded-full');
        badge.textContent = rise ? '선매입 권장' : (drop ? '구매 대기' : '평시 구매');
        badge.className = 'font-label-sm text-label-sm px-3 py-1 rounded-full text-white ' + (rise ? 'bg-primary' : 'bg-secondary');

        const trend = card.querySelector('.mt-xs span.flex');
        const flat = Math.abs(it.r30) <= 5;
        trend.innerHTML = flat
          ? '<span class="material-symbols-outlined text-[18px]">trending_flat</span> 30일 뒤 보합 예상'
          : `<span class="material-symbols-outlined text-[18px]">${it.r30 > 0 ? 'trending_up' : 'trending_down'}</span> 30일 뒤 ${it.r30 > 0 ? '+' : ''}${it.r30}% ${it.r30 > 0 ? '상승' : '하락'} 예상`;
        trend.className = 'flex items-center font-label-md text-label-md ' +
          (flat ? 'text-on-surface-variant' : (it.r30 > 0 ? 'text-error' : 'text-primary-container'));

        const rows = card.querySelectorAll('.px-md.pb-md .flex.items-center.justify-between');
        const desc = card.querySelector('p.leading-relaxed');
        const basePred =
          `현재 ${fmt(it.cur)}원/${it.unit} → 7일 뒤 ${fmt(it.p7)}원 · 30일 뒤 ${fmt(it.p30)}원 예상` +
          ` (범위 ${fmt(it.ci30[0])}~${fmt(it.ci30[1])}).`;

        // 보유 재고(일) 입력 행 — 값 입력 시 소진 시점 기반 제안으로 전환
        const box = card.querySelector('.px-md.pb-md');
        const sd = parseInt(stock[it.name]) || 0;
        const stockRow = document.createElement('div');
        stockRow.className = 'bg-surface-container-low p-sm rounded-lg flex items-center justify-between';
        stockRow.innerHTML =
          '<span class="font-body-sm text-body-sm text-on-surface-variant">보유 재고 (일)</span>' +
          `<input type="number" min="0" max="60" placeholder="입력" value="${sd || ''}"` +
          ' style="width:88px;text-align:right;border:1px solid #bfc9c3;border-radius:8px;padding:4px 8px;font-size:14px;background:#fff;">';
        stockRow.querySelector('input').addEventListener('change', async e => {
          const v = parseInt(e.target.value);
          const s = window.ctStore ? await window.ctStore.getStock() : JSON.parse(localStorage.getItem('ct_stock') || '{}');
          if (v > 0) s[it.name] = v; else delete s[it.name];
          if (window.ctStore) {
            await window.ctStore.setStock(s);
          } else {
            localStorage.setItem('ct_stock', JSON.stringify(s));
          }
          location.reload();
        });
        box.insertBefore(stockRow, box.firstChild);

        if (sd > 0) {
          // 재고 기반 실계산: 소진 시점 예상가와 지금 매입의 차액
          const dep = priceAt(it, sd);
          const depPct = Math.round((dep - it.cur) / it.cur * 100);
          const save = Math.round(dep - it.cur);
          if (rows[0]) rows[0].lastElementChild.textContent = save > 0
            ? `소진 D+${sd} → 지금 ${sd + 14}일치 선구매 권장`
            : `소진 D+${sd} → 소진 직전 재구매 권장`;
          if (rows[1]) rows[1].lastElementChild.textContent = save > 0
            ? `${it.unit}당 ₩${fmt(save)} 절감 (소진일 매입 대비)`
            : (save < 0 ? `대기 시 ${it.unit}당 ₩${fmt(-save)} 절감` : '소진일 가격 변동 미미');
          if (desc) desc.textContent =
            `보유 재고 소진 예정일(D+${sd})의 예상가 ${fmt(dep)}원/${it.unit} (${depPct >= 0 ? '+' : ''}${depPct}%). ` + basePred;
        } else {
          if (rows[0]) rows[0].lastElementChild.textContent = rise ? '향후 14일치 선구매' : (drop ? '3일치 소량 분할 구매' : '평시 물량 유지');
          if (rows[1]) {
            const diff = rise ? it.p30 - it.cur : (drop ? it.cur - it.p7 : 0);
            rows[1].lastElementChild.textContent = diff > 0
              ? `${it.unit}당 ₩${fmt(diff)} ${rise ? '절감 예상' : '대기 시 절감'}`
              : '변동 미미';
          }
          if (desc) desc.textContent = basePred + ' 보유 재고 일수를 입력하면 맞춤 선매입 제안을 계산합니다.';
        }

        const cta = card.querySelector('button.w-full');
        if (cta) {
          cta.innerHTML = (rise ? '상세 분석 보기' : '상세 분석 보기') + ' <span class="material-symbols-outlined text-[20px]">query_stats</span>';
          cta.addEventListener('click', () => { location.href = '/app/item-analysis?item=' + encodeURIComponent(it.name); });
        }
        list.appendChild(card);
      });
    } catch (e) {}
  }).catch(() => {});
});
