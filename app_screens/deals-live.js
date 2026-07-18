// 스마트 딜 화면: /api/dashboard(예측 11품목) 기반 실데이터 추천 연동 및 필터/카테고리 기능
// app.py에서 </body> 직전에 <script src>로 주입됨 → DOM이 이미 준비된 상태이므로 DOMContentLoaded 불필요
(function () {
  const fmt = n => Math.round(n).toLocaleString();

  // 품목별 판매처 및 아이콘, 이미지 매핑 테이블
  const ITEM_META = {
    '배추': {
      merchant: '강원 고랭지 배추 영농조합',
      icon: 'spa',
      img: 'https://lh3.googleusercontent.com/aida-public/AB6AXuDT-w6q7N67i_2-Mspm4_Hn-H9c4uS15n36B-P91lJ2aWv9i25XN5y6uW3p=w600'
    },
    '무': {
      merchant: '제주 구좌 무 생산협동조합',
      icon: 'spa',
      img: 'https://lh3.googleusercontent.com/aida-public/AB6AXuDT-w6q7N67i_2-Mspm4_Hn-H9c4uS15n36B-P91lJ2aWv9i25XN5y6uW3p=w600'
    },
    '양파': {
      merchant: '무안 양파 도매 유통',
      icon: 'skillet',
      img: 'https://lh3.googleusercontent.com/aida-public/AB6AXuDtz77ReFFcIxJpFV7XgBAGUZSKDae_iJSyE0Pfo7W24uIMQwEivC7Jo0sQyH4gRVUEH9wTUaxwsJKe2I4Q2WlZztNSMZdEY398tQ2TIV8s3aIDmZ4DOtMz4Sjx51dU5lPSG1OxqWO8cH2pLEolhsgkyz_OLI13BcZs5ePNz-2pkQDz9Cq5Hk5F2RaOhDr09_d28eIpOkKLMmZEVb8dytCBQEnk7PrwwcCowC17LBfMcX1wiN-WQLqn'
    },
    '대파': {
      merchant: '진도 대파 영농조합',
      icon: 'skillet',
      img: 'https://lh3.googleusercontent.com/aida-public/AB6AXuCPpmp_jaArieWFbGammzhBielNygAt9FBasoHCHPRs2zHx_z7lbCSzt63ywtXePaihn1YUZRRPwAS1H1AfDPgFZ3xLuXvAaZQ8eeJCKNq9UkiaaG3VGaCYJuSEGj6hJGGIS6Xs4eT4mKXPEp3rJjMl0IuFHvKsTe3e0vHrjXgcrdWdJa15N7zHRnQ91aNQaHxNvbYrh1ePiOhutaoG6IWx6mcSv3GKm8NGUVWe1JT--zP7c29cxanK'
    },
    '마늘': {
      merchant: '의성 마늘 생산협동조합',
      icon: 'storefront',
      img: 'https://lh3.googleusercontent.com/aida-public/AB6AXuBt5P16rDGfBRHSbENGIbAKRKblncuvhln9bs0xmEI9WkkyAzqfq33iI78Bba6_2kVq6PzxuIi4HgWmaVv_XDdia9gIDLOicj6nr6ExK2WSoXbzUXDOQTS0ZiXFiiZ-kkDeZpzFeVUFnD8-Ar6TYgoe-me3c8PaOQHcQrcGCDVGc7GLVx9PXQB-Y8zqS6nNo73Mua5kZxZkS-ak17sjTEgFgHHGwFH4SdfeU0oG16EPIsq90Hamy4g9'
    },
    '당근': {
      merchant: '평창 당근 유통조합',
      icon: 'skillet',
      img: 'https://lh3.googleusercontent.com/aida-public/AB6AXuDT-w6q7N67i_2-Mspm4_Hn-H9c4uS15n36B-P91lJ2aWv9i25XN5y6uW3p=w600'
    },
    '오이': {
      merchant: '천안 아우내 오이 농가',
      icon: 'skillet',
      img: 'https://lh3.googleusercontent.com/aida-public/AB6AXuDT-w6q7N67i_2-Mspm4_Hn-H9c4uS15n36B-P91lJ2aWv9i25XN5y6uW3p=w600'
    },
    '시금치': {
      merchant: '남해 시금치 유통본부',
      icon: 'spa',
      img: 'https://lh3.googleusercontent.com/aida-public/AB6AXuDT-w6q7N67i_2-Mspm4_Hn-H9c4uS15n36B-P91lJ2aWv9i25XN5y6uW3p=w600'
    },
    '상추': {
      merchant: '논산 상추 영농조합',
      icon: 'spa',
      img: 'https://lh3.googleusercontent.com/aida-public/AB6AXuDT-w6q7N67i_2-Mspm4_Hn-H9c4uS15n36B-P91lJ2aWv9i25XN5y6uW3p=w600'
    },
    '사과': {
      merchant: '충주 사과 농협',
      icon: 'egg',
      img: 'https://lh3.googleusercontent.com/aida-public/AB6AXuD9bR071NARcXAfy8kJAA_2xlFQ1k9fJi6Vt7xRcYTF56ukIGz9SYhXqBeoKb9M_lZIwassPecJZ-NLvwwdv7ubs2H7ej3OgrdP0Y-LSOTCANiTKWJS0LCrbaykWoBQCAQ4nawquYkrzT4DxmO-9iJyht1tLOPlVvdJbQ5eFz1O5Z3aF8LRyj_dsMIePnSKTpSZXJkYBWP3-u6uZN-DL_fWVIDyMrOlPBiwrcWpeyXn0bkfinE2wnLL'
    },
    '배': {
      merchant: '나주 배 원예농협',
      icon: 'egg',
      img: 'https://lh3.googleusercontent.com/aida-public/AB6AXuD9bR071NARcXAfy8kJAA_2xlFQ1k9fJi6Vt7xRcYTF56ukIGz9SYhXqBeoKb9M_lZIwassPecJZ-NLvwwdv7ubs2H7ej3OgrdP0Y-LSOTCANiTKWJS0LCrbaykWoBQCAQ4nawquYkrzT4DxmO-9iJyht1tLOPlVvdJbQ5eFz1O5Z3aF8LRyj_dsMIePnSKTpSZXJkYBWP3-u6uZN-DL_fWVIDyMrOlPBiwrcWpeyXn0bkfinE2wnLL'
    }
  };

  // 전역 상태 변수
  let allRawItems = [];
  let currentCategory = 'all'; // all, veg, fruit
  let currentSort = 'rise_desc'; // rise_desc, savings_desc, price_asc
  let currentLevel = 'all'; // all, 위험, 주의, 안정

  // 카테고리 정의
  const getCategoryOf = (name) => {
    if (['사과', '배'].includes(name)) return 'fruit';
    return 'veg'; // 기본적으로 채소류 분류
  };

  // 드롭다운 모달 표시 함수들
  const toggleDropdown = (btn, dropdownId, options, onSelect) => {
    // 기존 활성화된 드롭다운 제거
    document.querySelectorAll('.ct-dropdown-menu').forEach(el => {
      if (el.id !== dropdownId) el.remove();
    });

    let dropdown = document.getElementById(dropdownId);
    if (dropdown) {
      dropdown.remove();
      return;
    }

    dropdown = document.createElement('div');
    dropdown.id = dropdownId;
    dropdown.className = 'ct-dropdown-menu absolute right-0 mt-2 w-48 bg-surface-container-lowest dark:bg-inverse-surface border border-outline-variant rounded-xl shadow-xl z-50 p-md space-y-xs transition-all duration-200';
    
    // 버튼 위치를 기준으로 상대적 좌표 정렬을 위해 버튼의 부모 또는 상위 relative 박스 내에 추가
    btn.parentElement.appendChild(dropdown);

    options.forEach(opt => {
      const itemBtn = document.createElement('button');
      itemBtn.className = `w-full text-left px-md py-sm rounded-lg font-label-md text-label-md hover:bg-surface-container transition-all flex justify-between items-center ${opt.active ? 'text-primary dark:text-primary-fixed-dim font-bold bg-surface-container-low' : 'text-on-surface'}`;
      itemBtn.innerHTML = `<span>${opt.label}</span>`;
      if (opt.active) {
        itemBtn.innerHTML += `<span class="material-symbols-outlined text-[18px]">check</span>`;
      }
      itemBtn.addEventListener('click', () => {
        onSelect(opt.value);
        dropdown.remove();
      });
      dropdown.appendChild(itemBtn);
    });

    // 외부 클릭 시 드롭다운 닫기
    const closeHandler = (e) => {
      if (!btn.contains(e.target) && !dropdown.contains(e.target)) {
        dropdown.remove();
        document.removeEventListener('click', closeHandler);
      }
    };
    // 시간 지연을 약간 두어 클릭 즉시 닫히지 않게 조절
    setTimeout(() => {
      document.addEventListener('click', closeHandler);
    }, 10);
  };

  const renderDealsGrid = () => {
    const grid = document.getElementById('predictive-deals-grid');
    if (!grid) return;

    // 1) 필터링
    let filtered = allRawItems.filter(item => {
      // 카테고리 필터
      if (currentCategory !== 'all' && getCategoryOf(item.name) !== currentCategory) {
        return false;
      }
      // 예측 위험도 필터
      if (currentLevel !== 'all' && item.level !== currentLevel) {
        return false;
      }
      return true;
    });

    // 2) 정렬
    filtered.sort((a, b) => {
      if (currentSort === 'rise_desc') {
        return b.r30 - a.r30; // 상승률 높은순
      } else if (currentSort === 'savings_desc') {
        const aSavings = a.p30 - a.cur;
        const bSavings = b.p30 - b.cur;
        return bSavings - aSavings; // 절감금액 높은순
      } else if (currentSort === 'price_asc') {
        return a.cur - b.cur; // 가격 낮은순
      }
      return 0;
    });

    // 3) 렌더링
    grid.innerHTML = '';
    if (!filtered.length) {
      grid.innerHTML = `<div class="col-span-2 text-center py-12 text-on-surface-variant">조건에 맞는 추천 상품이 없습니다.</div>`;
      return;
    }

    filtered.forEach(item => {
      const meta = ITEM_META[item.name] || { merchant: '종합 식자재 도매상', icon: 'storefront', img: '' };
      const savingsPct = Math.max(5, item.r30);
      const originPrice = item.p30;
      const dealPrice = item.cur;

      const card = document.createElement('div');
      card.className = 'glass-card p-md rounded-xl flex flex-col hover:shadow-lg transition-all group';
      card.innerHTML = `
        <div class="h-32 rounded-lg overflow-hidden mb-sm bg-surface-container">
          <img class="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500" src="${meta.img}" alt="${item.name}"/>
        </div>
        <div class="flex justify-between items-start mb-xs">
          <h4 class="font-label-md text-label-md text-on-surface">${item.name} (${item.unit})</h4>
          <span class="text-error font-label-sm text-label-sm">+${item.r30}% 예상</span>
        </div>
        <div class="flex items-center gap-xs mb-md">
          <span class="bg-secondary-container/20 text-secondary font-label-sm text-label-sm px-2 py-0.5 rounded">Predictive Savings ${savingsPct}%</span>
          <span class="bg-surface-variant text-on-surface-variant font-label-sm text-label-sm px-2 py-0.5 rounded">${item.level}</span>
        </div>
        <div class="mt-auto">
          <div class="flex justify-between items-end mb-sm">
            <div>
              <p class="text-on-surface-variant line-through text-label-sm">${fmt(originPrice)}원</p>
              <p class="font-headline-md text-headline-md text-primary">${fmt(dealPrice)}원</p>
            </div>
          </div>
          <button class="w-full py-2 bg-primary-container text-on-primary-container font-label-md text-label-md rounded-lg active:opacity-80 active:scale-95 transition-all">구매하기</button>
        </div>
      `;

      // data-ct-deal 속성으로 구매 버튼 마킹 (nav.js 라우팅 충돌 방지)
      const btn = card.querySelector('button');
      if (btn) {
        btn.setAttribute('data-ct-deal', '1');
        btn.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopImmediatePropagation();
          if (typeof window.placeDealOrder === 'function') {
            window.placeDealOrder(meta.merchant, `${item.name} ${item.unit}`, dealPrice, meta.icon, meta.img);
          }
        }, true); // 캡처링 단계에서 먼저 처리
      }
      grid.appendChild(card);
    });
  };

  // API 데이터 로드 및 초기 설정
  fetch('/api/dashboard')
    .then(r => r.json())
    .then(data => {
      // 상승률 내림차순 정렬 및 전역 변수 할당
      const items = [...data.items].sort((a, b) => b.r30 - a.r30);
      if (!items.length) return;

      const top = items[0];
      // Hero (긴급 특가)는 전체 품목 1위로 유지
      const hero = document.getElementById('featured-deal-hero');
      if (hero && top) {
        const meta = ITEM_META[top.name] || { merchant: '산지 유통 영농조합', icon: 'storefront', img: '' };
        hero.querySelector('h3').textContent = `${top.name} 가격 상승 경보! 30일 뒤 ${top.r30}% 폭등 예상.`;
        hero.querySelector('p.font-body-md').textContent = `가격 인상 전, 산지 직송가로 미리 확보하세요. 현재 250 유닛 남음.`;
        hero.querySelector('.hero-stock-text').textContent = `남은 수량: 250 / 1000 유닛`;
        hero.querySelector('.hero-progress-pct').textContent = `75% 판매 완료`;
        hero.querySelector('.hero-progress-bar').style.width = '75%';
        if (meta.img) {
          hero.querySelector('.hero-image').setAttribute('src', meta.img);
        }

        const heroBtn = hero.querySelector('button');
        if (heroBtn) {
          const dealPrice = Math.round(top.cur * 0.9);
          // data 속성을 API 데이터로 업데이트 (인라인 스크립트가 읽을 수 있도록)
          heroBtn.setAttribute('data-ct-deal', '1');
          heroBtn.setAttribute('data-merchant', meta.merchant);
          heroBtn.setAttribute('data-item', `${top.name} ${top.unit} (긴급 특가)`);
          heroBtn.setAttribute('data-price', String(dealPrice));
          heroBtn.setAttribute('data-image', meta.img || '');
          heroBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopImmediatePropagation();
            if (typeof window.placeDealOrder === 'function') {
              window.placeDealOrder(meta.merchant, `${top.name} ${top.unit} (긴급 특가)`, dealPrice, meta.icon, meta.img);
            }
          }, true); // 캡처링 단계에서 먼저 처리
        }
      }

      // 그리드용 리스트 저장 (상위 1위 품목을 제외할지 여부는 비즈니스 로직에 따르나, 
      // 필터 적용을 원활히 하기 위해 Hero와 중복을 피하기 위해 slice(1)로 초기설정)
      allRawItems = items.slice(1);

      // 초기 그리드 렌더링
      renderDealsGrid();

      // 구매 시점 시뮬레이션 문구 업데이트
      const activeRisers = items.filter(i => i.r30 > 0);
      const avgRise = activeRisers.length ? Math.round(activeRisers.reduce((acc, cur) => acc + cur.r30, 0) / activeRisers.length) : 18.5;
      const simText = document.querySelector('main p.text-on-surface-variant');
      if (simText) {
        simText.innerHTML = `현재 시점에서 구매 시 향후 30일 대비 평균 <span class="text-primary font-bold">${avgRise}%</span> 예산을 절감할 수 있습니다.`;
      }
    })
    .catch(err => {
      console.error("스마트 딜 가격 예측 데이터 로드 실패:", err);
    });

  // 카테고리 드롭다운 이벤트 연결
  const catBtn = document.getElementById('deals-category-btn');
  if (catBtn) {
    catBtn.addEventListener('click', (e) => {
      e.preventDefault();
      const options = [
        { label: '전체 품목', value: 'all', active: currentCategory === 'all' },
        { label: '채소류', value: 'veg', active: currentCategory === 'veg' },
        { label: '과일류', value: 'fruit', active: currentCategory === 'fruit' }
      ];
      toggleDropdown(catBtn, 'deals-category-dropdown', options, (val) => {
        currentCategory = val;
        // 선택된 값에 따른 라벨 변경 반영
        const labelMap = { all: '카테고리', veg: '채소류', fruit: '과일류' };
        catBtn.innerHTML = `${labelMap[val]} <span class="material-symbols-outlined text-[16px]">arrow_drop_down</span>`;
        renderDealsGrid();
      });
    });
  }

  // 필터 드롭다운 이벤트 연결 (정렬 및 위험도 필터 포함)
  const filterBtn = document.getElementById('deals-filter-btn');
  if (filterBtn) {
    filterBtn.addEventListener('click', (e) => {
      e.preventDefault();
      const options = [
        { label: '상승률 높은순', value: 'sort_rise', active: currentSort === 'rise_desc' && currentLevel === 'all' },
        { label: '절감 금액순', value: 'sort_savings', active: currentSort === 'savings_desc' && currentLevel === 'all' },
        { label: '가격 낮은순', value: 'sort_price', active: currentSort === 'price_asc' && currentLevel === 'all' },
        { label: '위험 등급만', value: 'filter_danger', active: currentLevel === '위험' },
        { label: '주의 등급만', value: 'filter_warning', active: currentLevel === '주의' },
        { label: '안정 등급만', value: 'filter_stable', active: currentLevel === '안정' }
      ];
      toggleDropdown(filterBtn, 'deals-filter-dropdown', options, (val) => {
        if (val === 'sort_rise') {
          currentSort = 'rise_desc';
          currentLevel = 'all';
        } else if (val === 'sort_savings') {
          currentSort = 'savings_desc';
          currentLevel = 'all';
        } else if (val === 'sort_price') {
          currentSort = 'price_asc';
          currentLevel = 'all';
        } else if (val === 'filter_danger') {
          currentLevel = '위험';
        } else if (val === 'filter_warning') {
          currentLevel = '주의';
        } else if (val === 'filter_stable') {
          currentLevel = '안정';
        }

        const filterLabels = {
          sort_rise: '상승률 높은순',
          sort_savings: '절감 금액순',
          sort_price: '가격 낮은순',
          filter_danger: '위험 등급만',
          filter_warning: '주의 등급만',
          filter_stable: '안정 등급만'
        };
        filterBtn.innerHTML = `${filterLabels[val]} <span class="material-symbols-outlined text-[16px]">arrow_drop_down</span>`;
        renderDealsGrid();
      });
    });
  }
})();
