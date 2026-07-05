// 품목 원가 상세 분석 화면을 ?item= 파라미터 + /api/dashboard 실데이터로 렌더링
document.addEventListener('DOMContentLoaded', () => {
  const fmt = n => n.toLocaleString();

  fetch('/api/dashboard').then(r => r.json()).then(data => {
    const items = [...data.items].sort((a, b) => b.r30 - a.r30);
    const want = new URLSearchParams(location.search).get('item');
    const it = items.find(i => i.name === want) || items[0];   // 기본: 최대 상승 품목

    // 1) 제목·부제
    try {
      document.querySelector('h2').textContent = `${it.name} 원가 분석`;
      document.title = `CartTiming | ${it.name} 원가 분석`;
      const sub = document.querySelector('h2 + p');
      if (sub) sub.textContent = `KAMIS 소매가 · 기상 시차효과 기반 AI 예측 (${data.date} 기준)`;
    } catch (e) {}

    // 2) 차트: 과거 30일 실측(0~400) + 예측 7·30일(400~800) + 신뢰구간 폴리곤
    try {
      const hist = it.trend.slice(-30).map(t => t.p);
      const all = [...hist, it.p7, it.p30, it.ci7[0], it.ci7[1], it.ci30[0], it.ci30[1]];
      const mn = Math.min(...all), mx = Math.max(...all);
      const Y = v => mx === mn ? 150 : Math.round(280 - (v - mn) / (mx - mn) * 260);

      const histPts = hist.map((v, i) => [Math.round(i * 400 / (hist.length - 1)), Y(v)]);
      const x7 = 400 + Math.round(400 * 7 / 30);
      const cy = Y(hist[hist.length - 1]);

      const seg = pts => pts.map((p, i) => (i ? 'L ' : 'M ') + p[0] + ' ' + p[1]).join(' ');
      document.querySelector('.historical-line').setAttribute('d', seg(histPts));
      document.querySelector('.prediction-line').setAttribute('d',
        `M 400 ${cy} L ${x7} ${Y(it.p7)} L 800 ${Y(it.p30)}`);
      document.querySelector('.confidence-area').setAttribute('d',
        `M 400 ${cy} L ${x7} ${Y(it.ci7[1])} L 800 ${Y(it.ci30[1])}` +
        ` L 800 ${Y(it.ci30[0])} L ${x7} ${Y(it.ci7[0])} Z`);
      const marker = document.querySelector('circle');
      if (marker) { marker.setAttribute('cx', 400); marker.setAttribute('cy', cy); }

      // X축 라벨: 실제 날짜
      const d = new Date(data.date);
      const lab = off => { const t = new Date(d); t.setDate(t.getDate() + off); return (t.getMonth() + 1) + '월 ' + t.getDate() + '일'; };
      const xl = document.querySelectorAll('.absolute.bottom-0 span');
      const L = [lab(-30), lab(-15), '오늘', '+7일 (' + lab(7) + ')', '+30일 (' + lab(30) + ')'];
      xl.forEach((s, i) => { if (i < L.length) s.textContent = L[i]; });
    } catch (e) {}

    // 3) AI 인사이트 카드: 예상가·변동폭 실데이터
    try {
      const priceEl = document.querySelector('.text-display-lg');
      priceEl.innerHTML = `₩${fmt(it.p30)}<span class="text-label-md font-label-md opacity-60 ml-1">/ ${it.unit} (30일 뒤)</span>`;
      const chg = document.querySelector('.text-headline-md.text-error-container, .grid .flex.items-center.gap-1');
      if (chg) chg.innerHTML =
        `<span class="material-symbols-outlined">${it.r30 >= 0 ? 'trending_up' : 'trending_down'}</span><span>${it.r30 >= 0 ? '+' : ''}${it.r30}%</span>`;
    } catch (e) {}
  }).catch(() => {});
});
