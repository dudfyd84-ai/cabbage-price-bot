// 홈 대시보드: /api/dashboard(예측 11품목) + /api/retail(전 품목 시세)로 실데이터 렌더링
document.addEventListener('DOMContentLoaded', () => {
  const fmt = n => Math.round(n).toLocaleString();

  const loadHomeData = () => {
    // 0) 로딩 중임을 보이기 위해 기존 스켈레톤 복원
    const bomGrid = document.getElementById('bom-grid');
    if (bomGrid) {
      bomGrid.innerHTML = `
        <div class="skeleton-loader col-span-full grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-md w-full">
            <div class="glass-card rounded-xl p-md space-y-md animate-pulse">
                <div class="flex justify-between items-start">
                    <div class="w-12 h-12 rounded bg-surface-container"></div>
                    <div class="h-6 bg-surface-container rounded w-1/3"></div>
                </div>
                <div class="h-5 bg-surface-container rounded w-2/3"></div>
                <div class="h-8 bg-surface-container rounded w-full"></div>
            </div>
        </div>
      `;
    }

    Promise.all([
      (window.ctStore ? ctStore.authFetch('/api/dashboard') : fetch('/api/dashboard')).then(r => {
        if (!r.ok) throw new Error('dashboard API 실패');
        return r.json();
      }),
      fetch('/api/retail').then(r => {
        if (!r.ok) throw new Error('retail API 실패');
        return r.json();
      }).catch(() => ({ groups: {} })),
      window.ctStore ? ctStore.getStockLevels() : Promise.resolve(JSON.parse(localStorage.getItem('ct_stock') || '{}')),
      window.ctStore ? ctStore.getMenus() : Promise.resolve(JSON.parse(localStorage.getItem('ct_bom') || '[]')),
    ]).then(([data, retail, stock, boms]) => {
      const isFree = data.items.some(i => i.p30 === null);
      const items = [...data.items].sort((a, b) => (b.r30 ?? b.r7) - (a.r30 ?? a.r7));
      const risers = items.filter(i => (i.r30 ?? i.r7) > 5);
      const top = items[0];

      // 1) 상단 경보: 다음 달 예상 비용 분석
      try {
        const p = document.querySelector('.bg-error-container p.font-headline-md');
        const h = document.querySelector('.bg-error-container h2');
        if (top && (top.r30 ?? top.r7) > 5) {
          if (p) p.textContent = `+${top.r30 ?? top.r7}% 지출 증가 예상`;
          if (h) h.textContent = `다음 달 예상 비용 분석 · 상승 품목 ${risers.length}개 (${data.date} 기준)`;
        } else {
          if (p) p.textContent = '지출 안정 예상';
          if (h) h.textContent = `다음 달 예상 비용 분석 (${data.date} 기준)`;
        }
      } catch (e) {
        console.error('[홈] 다음 달 예상 비용 렌더링 실패:', e);
      }

      // 2) 재고 확보 알림 카드: 최대 상승 품목 + 입력된 재고 일수 기반 실계산
      try {
        const card = document.querySelector('.bg-secondary');
        const titleEl = document.getElementById('bento-alert-title');
        const descEl = document.getElementById('bento-alert-desc');
        const actionEl = document.getElementById('bento-alert-actions');

        if (card && top && (top.r30 ?? top.r7) > 5) {
          if (titleEl) titleEl.textContent = isFree ? `🔒 유료 전용 분석 (D+30일 예측)` : `${top.name} 가격 30일 뒤 ${top.r30}% 상승 예상!`;
          const sd = parseInt(stock[top.name]) || 0;
          let msg;
          if (isFree) {
             msg = '프로 플랜으로 업그레이드 시 D+30일 예측 데이터와 재고 소진 시점에 맞춘 최적 선매입 가이드를 제공합니다.';
             card.style.cursor = 'pointer';
             card.addEventListener('click', () => location.href='/app/plan');
             if (actionEl) actionEl.style.display = 'none';
          } else if (sd > 0) {
            const dep = sd <= 7 ? top.cur + (top.p7 - top.cur) * sd / 7
              : sd <= 30 ? top.p7 + (top.p30 - top.p7) * (sd - 7) / 23 : top.p30;
            const save = Math.round(dep - top.cur);
            msg = `보유 재고가 D+${sd}에 소진됩니다. 그 시점 예상가 ${fmt(dep)}원/${top.unit}` +
              (save > 0
                ? ` — 지금 ${sd + 14}일치를 선매입하면 ${top.unit}당 ${fmt(save)}원 절감됩니다.`
                : ' — 소진 직전 재구매가 유리합니다.');
            if (actionEl) actionEl.style.display = 'flex';
          } else {
            if (top.ci30 === null) {
              // 무료: D+7은 그대로, D+30 자리에만 잠금 표시
              msg = `현재 ${fmt(top.cur)}원/${top.unit} → 7일 뒤 ${fmt(top.p7)}원 예상. 재고 최적화 화면에서 확인하세요.`;
            } else {
              msg = `현재 ${fmt(top.cur)}원/${top.unit} → 30일 뒤 ${fmt(top.p30)}원 예상` +
                ` (범위 ${fmt(top.ci30[0])}~${fmt(top.ci30[1])}원). 재고 최적화 화면에서 보유 재고를 입력하면 맞춤 제안을 계산합니다.`;
            }
            if (actionEl) actionEl.style.display = 'none';
          }
          if (descEl) descEl.textContent = msg;
        } else if (card) {
          if (titleEl) titleEl.textContent = '지출 안정 예상';
          if (descEl) descEl.textContent = '상승폭이 높은 핵심 농산물 식재료가 없습니다.';
          if (actionEl) actionEl.style.display = 'none';
        }
      } catch (e) {
        console.error('[홈] 재고 확보 알림 렌더링 실패:', e);
      }

      // 3) 핵심 식자재 가격 추이: 상승률 상위 2개 품목의 실제 추이로 SVG 재생성
      try {
        const [a, b] = [items[0], items[1]];
        const trendH3 = [...document.querySelectorAll('h3')].find(h => h.textContent.includes('가격 추이'));
        const headRow = trendH3 ? trendH3.parentElement.parentElement : null;
        if (headRow) {
          const chipSpans = headRow.querySelectorAll('#bento-trend-chips > span');
          if (chipSpans.length >= 2 && a && b) { chipSpans[0].textContent = a.name; chipSpans[1].textContent = b.name; }

          const chartCard = headRow.parentElement;               // 추이 카드 컨테이너로 스코프 한정
          const paths = chartCard.querySelectorAll('svg path');
          const toPath = it => {
            const vals = it.trend.slice(-60).map(t => t.p);
            const mn = Math.min(...vals), mx = Math.max(...vals);
            return vals.map((v, i) => {
              const x = Math.round(i * 1000 / (vals.length - 1));
              const y = mx === mn ? 100 : Math.round(180 - (v - mn) / (mx - mn) * 160);
              return (i === 0 ? 'M' : 'L') + x + ',' + y;
            }).join(' ');
          };
          if (paths.length >= 2 && a && b && a.trend && b.trend) {
            paths[0].setAttribute('d', toPath(a));
            paths[1].setAttribute('d', toPath(b));
          }
          const svgEl = chartCard.querySelector('svg');
          const xlabels = svgEl && svgEl.nextElementSibling ? svgEl.nextElementSibling.querySelectorAll('span') : [];
          const L = ['-60일', '-45일', '-30일', '-15일', '오늘'];
          xlabels.forEach((s, i) => { if (i < L.length) s.textContent = L[i]; });
          
          const descEl = document.getElementById('bento-trend-desc');
          const ov = data.accuracy && data.accuracy.overall && data.accuracy.overall.h30;
          if (descEl) descEl.textContent = '최근 60일 실측 추이 (소매가, 서울)' +
            (ov ? ` · AI 검증 30일 방향 적중률 ${ov.dir_acc}% / 평균오차 ${ov.wape}%` : '');
        }
      } catch (e) {
        console.error('[홈] 핵심 식자재 가격 추이 렌더링 실패:', e);
      }

      // 4) BOM 섹션: 등록 메뉴를 "전 품목 시세 + 예측"으로 원가 계산
      try {
        const h3s = [...document.querySelectorAll('h3')];
        const bomH = h3s.find(h => h.textContent.includes('메뉴별 원가'));
        const grid = document.getElementById('bom-grid');

        if (grid) {
          if (!boms.length) {
            grid.innerHTML = `
              <div class="glass-card rounded-xl p-lg text-center text-on-surface-variant col-span-full flex flex-col items-center justify-center space-y-sm">
                <span class="material-symbols-outlined text-[32px] text-outline">receipt_long</span>
                <div>
                  <p class="font-label-md">아직 등록된 메뉴 BOM이 없습니다.</p>
                  <p class="text-xs text-outline mt-0.5">매장의 메뉴를 등록하여 4주 원가 리스크를 분석해 보세요.</p>
                </div>
                <button onclick="location.href='/app/bom-register'" class="px-md py-sm bg-primary text-white font-label-md rounded-lg active:scale-95 transition-transform hover:brightness-110">
                  메뉴 BOM 등록하러 가기
                </button>
              </div>
            `;
            return;
          }

          // ── 전 품목 가격 사전 구축 ──
          // 단가 파서: 단위 문자열 → {type: g|ml|ea, per1: 1g/1ml/1개당 가격}
          const parseUnit = (unit, price) => {
            const u = (unit || '').toLowerCase();
            let m = u.match(/([\d.]+)\s*(kg|g)(?![a-z])/);
            if (m) return { type: 'g', per1: price / (parseFloat(m[1]) * (m[2] === 'kg' ? 1000 : 1)) };
            m = u.match(/([\d.]+)\s*(l|ml)(?![a-z])/);
            if (m) return { type: 'ml', per1: price / (parseFloat(m[1]) * (m[2] === 'l' ? 1000 : 1)) };
            m = (unit || '').match(/([\d.]+)?\s*(개|구|마리|포기|장|속|단|병|봉|팩)/);
            if (m) return { type: 'ea', per1: price / (parseFloat(m[1]) || 1) };
            return null;
          };
          const norm = s => (s || '').replace(/\(.*?\)|\s/g, '');   // 괄호·공백 제거

          const priceBook = {};   // normName → {now per-base, futRatio, type, label}
          Object.values(retail.groups || {}).flat().forEach(r => {
            const up = parseUnit(r.unit, r.cur);
            if (up) priceBook[norm(r.name)] = { ...up, futRatio: 1, label: r.name, predicted: false };
          });
          items.forEach(i => {   // 예측 11품목은 미래 비율 덮어쓰기
            const up = parseUnit(i.unit, i.cur);
            const fut = isFree ? i.p7 : i.p30;
            if (up) priceBook[norm(i.name)] = {
              ...up, futRatio: i.cur > 0 ? fut / i.cur : 1, label: i.name, predicted: true,
            };
          });

          const calc = bom => {
            let now = 0, fut = 0, unmatched = [], unpredicted = 0, topRise = null;
            bom.ings.forEach(g => {
              const pb = priceBook[norm(g.name)] || (g.kamis ? priceBook[norm(g.kamis)] : null);
              const qBase = g.unit === 'kg' || g.unit === 'l' ? g.qty * 1000 : g.qty;
              const typeOk = pb && ((pb.type === 'g' && (g.unit === 'g' || g.unit === 'kg')) ||
                                    (pb.type === 'ml' && (g.unit === 'ml' || g.unit === 'l')) ||
                                    (pb.type === 'ea' && g.unit === 'ea'));
              if (typeOk) {
                const c = pb.per1 * qBase;
                now += c; fut += c * pb.futRatio;
                if (!pb.predicted) unpredicted += 1;
                const d = c * (pb.futRatio - 1);
                if (!topRise || d > topRise.d) topRise = { name: pb.label, d };
              } else if (g.manualPrice && g.manualPrice > 0) {
                now += g.manualPrice; fut += g.manualPrice;
                // 수동 입력 가격(manualPrice)이 있는 경우 미연동(unmatched) 목록에서 제외
              } else {
                unmatched.push(g.name);
              }
            });
            return { now, fut, unmatched, unpredicted, topRise };
          };

          const tpl = document.querySelector('#bom-grid > div.hidden');
          if (tpl) {
            const tempContainer = document.createDocumentFragment();
            boms.forEach(bom => {
              const c = calc(bom);
              const card = tpl.cloneNode(true);
              card.classList.remove('hidden');
              const img = card.querySelector('[style*="background-image"]');
              if (img) {
                img.style.backgroundImage = 'none';
                img.style.cssText += 'display:flex;align-items:center;justify-content:center;background:#e5eeff;font-weight:700;font-size:20px;color:#003527;';
                img.textContent = bom.menu[0];
              }
              card.querySelector('h4').textContent = bom.menu;

              const pct = c.now > 0 ? Math.round((c.fut - c.now) / c.now * 100) : 0;
              const diff = Math.round(c.fut - c.now);
              const chip = card.querySelector('span.rounded-full');
              if (chip) {
                if (pct > 5) {
                  chip.textContent = `+${pct}% 위험 (+${fmt(diff)}원/인분)`;
                  chip.className = 'font-label-sm text-label-sm px-sm py-xs bg-error-container text-error rounded-full';
                } else if (pct < -5) {
                  chip.textContent = `${pct}% 안정 (${fmt(diff)}원/인분)`;
                  chip.className = 'font-label-sm text-label-sm px-sm py-xs bg-tertiary-container text-on-tertiary-container rounded-full';
                } else {
                  chip.textContent = `변동 미미 (${diff >= 0 ? '+' : ''}${fmt(diff)}원/인분)`;
                  chip.className = 'font-label-sm text-label-sm px-sm py-xs bg-surface-container text-on-surface-variant rounded-full';
                }
              }

              const notes = [];
              if (c.topRise && Math.abs(c.topRise.d) >= 1) notes.push(`주요 원인: ${c.topRise.name} 가격 변동`);
              if (c.unpredicted) notes.push(`현재가 반영 ${c.unpredicted}개(예측 미지원)`);
              if (c.unmatched.length) notes.push(`미연동 ${c.unmatched.join(', ')}`);
              
              const notesEl = card.querySelector('p.font-body-sm');
              if (notesEl) notesEl.textContent = notes.join(' · ') || '재료 변동 없음';

              const priceEl = card.querySelector('.font-data-mono');
              if (priceEl) priceEl.textContent = c.now > 0 ? `₩${fmt(c.fut)}` : '—';
              
              const icon = card.querySelector('.pt-sm span.material-symbols-outlined');
              if (icon) {
                icon.textContent = pct > 5 ? 'trending_up' : (pct < -5 ? 'trending_down' : 'horizontal_rule');
                icon.className = 'material-symbols-outlined ' + (pct > 5 ? 'trend-up' : (pct < -5 ? 'trend-down' : 'text-outline-variant'));
              }

              card.addEventListener('click', () => { location.href = '/app/bom-register'; });
              tempContainer.appendChild(card);
            });
            bomGrid.innerHTML = '';
            bomGrid.appendChild(tempContainer);
          }
        }
      } catch (e) {
        console.error('[홈] BOM 섹션 렌더링 실패:', e);
        showHomeErrorState();
      }
    }).catch(err => {
      console.error('[홈] API 통신 실패:', err);
      showHomeErrorState();
    });
  };

  const showHomeErrorState = () => {
    const bomGrid = document.getElementById('bom-grid');
    if (bomGrid) {
      bomGrid.innerHTML = `
        <div class="glass-card rounded-xl p-lg text-center text-on-surface-variant col-span-full">
          <span class="material-symbols-outlined text-[32px] text-error mb-xs">error</span>
          <p class="font-label-md">데이터를 불러오지 못했습니다.</p>
          <p class="text-xs text-outline mt-1 mb-md">네트워크 상태를 확인하고 다시 시도해 주세요.</p>
          <button id="btn-home-retry" class="mx-auto flex items-center justify-center gap-xs px-md py-sm bg-primary text-white font-label-md rounded-lg active:scale-95 transition-transform hover:brightness-110">
            <span class="material-symbols-outlined text-[18px]">refresh</span>
            다시 시도
          </button>
        </div>
      `;
      const retryBtn = document.getElementById('btn-home-retry');
      if (retryBtn) {
        retryBtn.addEventListener('click', () => loadHomeData());
      }
    }
  };

  loadHomeData();
});
