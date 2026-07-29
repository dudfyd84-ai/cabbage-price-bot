// Supabase 연동 및 로컬 스토리지 폴백을 제공하는 공통 데이터 스토어 클라이언트
// 
// [ ctStore 공개 메서드 목록 ]
// - init() : 초기화 (내부적으로 자동 호출되나 명시적 호출 가능)
// - syncOnLogin() : 로그인 감지 시 동기화/마이그레이션 제어 (내부용)
// - migrateLocalDataToServer(), syncServerToLocal() : 데이터 동기화
// - authFetch(url, options) : 토큰을 포함하여 서버 API 호출
// - getStore(), setStore(storeData) : 매장 정보 조회/저장
// - getMenus(), setMenus(bomList) : 메뉴 BOM 정보 조회/저장
// - getStockLevels(), setStockLevels(stockObj) : 재고 정보 조회/저장
// - getAlertPrefs(), setAlertPrefs(alertsList) : 알림 설정 조회/저장
(function() {
  const ctStore = {
    client: null,
    session: null,
    initialized: false,
    initPromise: null,

    // 1. 초기화: 서버 API로부터 Supabase 접속 정보 로드 및 클라이언트 생성
    async init() {
      if (this.initPromise) return this.initPromise;

      this.initPromise = (async () => {
        try {
          const res = await fetch('/api/config');
          const config = await res.json();

          if (config.supabaseUrl && config.supabaseAnonKey) {
            this.client = supabase.createClient(config.supabaseUrl, config.supabaseAnonKey);
            
            // 세션 정보 갱신
            const { data: { session } } = await this.client.auth.getSession();
            this.session = session;

            // 인증 상태 변화 구독
            this.client.auth.onAuthStateChange(async (event, session) => {
              const prevSession = this.session;
              this.session = session;

              if (event === 'SIGNED_IN' && !prevSession) {
                console.log('Supabase 로그인 감지: 동기화 및 마이그레이션 진행');
                await this.syncOnLogin();
              } else if (event === 'SIGNED_OUT') {
                console.log('Supabase 로그아웃 감지');
                // 필요시 로컬 정리
              }
            });
          } else {
            console.warn('Supabase 자격증명이 설정되지 않았습니다. 로컬 스토리지만 사용합니다.');
          }
        } catch (e) {
          console.error('Supabase 클라이언트 초기화 중 에러 발생:', e);
        }
        this.initialized = true;
      })();

      return this.initPromise;
    },

    // 로그인 직후 자동 동기화/마이그레이션 제어
    async syncOnLogin() {
      if (!this.client || !this.session) return;
      const userId = this.session.user.id;

      try {
        // 서버 DB에 stores 데이터가 존재하는지 확인
        const { data: stores, error } = await this.client
          .from('stores')
          .select('id')
          .limit(1);

        if (error) throw error;

        if (!stores || stores.length === 0) {
          // 서버에 데이터가 없으므로 로컬 데이터를 서버로 업로드 (최초 로그인 마이그레이션)
          console.log('최초 로그인 감지: 로컬 데이터를 서버 DB로 마이그레이션합니다.');
          await this.migrateLocalDataToServer(userId);
        } else {
          // 서버에 데이터가 존재하므로 서버 데이터를 로컬로 다운로드
          console.log('기존 서버 데이터 감지: 서버 데이터를 로컬 스토리지에 동기화합니다.');
          await this.syncServerToLocal();
        }
      } catch (e) {
        console.error('로그인 동기화 프로세스 오류:', e);
      }
    },

    // 2. 마이그레이션: 로컬 데이터를 Supabase DB로 업로드
    async migrateLocalDataToServer(userId) {
      if (!this.client) return;

      // 1) 매장 정보 마이그레이션
      const localStore = localStorage.getItem('ct_store');
      if (localStore) {
        try {
          const storeData = JSON.parse(localStore);
          await this.client.from('stores').insert({
            user_id: userId,
            name: storeData.name || '',
            addr: storeData.addr || '',
            cuisine: storeData.cat || ''
          });
        } catch (e) { console.error('매장 정보 마이그레이션 실패:', e); }
      }

      // 2) 메뉴 BOM 마이그레이션
      const localBom = localStorage.getItem('ct_bom');
      if (localBom) {
        try {
          const bomList = JSON.parse(localBom); // [{menu, ings: [...]}]
          if (Array.isArray(bomList)) {
            const insertMenus = bomList.map(item => ({
              user_id: userId,
              name: item.menu,
              ings: item.ings || []
            }));
            if (insertMenus.length > 0) {
              await this.client.from('menus').insert(insertMenus);
            }
          }
        } catch (e) { console.error('메뉴 BOM 마이그레이션 실패:', e); }
      }

      // 3) 재고 마이그레이션
      const localStock = localStorage.getItem('ct_stock');
      if (localStock) {
        try {
          const stockObj = JSON.parse(localStock); // {item_name: days_left}
          const insertStocks = Object.keys(stockObj).map(item_name => ({
            user_id: userId,
            item_name: item_name,
            days_left: parseInt(stockObj[item_name]) || 0
          }));
          if (insertStocks.length > 0) {
            await this.client.from('stock_levels').upsert(insertStocks);
          }
        } catch (e) { console.error('재고 마이그레이션 실패:', e); }
      }

      // 4) 알림 설정 마이그레이션
      const localAlerts = localStorage.getItem('ct_alerts');
      if (localAlerts) {
        try {
          const alertsList = JSON.parse(localAlerts); // [bool, bool, ...]
          await this.client.from('alert_prefs').upsert({
            user_id: userId,
            prefs: alertsList
          });
        } catch (e) { console.error('알림 설정 마이그레이션 실패:', e); }
      }

      console.log('로컬 데이터 마이그레이션 완료.');
    },

    // 3. 동기화: 서버 DB 데이터를 로컬 스토리지에 복사
    async syncServerToLocal() {
      if (!this.client || !this.session) return;

      try {
        // 1) 매장 정보 동기화
        const { data: stores } = await this.client.from('stores').select('*').limit(1);
        if (stores && stores.length > 0) {
          localStorage.setItem('ct_store', JSON.stringify({
            name: stores[0].name,
            addr: stores[0].addr,
            cat: stores[0].cuisine
          }));
        }

        // 2) 메뉴 BOM 동기화
        const { data: menus } = await this.client.from('menus').select('*');
        if (menus) {
          const mappedBom = menus.map(m => ({
            menu: m.name,
            ings: m.ings,
            saved: m.created_at ? new Date(m.created_at).toISOString().slice(0, 10) : new Date().toISOString().slice(0, 10)
          }));
          localStorage.setItem('ct_bom', JSON.stringify(mappedBom));
        }

        // 3) 재고 정보 동기화
        const { data: stocks } = await this.client.from('stock_levels').select('*');
        if (stocks) {
          const mappedStock = {};
          stocks.forEach(s => {
            mappedStock[s.item_name] = s.days_left;
          });
          localStorage.setItem('ct_stock', JSON.stringify(mappedStock));
        }

        // 4) 알림 설정 동기화
        const { data: alerts } = await this.client.from('alert_prefs').select('*').limit(1);
        if (alerts && alerts.length > 0) {
          localStorage.setItem('ct_alerts', JSON.stringify(alerts[0].prefs));
        }

        console.log('서버 데이터를 로컬 스토리지로 동기화 완료.');
      } catch (e) {
        console.error('서버 데이터 동기화 실패:', e);
      }
    },

    // 4. 추상화된 데이터 호출 인터페이스
    // 4-0) 인증 토큰이 포함된 fetch 래퍼
    async authFetch(url, options = {}) {
      await this.init();
      if (this.session && this.session.access_token) {
        options.headers = options.headers || {};
        options.headers['Authorization'] = `Bearer ${this.session.access_token}`;
      }
      let response = await fetch(url, options);

      // 401 Unauthorized 감지 시 토큰 갱신 시도
      if (response.status === 401 && this.client && this.session) {
        console.warn('API 401 에러 감지. 세션 갱신을 시도합니다.');
        const { data, error } = await this.client.auth.refreshSession();
        
        if (error || !data.session) {
          console.error('세션 갱신 실패. 강제 로그아웃 처리합니다.', error);
          await this.client.auth.signOut();
          alert('로그인 세션이 만료되었습니다. 다시 로그인해 주세요.');
          window.location.href = '/app/onboarding';
          return response;
        }

        console.log('세션 갱신 성공. 새 토큰으로 요청을 재시도합니다.');
        this.session = data.session;
        options.headers['Authorization'] = `Bearer ${this.session.access_token}`;
        response = await fetch(url, options);
      }

      return response;
    },

    // 4-1) 매장 정보
    async getStore() {
      await this.init();
      if (this.client && this.session) {
        const { data, error } = await this.client.from('stores').select('*').limit(1);
        if (!error && data && data.length > 0) {
          return { name: data[0].name, addr: data[0].addr, cat: data[0].cuisine };
        }
      }
      const local = localStorage.getItem('ct_store');
      return local ? JSON.parse(local) : null;
    },

    async setStore(storeData) {
      await this.init();
      const localStr = JSON.stringify(storeData);
      localStorage.setItem('ct_store', localStr);

      if (this.client && this.session) {
        const userId = this.session.user.id;
        // 기존 매장 확인 후 upsert
        const { data } = await this.client.from('stores').select('id').limit(1);
        if (data && data.length > 0) {
          await this.client.from('stores').update({
            name: storeData.name,
            addr: storeData.addr,
            cuisine: storeData.cat
          }).eq('id', data[0].id);
        } else {
          await this.client.from('stores').insert({
            user_id: userId,
            name: storeData.name,
            addr: storeData.addr,
            cuisine: storeData.cat
          });
        }
      }
    },

    // 데이터 병합용 헬퍼 함수 (마스킹 처리 등)
    fallback(item, primaryKey, fallbackKey) {
      if (!item) return null;
      return item[primaryKey] ?? item[fallbackKey];
    },

    // 마스킹 UI용 헬퍼 함수
    // 주의: 결과값이 innerHTML로 삽입되므로, 추후 사용자 입력값(매장명, 메뉴명 등)을
    // 처리하게 될 경우 XSS 방지를 위한 이스케이프(escape) 처리가 필요합니다.
    masked(item, key, renderFn) {
      if (!item || item[key] === null) {
        return '<span style="color:#ba1a1a;">🔒 유료 전용 (D+30일)</span>';
      }
      return renderFn(item[key]);
    },

    // 4-2) 메뉴 BOM 정보
    async getMenus() {
      await this.init();
      if (this.client && this.session) {
        const { data, error } = await this.client.from('menus').select('*');
        if (!error && data) {
          return data.map(m => ({
            menu: m.name,
            ings: m.ings,
            saved: m.created_at ? new Date(m.created_at).toISOString().slice(0, 10) : new Date().toISOString().slice(0, 10)
          }));
        }
      }
      const local = localStorage.getItem('ct_bom');
      return local ? JSON.parse(local) : [];
    },

    async setMenus(bomList) {
      await this.init();
      localStorage.setItem('ct_bom', JSON.stringify(bomList));

      if (this.client && this.session) {
        const userId = this.session.user.id;
        // 메뉴는 삭제 후 일괄 재등록(또는 Upsert)으로 단순하게 처리
        await this.client.from('menus').delete().eq('user_id', userId);
        if (bomList.length > 0) {
          const insertData = bomList.map(item => ({
            user_id: userId,
            name: item.menu,
            ings: item.ings || []
          }));
          await this.client.from('menus').insert(insertData);
        }
      }
    },

    // 4-3) 재고 정보
    async getStockLevels() {
      await this.init();
      if (this.client && this.session) {
        const { data, error } = await this.client.from('stock_levels').select('*');
        if (!error && data) {
          const res = {};
          data.forEach(s => { res[s.item_name] = s.days_left; });
          return res;
        }
      }
      const local = localStorage.getItem('ct_stock');
      return local ? JSON.parse(local) : {};
    },

    async setStockLevels(stockObj) {
      await this.init();
      localStorage.setItem('ct_stock', JSON.stringify(stockObj));

      if (this.client && this.session) {
        const userId = this.session.user.id;
        const upsertData = Object.keys(stockObj).map(item_name => ({
          user_id: userId,
          item_name: item_name,
          days_left: parseInt(stockObj[item_name]) || 0
        }));
        if (upsertData.length > 0) {
          await this.client.from('stock_levels').upsert(upsertData);
        }
      }
    },

    // 4-4) 알림 설정 정보
    async getAlertPrefs() {
      await this.init();
      if (this.client && this.session) {
        const { data, error } = await this.client.from('alert_prefs').select('*').limit(1);
        if (!error && data && data.length > 0) {
          return data[0].prefs;
        }
      }
      const local = localStorage.getItem('ct_alerts');
      return local ? JSON.parse(local) : null;
    },

    async setAlertPrefs(alertsList) {
      await this.init();
      localStorage.setItem('ct_alerts', JSON.stringify(alertsList));

      if (this.client && this.session) {
        const userId = this.session.user.id;
        await this.client.from('alert_prefs').upsert({
          user_id: userId,
          prefs: alertsList
        });
      }
    }
  };

  // 전역에 ctStore 객체 바인딩
  window.ctStore = ctStore;

  // 페이지 로드 즉시 초기화 시작
  ctStore.init();
})();
