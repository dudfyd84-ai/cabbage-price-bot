// BOM 등록 화면: 메뉴·식재료를 localStorage에 저장하고 홈 원가 카드와 연동
document.addEventListener('DOMContentLoaded', () => {
  const saveBtn = [...document.querySelectorAll('button')]
    .find(b => b.textContent.includes('BOM 등록 완료'));
  if (!saveBtn) return;

  saveBtn.addEventListener('click', () => {
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

    const boms = JSON.parse(localStorage.getItem('ct_bom') || '[]');
    boms.push({ menu, ings, saved: new Date().toISOString().slice(0, 10) });
    localStorage.setItem('ct_bom', JSON.stringify(boms));
    alert(`'${menu}' BOM이 등록되었습니다.\n홈 화면에서 AI 원가 변동 예측을 확인하세요.`);
    location.href = '/app';
  });
});
