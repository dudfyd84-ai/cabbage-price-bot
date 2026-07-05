// Stitch 화면들의 placeholder 앵커(href="#")를 실제 라우트로 연결하는 공통 네비 스크립트
document.addEventListener('DOMContentLoaded', () => {
  const ROUTES = {
    '홈': '/app', 'Home': '/app',
    '예측 분석': '/app/item-analysis', 'Predictions': '/app/item-analysis',
    '스마트 딜': '/app/deals', 'Smart Deal': '/app/deals',
    '내 정보': '/app/plan', 'My Page': '/app/plan',
    '인벤토리': '/app/inventory', 'Inventory': '/app/inventory',
    '알림 설정': '/app/alerts',
    '주문 관리': '/app/orders',
    '주문 내역': '/app/orders',
    '시장 동향': '/',
    '인사이트': '/app/item-analysis',
  };
  document.querySelectorAll('a, button').forEach(el => {
    const t = (el.textContent || '').trim();
    for (const k in ROUTES) {
      if (t === k || t.endsWith(k)) {
        el.addEventListener('click', e => { e.preventDefault(); location.href = ROUTES[k]; });
        return;
      }
    }
    if (t.includes('선매입') || t.includes('대체재') || t.includes('특가')) {
      el.addEventListener('click', e => { e.preventDefault(); location.href = '/app/deals'; });
      return;
    }
    if (t.includes('BOM') && t.includes('등록')) {
      el.addEventListener('click', e => { e.preventDefault(); location.href = '/app/bom-register'; });
      return;
    }
    if (t.startsWith('arrow_back')) {
      el.addEventListener('click', e => {
        e.preventDefault();
        history.length > 1 ? history.back() : (location.href = '/app');
      });
    }
  });
});
