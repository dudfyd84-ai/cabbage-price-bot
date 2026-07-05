// 재고 최적화 제안 화면을 /api/dashboard 실데이터로 재구성 (템플릿 카드 복제 방식)
document.addEventListener('DOMContentLoaded', () => {
  const fmt = n => n.toLocaleString();

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
        if (rows[0]) rows[0].lastElementChild.textContent = rise ? '향후 14일치 선구매' : (drop ? '3일치 소량 분할 구매' : '평시 물량 유지');
        if (rows[1]) {
          const diff = rise ? it.p30 - it.cur : (drop ? it.cur - it.p7 : 0);
          rows[1].lastElementChild.textContent = diff > 0
            ? `${it.unit}당 ₩${fmt(diff)} ${rise ? '절감 예상' : '대기 시 절감'}`
            : '변동 미미';
        }
        const desc = card.querySelector('p.leading-relaxed');
        if (desc) desc.textContent =
          `현재 ${fmt(it.cur)}원/${it.unit} → 7일 뒤 ${fmt(it.p7)}원 · 30일 뒤 ${fmt(it.p30)}원 예상` +
          ` (범위 ${fmt(it.ci30[0])}~${fmt(it.ci30[1])}). XGBoost 예측 · 날씨 시차효과 반영.`;

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
