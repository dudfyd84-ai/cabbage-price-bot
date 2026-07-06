// 품목 원가 상세 분석: ?item= 파라미터 + 1주/2주/4주 호라이즌 전환 (8주는 예측 범위 밖이라 숨김)
document.addEventListener('DOMContentLoaded', () => {
  const fmt = n => Math.round(n).toLocaleString();

  fetch('/api/dashboard').then(r => r.json()).then(data => {
    const items = [...data.items].sort((a, b) => b.r30 - a.r30);
    const want = new URLSearchParams(location.search).get('item');
    const it = items.find(i => i.name === want) || items[0];

    // 예측·신뢰구간 보간: D+7, D+30 사이 선형 (모델 산출 지점 기준)
    const at = d => d <= 0 ? it.cur
      : d <= 7 ? it.cur + (it.p7 - it.cur) * d / 7
      : it.p7 + (it.p30 - it.p7) * (d - 7) / 23;
    const ciAt = (d, k) => d <= 0 ? it.cur
      : d <= 7 ? it.cur + (it.ci7[k] - it.cur) * d / 7
      : it.ci7[k] + (it.ci30[k] - it.ci7[k]) * (d - 7) / 23;

    // 1) 제목·부제 + 과장 문구 정정 (통계적 신뢰구간이 아니므로 정직하게 표기)
    try {
      document.querySelector('h2').textContent = `${it.name} 원가 분석`;
      document.title = `CartTiming | ${it.name} 원가 분석`;
      const sub = document.querySelector('h2 + p');
      if (sub) sub.textContent = `KAMIS 소매가 · 기상 시차효과 기반 AI 예측 (${data.date} 기준)`;

      // 범례 "95% 신뢰 구간" → "예상 범위(백테스트 오차 기반)"
      document.querySelectorAll('span').forEach(s => {
        if (s.textContent.trim() === '95% 신뢰 구간') s.textContent = '예상 범위 (백테스트 오차 기반)';
      });
      // 하드코딩 "신뢰도 94%" → 실제 백테스트 오차율로 교체
      const mape30 = it.cur > 0 ? Math.round((it.ci30[1] - it.p30) / it.p30 * 100) : null;
      document.querySelectorAll('p, span, div').forEach(el => {
        if (el.children.length === 0 && el.textContent.trim() === '신뢰도') el.textContent = '백테스트 오차(30일)';
        if (el.children.length <= 1 && /^94%/.test(el.textContent.trim()) && mape30 != null) el.innerHTML = `±${mape30}%`;
      });
    } catch (e) {}

    // 2) 호라이즌별 차트 렌더 (과거 30일 실측 x0~400 + 예측 x400~800)
    const render = H => {
      try {
        const hist = it.trend.slice(-30).map(t => t.p);
        const mids = Math.round(H / 2);
        const all = [...hist, at(mids), at(H), ciAt(mids, 0), ciAt(mids, 1), ciAt(H, 0), ciAt(H, 1)];
        const mn = Math.min(...all), mx = Math.max(...all);
        const Y = v => mx === mn ? 150 : Math.round(280 - (v - mn) / (mx - mn) * 260);

        const histPts = hist.map((v, i) => [Math.round(i * 400 / (hist.length - 1)), Y(v)]);
        const xm = 600, cy = Y(hist[hist.length - 1]);
        const seg = pts => pts.map((p, i) => (i ? 'L ' : 'M ') + p[0] + ' ' + p[1]).join(' ');

        document.querySelector('.historical-line').setAttribute('d', seg(histPts));
        document.querySelector('.prediction-line').setAttribute('d',
          `M 400 ${cy} L ${xm} ${Y(at(mids))} L 800 ${Y(at(H))}`);
        document.querySelector('.confidence-area').setAttribute('d',
          `M 400 ${cy} L ${xm} ${Y(ciAt(mids, 1))} L 800 ${Y(ciAt(H, 1))}` +
          ` L 800 ${Y(ciAt(H, 0))} L ${xm} ${Y(ciAt(mids, 0))} Z`);
        const marker = document.querySelector('circle');
        if (marker) { marker.setAttribute('cx', 400); marker.setAttribute('cy', cy); }

        const d0 = new Date(data.date);
        const lab = off => { const t = new Date(d0); t.setDate(t.getDate() + off); return (t.getMonth() + 1) + '월 ' + t.getDate() + '일'; };
        const chartWrap = document.querySelector('.historical-line').closest('div');
        const xl = chartWrap ? chartWrap.querySelectorAll('.absolute.bottom-0 span') : [];
        const L = [lab(-30), lab(-15), '오늘', `+${mids}일`, `+${H}일 (${lab(H)})`];
        xl.forEach((s, i) => { if (i < L.length) s.textContent = L[i]; });

        // AI 인사이트: 호라이즌 기준 예상가·변동폭
        const pH = at(H), pct = Math.round((pH - it.cur) / it.cur * 100);
        const priceEl = document.querySelector('.text-display-lg');
        if (priceEl) priceEl.innerHTML =
          `₩${fmt(pH)}<span class="text-label-md font-label-md opacity-60 ml-1">/ ${it.unit} (${H}일 뒤)</span>`;
        const chg = document.querySelector('.grid .flex.items-center.gap-1');
        if (chg) chg.innerHTML =
          `<span class="material-symbols-outlined">${pct >= 0 ? 'trending_up' : 'trending_down'}</span><span>${pct >= 0 ? '+' : ''}${pct}%</span>`;
      } catch (e) {}
    };

    // 3) 기간 버튼 연결: 1주=7일, 2주=14일(보간), 4주=30일 / 8주는 예측 범위 밖 → 숨김
    try {
      const H_MAP = { '1주': 7, '2주': 14, '4주': 30 };
      const btns = [...document.querySelectorAll('button')].filter(b => ['1주', '2주', '4주', '8주'].includes(b.textContent.trim()));
      btns.forEach(b => {
        const t = b.textContent.trim();
        if (t === '8주') { b.style.display = 'none'; return; }
        b.addEventListener('click', () => {
          btns.forEach(x => { x.className = 'px-4 py-1.5 text-label-sm font-label-sm rounded-md transition-all text-on-surface-variant hover:bg-surface-container-low'; });
          b.className = 'px-4 py-1.5 text-label-sm font-label-sm rounded-md transition-all bg-secondary text-white shadow-sm';
          render(H_MAP[t]);
        });
      });
    } catch (e) {}

    render(30);   // 기본 4주
  }).catch(() => {});
});
