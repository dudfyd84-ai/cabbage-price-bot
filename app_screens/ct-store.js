// ct-store.js: localStorage와 Supabase를 투명하게 전환하는 추상화 데이터 레이어
// (Track B의 Supabase 설정이 완료되면 아래 URL과 Anon Key를 입력합니다)
const SUPABASE_URL = "";
const SUPABASE_ANON_KEY = "";

(function () {
  let supabase = null;
  if (SUPABASE_URL && SUPABASE_ANON_KEY && window.supabase) {
    supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  }

  const ctStore = {
    // ── 0) 로그인 상태 확인 ──
    async isLoggedIn() {
      if (!supabase) return false;
      try {
        const { data, error } = await supabase.auth.getSession();
        return !error && data && data.session && data.session.user;
      } catch (e) {
        console.error("[ctStore] 세션 확인 실패:", e);
        return false;
      }
    },

    // ── 1) 매장 정보 (stores) ──
    // Local format: { name, addr, cat }
    // DB format: name, addr, cuisine (cuisine = cat)
    async getStore() {
      if (await this.isLoggedIn()) {
        try {
          const { data, error } = await supabase
            .from("stores")
            .select("name, addr, cuisine")
            .limit(1)
            .maybeSingle();
          if (!error && data) {
            return { name: data.name, addr: data.addr, cat: data.cuisine };
          }
          if (error) console.error("[ctStore] 매장 조회 실패:", error);
        } catch (e) {
          console.error("[ctStore] 매장 조회 오류:", e);
        }
      }
      return JSON.parse(localStorage.getItem("ct_store") || "null");
    },

    async setStore(data) {
      localStorage.setItem("ct_store", JSON.stringify(data));
      if (await this.isLoggedIn()) {
        try {
          const { data: { user } } = await supabase.auth.getUser();
          if (user) {
            const { data: existing } = await supabase
              .from("stores")
              .select("id")
              .limit(1)
              .maybeSingle();
            
            const payload = {
              user_id: user.id,
              name: data.name,
              addr: data.addr,
              cuisine: data.cat || ""
            };

            if (existing) {
              await supabase.from("stores").update(payload).eq("id", existing.id);
            } else {
              await supabase.from("stores").insert(payload);
            }
          }
        } catch (e) {
          console.error("[ctStore] 매장 저장 실패:", e);
        }
      }
    },

    // ── 2) 메뉴 BOM (menus) ──
    // Local format: Array of { menu, ings: [...], saved }
    // DB format: id, name (menu), ings (jsonb array)
    async getBoms() {
      if (await this.isLoggedIn()) {
        try {
          const { data, error } = await supabase.from("menus").select("name, ings, created_at");
          if (!error && data) {
            return data.map(m => ({
              menu: m.name,
              ings: m.ings,
              saved: m.created_at ? new Date(m.created_at).toISOString().slice(0, 10) : new Date().toISOString().slice(0, 10)
            }));
          }
          if (error) console.error("[ctStore] BOM 조회 실패:", error);
        } catch (e) {
          console.error("[ctStore] BOM 조회 오류:", e);
        }
      }
      return JSON.parse(localStorage.getItem("ct_bom") || "[]");
    },

    async setBoms(bomsArray) {
      localStorage.setItem("ct_bom", JSON.stringify(bomsArray));
      if (await this.isLoggedIn()) {
        try {
          const { data: { user } } = await supabase.auth.getUser();
          if (user) {
            // 전체 덮어쓰기 방식으로 기존 메뉴 삭제 후 새 목록 등록
            await supabase.from("menus").delete().eq("user_id", user.id);
            if (bomsArray.length > 0) {
              const rows = bomsArray.map(b => ({
                user_id: user.id,
                name: b.menu,
                ings: b.ings
              }));
              await supabase.from("menus").insert(rows);
            }
          }
        } catch (e) {
          console.error("[ctStore] BOM 저장 실패:", e);
        }
      }
    },

    // ── 3) 품목별 보유 재고 일수 (stock_levels) ──
    // Local format: { "배추": 10, "무": 5 }
    // DB format: item_name, days_left
    async getStock() {
      if (await this.isLoggedIn()) {
        try {
          const { data, error } = await supabase.from("stock_levels").select("item_name, days_left");
          if (!error && data) {
            const stockObj = {};
            data.forEach(row => {
              stockObj[row.item_name] = row.days_left;
            });
            return stockObj;
          }
          if (error) console.error("[ctStore] 재고 조회 실패:", error);
        } catch (e) {
          console.error("[ctStore] 재고 조회 오류:", e);
        }
      }
      return JSON.parse(localStorage.getItem("ct_stock") || "{}");
    },

    async setStock(stockObj) {
      localStorage.setItem("ct_stock", JSON.stringify(stockObj));
      if (await this.isLoggedIn()) {
        try {
          const { data: { user } } = await supabase.auth.getUser();
          if (user) {
            // 기존 재고 목록 삭제 후 새 목록 추가
            await supabase.from("stock_levels").delete().eq("user_id", user.id);
            const rows = Object.entries(stockObj).map(([name, days]) => ({
              user_id: user.id,
              item_name: name,
              days_left: days
            }));
            if (rows.length > 0) {
              await supabase.from("stock_levels").insert(rows);
            }
          }
        } catch (e) {
          console.error("[ctStore] 재고 저장 실패:", e);
        }
      }
    },

    // ── 4) 알림 설정 (alert_prefs) ──
    // Local format: Array of booleans [true, false, true]
    // DB format: prefs (jsonb array)
    async getAlerts() {
      if (await this.isLoggedIn()) {
        try {
          const { data, error } = await supabase
            .from("alert_prefs")
            .select("prefs")
            .limit(1)
            .maybeSingle();
          if (!error && data) {
            return data.prefs;
          }
          if (error) console.error("[ctStore] 알림 조회 실패:", error);
        } catch (e) {
          console.error("[ctStore] 알림 조회 오류:", e);
        }
      }
      return JSON.parse(localStorage.getItem("ct_alerts") || "null");
    },

    async setAlerts(alertsArray) {
      localStorage.setItem("ct_alerts", JSON.stringify(alertsArray));
      if (await this.isLoggedIn()) {
        try {
          const { data: { user } } = await supabase.auth.getUser();
          if (user) {
            const { data: existing } = await supabase
              .from("alert_prefs")
              .select("user_id")
              .limit(1)
              .maybeSingle();

            const payload = {
              user_id: user.id,
              prefs: alertsArray
            };

            if (existing) {
              await supabase.from("alert_prefs").update(payload).eq("user_id", user.id);
            } else {
              await supabase.from("alert_prefs").insert(payload);
            }
          }
        } catch (e) {
          console.error("[ctStore] 알림 저장 실패:", e);
        }
      }
    },

    // ── 5) 로컬스토리지 데이터를 Supabase로 1회 마이그레이션 ──
    async migrateLocalStorageToSupabase() {
      if (!(await this.isLoggedIn())) return;
      
      const isMigrated = localStorage.getItem("ct_migrated_to_supabase") === "true";
      if (isMigrated) return;

      console.log("[ctStore] 로그인 감지: 로컬 데이터를 Supabase로 마이그레이션 시작합니다...");
      try {
        // 매장 마이그레이션
        const store = JSON.parse(localStorage.getItem("ct_store") || "null");
        if (store) {
          await this.setStore(store);
        }

        // BOM 마이그레이션
        const boms = JSON.parse(localStorage.getItem("ct_bom") || "[]");
        if (boms.length > 0) {
          await this.setBoms(boms);
        }

        // 재고 마이그레이션
        const stock = JSON.parse(localStorage.getItem("ct_stock") || "{}");
        if (Object.keys(stock).length > 0) {
          await this.setStock(stock);
        }

        // 알림 설정 마이그레이션
        const alerts = JSON.parse(localStorage.getItem("ct_alerts") || "null");
        if (alerts) {
          await this.setAlerts(alerts);
        }

        localStorage.setItem("ct_migrated_to_supabase", "true");
        console.log("[ctStore] 🎉 로컬 데이터를 Supabase로 성공적으로 이관 완료했습니다!");
      } catch (e) {
        console.error("[ctStore] 마이그레이션 중 오류 발생:", e);
      }
    }
  };

  // 전역 객체로 노출
  window.ctStore = ctStore;
})();
