// BOM 등록 화면: 메뉴·식재료 localStorage 저장 + 전 품목 자동완성(datalist)
document.addEventListener('DOMContentLoaded', () => {
  // ── 1) 식재료명 자동완성: 시세 API 전 품목을 datalist로 제공 ──
  fetch('/api/retail').then(r => r.json()).then(retail => {
    const names = [...new Set(Object.values(retail.groups || {}).flat().map(i => i.name))];
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
  }).catch(() => {});

  // ── 2) BOM 저장 ──
  const saveBtn = [...document.querySelectorAll('button')]
    .find(b => b.textContent.includes('BOM 등록 완료'));
  if (!saveBtn) return;

  saveBtn.addEventListener('click', async () => {
    const menu = (document.getElementById('menu-name') || {}).value?.trim();
    if (!menu) { alert('메뉴명을 입력해주세요.'); return; }

    const cards = document.querySelectorAll('#ingredient-container > div');
    const ings = [];
    cards.forEach(c => {
      const name = c.querySelector('input[type="text"]')?.value?.trim();
      const qty = parseFloat(c.querySelector('input[type="number"]')?.value);
      const unit = c.querySelector('select')?.value;
      if (name && qty > 0) ings.push({ name, qty, unit });
    });
    if (!ings.length) { alert('식재료를 1개 이상 입력해주세요.'); return; }

    const boms = window.ctStore ? await ctStore.getMenus() : JSON.parse(localStorage.getItem('ct_bom') || '[]');
    boms.push({ menu, ings, saved: new Date().toISOString().slice(0, 10) });
    if (window.ctStore) {
      await ctStore.setMenus(boms);
    } else {
      localStorage.setItem('ct_bom', JSON.stringify(boms));
    }
    alert(`'${menu}' BOM이 등록되었습니다.\n홈 화면에서 AI 원가 변동 예측을 확인하세요.`);
    location.href = '/app';
  });
});
