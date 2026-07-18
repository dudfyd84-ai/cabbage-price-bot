// BOM 등록 화면: 전 품목 자동완성(datalist) 기능 제공
document.addEventListener('DOMContentLoaded', () => {
  // ── 1) 시세 및 예측 데이터 동시 로드 ──
  Promise.all([
    fetch('/api/dashboard').then(r => r.json()).catch(() => ({ items: [] })),
    fetch('/api/retail').then(r => r.json()).catch(() => ({ groups: {} }))
  ]).then(([dashboard, retail]) => {
    window.ctDashboardData = dashboard;
    window.ctRetailData = retail; // 글로벌 변수로 시세 데이터 노출

    // 자동완성 목록 생성 (예측 품목 + 일반 시세 품목 합집합)
    const retailNames = Object.values(retail.groups || {}).flat().map(i => i.name);
    const dashboardNames = (dashboard.items || []).map(i => i.name);
    const names = [...new Set([...retailNames, ...dashboardNames])];

    if (!names.length) return;
    const dl = document.createElement('datalist');
    dl.id = 'ct-ings';
    dl.innerHTML = names.map(n => `<option value="${n}">`).join('');
    document.body.appendChild(dl);

    const attach = () => document.querySelectorAll('#ingredient-container input[type="text"]')
      .forEach(inp => inp.setAttribute('list', 'ct-ings'));
    attach();
    const addBtn = document.getElementById('add-ingredient');
    if (addBtn) addBtn.addEventListener('click', () => setTimeout(attach, 50));

    // 시세 정보 로드 후 기존/프리셋 카드의 예상 시세 계산 실행
    if (typeof window.updateAllEstimates === 'function') {
      window.updateAllEstimates();
    }
  }).catch(() => {});
});
