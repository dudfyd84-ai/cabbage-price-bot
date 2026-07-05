// Stitch 화면 공통 셸: 네비 라우팅 + 온보딩 흐름 + 알림 토글 저장 + 데모 배지
document.addEventListener('DOMContentLoaded', () => {
  const path = location.pathname;

  // ── 1) 공통 네비: placeholder 앵커를 텍스트 매칭으로 라우팅 ──
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
    if (t.includes('BOM') && t.includes('등록') && !t.includes('완료')) {
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

  // ── 2) 온보딩: 시작/가입/로그인 → 매장 등록으로 ──
  if (path.endsWith('/onboarding')) {
    document.querySelectorAll('a, button').forEach(el => {
      const t = (el.textContent || '').trim();
      if (t.includes('시작하기') || t.includes('이메일로 가입') || t === '로그인' ||
          t.includes('Google') || t.includes('카카오')) {
        el.addEventListener('click', e => { e.preventDefault(); location.href = '/app/store-register'; });
      }
    });
  }

  // ── 3) 매장 등록: 입력 저장 → 홈 ──
  if (path.endsWith('/store-register')) {
    const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('다음 단계로'));
    if (btn) btn.addEventListener('click', e => {
      e.preventDefault();
      const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
      const name = inputs[0]?.value?.trim();
      if (!name) { alert('식당 이름을 입력해주세요.'); return; }
      const addr = inputs[1]?.value?.trim() || '';
      const cat = document.querySelector('#cuisine-chips .bg-primary, #cuisine-chips [class*="selected"]')?.textContent?.trim() || '';
      localStorage.setItem('ct_store', JSON.stringify({ name, addr, cat }));
      location.href = '/app';
    });
  }

  // ── 4) 알림 설정: 토글 상태 저장·복원 ──
  if (path.endsWith('/alerts')) {
    const boxes = document.querySelectorAll('input[type="checkbox"]');
    const saved = JSON.parse(localStorage.getItem('ct_alerts') || 'null');
    boxes.forEach((b, i) => {
      if (saved && typeof saved[i] === 'boolean') b.checked = saved[i];
      b.addEventListener('change', () => {
        localStorage.setItem('ct_alerts', JSON.stringify([...boxes].map(x => x.checked)));
      });
    });
  }

  // ── 5) 데모 화면 배지: 거래·결제 데이터 미연동 화면 표기 ──
  const DEMO = ['/app/deals', '/app/plan', '/app/orders', '/app/orders-table', '/app/orders-filter'];
  if (DEMO.includes(path)) {
    const h = document.querySelector('header h1, header h2, main h1, main h2');
    if (h) {
      const tag = document.createElement('span');
      tag.textContent = '데모';
      tag.style.cssText = 'font-size:11px;font-weight:700;color:#92400e;background:#fef3c7;border-radius:9999px;padding:2px 8px;vertical-align:middle;margin-left:8px;';
      h.appendChild(tag);
    }
  }

  // ── 6) 등록된 매장명 반영 (전 화면 헤더의 '나의 레스토랑') ──
  try {
    const store = JSON.parse(localStorage.getItem('ct_store') || 'null');
    if (store && store.name) {
      document.querySelectorAll('span, div').forEach(el => {
        if (el.children.length === 0 && el.textContent.trim() === '나의 레스토랑') el.textContent = store.name;
      });
    }
  } catch (e) {}
});
