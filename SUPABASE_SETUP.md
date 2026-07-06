# Supabase 계정화 셋업 (연동 대기 중)

현재 CartTiming 앱은 매장·메뉴(BOM)·재고·알림설정을 브라우저 `localStorage`에 저장한다.
기기 종속을 없애고 구독 BM의 전제인 계정 체계를 갖추기 위해 Supabase로 이관할 준비를 해둔다.
**스키마만 준비된 상태이며, 프론트 연동은 아래 자격증명이 준비되면 진행한다.**

## 1. 지금 준비된 것
- `supabase_schema.sql` — 사용자별 테이블 4종(stores/menus/stock_levels/alert_prefs) + RLS(소유자 전용).
  - `menus.ings`(jsonb) ← `ct_bom`, `stock_levels` ← `ct_stock`, `alert_prefs.prefs` ← `ct_alerts`, `stores` ← `ct_store`.

## 2. 연동을 시작하려면 (사용자 준비 항목)
1. Supabase 프로젝트에서 **SQL Editor로 `supabase_schema.sql` 1회 실행**.
2. **Project URL**과 **anon(public) key** 공유. (anon key는 공개용이며 RLS로 보호되므로 프론트에 노출 가능.)
3. 로그인 방식: **이메일 + 카카오 둘 다** (결정됨).
   - 카카오: Supabase Authentication → Providers → Kakao 활성화 + Kakao Developers 앱의 REST API 키/Redirect URL 등록 필요.
   - 이메일: 추가 설정 없이 즉시 사용 가능.

## 3. 연동 시 구현 계획 (최소 diff)
- `supabase-js` CDN + 공통 `ct-store.js` 추상화: 로그인 시 Supabase, 비로그인 시 localStorage 폴백.
- 기존 4개 localStorage 키 호출부(home/inventory/bom/nav)를 `ct-store.js` get/set으로 교체.
- 온보딩 화면에 이메일/카카오 로그인 버튼 연결(현재 placeholder).
- 로그인 상태에서 기존 localStorage 데이터를 최초 1회 마이그레이션.
