// 주문 관리 내역 실데이터 연동 및 필터링 로직
document.addEventListener('DOMContentLoaded', () => {
  const fmt = n => Math.round(n).toLocaleString();

  // 1) 초기 샘플 데이터 정의 및 localStorage 초기화
  const defaultOrders = [
    {
      id: '#20260718-01',
      date: '2026.07.18',
      status: 'Pending',
      merchant: '서울 마늘 도매상',
      items_text: '깐마늘 20kg',
      price: 150000,
      icon: 'storefront',
      image_url: 'https://images.unsplash.com/photo-1540148426945-6cf22a6b2383?auto=format&fit=crop&w=200&q=80'
    },
    {
      id: '#20260717-02',
      date: '2026.07.17',
      status: 'Shipping',
      merchant: '신선 농장 채소',
      items_text: '대파 10단, 양파 5망',
      price: 84200,
      icon: 'skillet',
      image_url: 'https://images.unsplash.com/photo-1620172671501-c8ee5b501d67?auto=format&fit=crop&w=200&q=80'
    },
    {
      id: '#20260715-01',
      date: '2026.07.15',
      status: 'Completed',
      merchant: '유기농 축산 직거래',
      items_text: '신선 특란 50판',
      price: 210000,
      icon: 'egg',
      image_url: 'https://images.unsplash.com/photo-1516448620398-c5f44bf9f441?auto=format&fit=crop&w=200&q=80'
    },
    {
      id: '#20260712-03',
      date: '2026.07.12',
      status: 'Cancelled',
      merchant: '글로벌 곡물 상사',
      items_text: '밀가루 10포대',
      price: 1120000,
      icon: 'storefront',
      image_url: 'https://images.unsplash.com/photo-1574316071802-0d684efa7bf5?auto=format&fit=crop&w=200&q=80'
    }
  ];

  let allOrders = JSON.parse(localStorage.getItem('ct_orders'));
  if (!allOrders || allOrders.length === 0) {
    allOrders = defaultOrders;
    localStorage.setItem('ct_orders', JSON.stringify(allOrders));
  } else {
    // 기존 로컬스토리지 데이터에 새 필드(image_url) 병합 마이그레이션
    let updated = false;
    allOrders = allOrders.map(o => {
      const def = defaultOrders.find(d => d.id === o.id);
      if (def && !o.image_url) {
        o.image_url = def.image_url;
        updated = true;
      }
      return o;
    });
    if (updated) {
      localStorage.setItem('ct_orders', JSON.stringify(allOrders));
    }
  }

  // 프리셋 범위 계산기
  const getPresetRange = (preset) => {
    const today = new Date('2026-07-18');
    const pad = (n) => String(n).padStart(2, '0');
    const format = (d) => `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())}`;

    if (preset === 'today') {
      return { start: format(today), end: format(today) };
    } else if (preset === '3days') {
      const start = new Date(today);
      start.setDate(today.getDate() - 2);
      return { start: format(start), end: format(today) };
    } else if (preset === 'week') {
      const day = today.getDay();
      const diffToMon = day === 0 ? -6 : 1 - day;
      const mon = new Date(today);
      mon.setDate(today.getDate() + diffToMon);
      const sun = new Date(mon);
      sun.setDate(mon.getDate() + 6);
      return { start: format(mon), end: format(sun) };
    } else if (preset === 'month') {
      const start = new Date(today.getFullYear(), today.getMonth(), 1);
      const end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
      return { start: format(start), end: format(end) };
    }
    return null;
  };

  // 프리셋 UI 상태 동기화
  const updatePresetUI = (currentRange) => {
    const presets = ['today', '3days', 'week', 'month'];
    presets.forEach(p => {
      const btn = document.querySelector(`[data-preset="${p}"]`);
      if (!btn) return;
      const range = getPresetRange(p);
      const active = currentRange && currentRange.start === range.start && currentRange.end === range.end;
      if (active) {
        btn.className = 'flex-1 min-h-[44px] px-4 py-2.5 rounded-full text-label-sm font-label-sm bg-primary text-white transition-all whitespace-nowrap shadow-sm font-semibold';
      } else {
        btn.className = 'flex-1 min-h-[44px] px-4 py-2.5 rounded-full text-label-sm font-label-sm bg-white border border-outline-variant text-on-surface-variant transition-all whitespace-nowrap hover:bg-surface-container-low';
      }
    });
  };

  let orders = allOrders;
  const dateRange = JSON.parse(localStorage.getItem('ct_orders_date_range'));
  if (dateRange && dateRange.start && dateRange.end) {
    const el = document.getElementById('date-range-text');
    if (el) el.textContent = `${dateRange.start} ~ ${dateRange.end}`;
    
    const start = new Date(dateRange.start.replace(/\./g, '-'));
    const end = new Date(dateRange.end.replace(/\./g, '-'));
    orders = allOrders.filter(o => {
      const od = new Date(o.date.replace(/\./g, '-'));
      return od >= start && od <= end;
    });
  }
  updatePresetUI(dateRange);

  let activeFilter = 'all'; // all, Pending, Shipping, Completed, Cancelled

  // 2) 카운트 갱신 함수
  const updateCounts = () => {
    const counts = {
      all: orders.length,
      Pending: orders.filter(o => o.status === 'Pending').length,
      Shipping: orders.filter(o => o.status === 'Shipping').length,
      Completed: orders.filter(o => o.status === 'Completed').length,
      Cancelled: orders.filter(o => o.status === 'Cancelled').length
    };

    const elAll = document.querySelector('#chip-all span');
    const elPending = document.querySelector('#chip-pending span');
    const elShipping = document.querySelector('#chip-shipping span');
    const elCompleted = document.querySelector('#chip-completed span');
    const elCancelled = document.querySelector('#chip-cancelled span');

    if (elAll) elAll.textContent = `전체 내역: ${counts.all}`;
    if (elPending) elPending.textContent = `대기 중: ${counts.Pending}`;
    if (elShipping) elShipping.textContent = `배송 중: ${counts.Shipping}`;
    if (elCompleted) elCompleted.textContent = `완료됨: ${counts.Completed}`;
    if (elCancelled) elCancelled.textContent = `취소됨: ${counts.Cancelled}`;
  };

  // 3) 주문 리스트 렌더링 함수
  const renderOrders = () => {
    const listContainer = document.getElementById('orders-list');
    if (!listContainer) return;

    listContainer.innerHTML = '';

    const filtered = activeFilter === 'all' 
      ? orders 
      : orders.filter(o => o.status === activeFilter);

    if (filtered.length === 0) {
      listContainer.innerHTML = `
        <div class="text-center py-12 opacity-60">
          <span class="material-symbols-outlined text-4xl mb-2">inbox</span>
          <p class="font-body-sm text-body-sm">해당 조건의 주문 내역이 없습니다.</p>
        </div>
      `;
      return;
    }

    filtered.forEach(order => {
      // 상태별 스타일 매핑
      let statusBadgeClass = '';
      let statusDotClass = '';
      if (order.status === 'Completed') {
        statusBadgeClass = 'bg-teal-50 text-teal-700 border-teal-100';
        statusDotClass = 'bg-teal-500';
      } else if (order.status === 'Shipping') {
        statusBadgeClass = 'bg-secondary-fixed text-on-secondary-fixed-variant border-secondary-container/30';
        statusDotClass = 'bg-secondary';
      } else if (order.status === 'Pending') {
        statusBadgeClass = 'bg-surface-container-high text-outline';
        statusDotClass = 'bg-outline';
      } else {
        statusBadgeClass = 'bg-error-container text-on-error-container';
        statusDotClass = 'bg-error';
      }

      // 카드 엘리먼트 생성
      const card = document.createElement('div');
      card.className = `glass-panel rounded-xl p-4 transition-all relative ${order.status === 'Pending' ? 'opacity-90' : order.status === 'Cancelled' ? 'opacity-60' : ''}`;
      
      // 액션 버튼 영역 생성 (대기중이거나 배송중일때 상태 변경 가능)
      let actionButtonsHtml = '';
      if (order.status === 'Pending') {
        actionButtonsHtml = `
          <div class="mt-3 pt-3 border-t border-outline-variant/10 flex gap-2 justify-end">
            <button class="btn-cancel px-3 py-1.5 rounded-lg border border-error text-error text-label-sm font-label-sm hover:bg-error-container/20 transition-all">주문 취소</button>
            <button class="btn-start px-3 py-1.5 rounded-lg bg-primary text-white text-label-sm font-label-sm hover:opacity-90 transition-all">배송 시작</button>
          </div>
        `;
      } else if (order.status === 'Shipping') {
        actionButtonsHtml = `
          <div class="mt-3 pt-3 border-t border-outline-variant/10 flex gap-2 justify-end">
            <button class="btn-complete px-3 py-1.5 rounded-lg bg-secondary text-white text-label-sm font-label-sm hover:opacity-90 transition-all">배송 완료</button>
          </div>
        `;
      }

      card.innerHTML = `
        <div class="flex justify-between items-start mb-3">
          <div class="space-y-1">
            <p class="font-data-mono text-label-sm text-outline">Order ID: ${order.id}</p>
            <p class="font-label-md text-label-md text-on-surface">${order.date}</p>
          </div>
          <span class="px-3 py-1 rounded-lg font-label-sm text-label-sm flex items-center gap-1 border ${statusBadgeClass}">
            <span class="w-1.5 h-1.5 rounded-full ${statusDotClass}"></span>
            ${order.status}
          </span>
        </div>
        <div class="flex items-center gap-3 py-3 border-y border-outline-variant/20">
          <div class="w-12 h-12 rounded-lg overflow-hidden bg-surface-container flex items-center justify-center flex-shrink-0">
            ${order.image_url ? 
              `<img src="${order.image_url}" class="w-full h-full object-cover" alt="${order.merchant}" />` : 
              `<span class="material-symbols-outlined text-primary text-2xl">${order.icon || 'storefront'}</span>`
            }
          </div>
          <div>
            <p class="font-headline-md text-body-md font-semibold text-on-surface">${order.merchant}</p>
            <p class="font-body-sm text-body-sm text-on-surface-variant">${order.items_text}</p>
          </div>
        </div>
        <div class="mt-3 flex justify-between items-center">
          <p class="font-body-sm text-body-sm text-outline">총 결제 금액</p>
          <p class="font-headline-md text-headline-md text-primary">₩${fmt(order.price)}</p>
        </div>
        ${actionButtonsHtml}
      `;

      // 버튼 이벤트 리스너 추가
      const btnCancel = card.querySelector('.btn-cancel');
      const btnStart = card.querySelector('.btn-start');
      const btnComplete = card.querySelector('.btn-complete');

      if (btnCancel) {
        btnCancel.addEventListener('click', (e) => {
          e.stopPropagation();
          updateOrderStatus(order.id, 'Cancelled');
        });
      }
      if (btnStart) {
        btnStart.addEventListener('click', (e) => {
          e.stopPropagation();
          updateOrderStatus(order.id, 'Shipping');
        });
      }
      if (btnComplete) {
        btnComplete.addEventListener('click', (e) => {
          e.stopPropagation();
          updateOrderStatus(order.id, 'Completed');
        });
      }

      listContainer.appendChild(card);
    });
  };

  // 4) 상태 업데이트 함수
  const updateOrderStatus = (orderId, newStatus) => {
    allOrders = allOrders.map(o => {
      if (o.id === orderId) {
        return { ...o, status: newStatus };
      }
      return o;
    });
    localStorage.setItem('ct_orders', JSON.stringify(allOrders));

    // 날짜 필터 재적용
    if (dateRange && dateRange.start && dateRange.end) {
      const start = new Date(dateRange.start.replace(/\./g, '-'));
      const end = new Date(dateRange.end.replace(/\./g, '-'));
      orders = allOrders.filter(o => {
        const od = new Date(o.date.replace(/\./g, '-'));
        return od >= start && od <= end;
      });
    } else {
      orders = allOrders;
    }

    updateCounts();
    renderOrders();
  };

  // 5) 칩 클릭 필터 제어 함수
  const setupFilterListeners = () => {
    const chipsMap = {
      'chip-all': 'all',
      'chip-pending': 'Pending',
      'chip-shipping': 'Shipping',
      'chip-completed': 'Completed',
      'chip-cancelled': 'Cancelled'
    };

    Object.keys(chipsMap).forEach(id => {
      const btn = document.getElementById(id);
      if (btn) {
        btn.addEventListener('click', () => {
          // 모든 칩의 활성화 스타일 제거 및 비활성화 스타일 적용
          Object.keys(chipsMap).forEach(key => {
            const b = document.getElementById(key);
            if (b) {
              b.className = 'flex-shrink-0 px-4 py-2 rounded-full bg-white border border-outline-variant text-on-surface-variant flex items-center gap-2';
            }
          });
          // 현재 클릭된 칩의 활성화 스타일 적용
          btn.className = 'flex-shrink-0 px-4 py-2 rounded-full bg-primary text-white flex items-center gap-2 shadow-md';
          
          activeFilter = chipsMap[id];
          renderOrders();
        });
      }
    });
  };

  // 6) 날짜 및 필터 버튼 클릭 시 이동 연동
  const dateRangeText = document.getElementById('date-range-text');
  const filterBtn = document.querySelector('button.bg-secondary-container');
  const goToFilter = () => {
    location.href = location.pathname.startsWith('/app') ? '/app/orders-filter' : 'orders-filter.html';
  };
  if (dateRangeText) {
    const parentPanel = dateRangeText.closest('.glass-panel');
    if (parentPanel) {
      parentPanel.style.cursor = 'pointer';
      parentPanel.addEventListener('click', goToFilter);
    }
  }
  if (filterBtn) {
    filterBtn.addEventListener('click', goToFilter);
  }

  // 7) 프리셋 버튼 클릭 이벤트 바인딩
  const setupPresetListeners = () => {
    const presets = ['today', '3days', 'week', 'month'];
    presets.forEach(p => {
      const btn = document.querySelector(`[data-preset="${p}"]`);
      if (btn) {
        btn.addEventListener('click', () => {
          const range = getPresetRange(p);
          localStorage.setItem('ct_orders_date_range', JSON.stringify(range));
          
          const el = document.getElementById('date-range-text');
          if (el) el.textContent = `${range.start} ~ ${range.end}`;
          
          const start = new Date(range.start.replace(/\./g, '-'));
          const end = new Date(range.end.replace(/\./g, '-'));
          orders = allOrders.filter(o => {
            const od = new Date(o.date.replace(/\./g, '-'));
            return od >= start && od <= end;
          });
          
          updatePresetUI(range);
          updateCounts();
          renderOrders();
        });
      }
    });
  };

  // 초기 로드 시 구동
  setupFilterListeners();
  setupPresetListeners();
  updateCounts();
  renderOrders();
});
