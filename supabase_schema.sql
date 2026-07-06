-- CartTiming 계정화 스키마: 매장·메뉴(BOM)·재고·알림설정을 사용자별로 저장 (RLS 소유자 전용)
-- Supabase SQL Editor에서 1회 실행. auth.users는 Supabase Auth가 자동 관리.

-- 1) 매장 (사용자당 1개 가정, 여러 개도 허용)
create table if not exists public.stores (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  addr text default '',
  cuisine text default '',
  created_at timestamptz default now()
);

-- 2) 메뉴 BOM (ct_bom 대체): 식재료 목록을 jsonb로 저장
create table if not exists public.menus (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  ings jsonb not null default '[]',   -- [{name, qty, unit}]
  created_at timestamptz default now()
);

-- 3) 품목별 보유 재고 일수 (ct_stock 대체): 사용자+품목 유일
create table if not exists public.stock_levels (
  user_id uuid not null references auth.users(id) on delete cascade,
  item_name text not null,
  days_left int not null check (days_left >= 0),
  updated_at timestamptz default now(),
  primary key (user_id, item_name)
);

-- 4) 알림 설정 (ct_alerts 대체): bool 배열을 jsonb로
create table if not exists public.alert_prefs (
  user_id uuid primary key references auth.users(id) on delete cascade,
  prefs jsonb not null default '[]',
  updated_at timestamptz default now()
);

-- RLS: 모든 테이블 소유자 전용
alter table public.stores enable row level security;
alter table public.menus enable row level security;
alter table public.stock_levels enable row level security;
alter table public.alert_prefs enable row level security;

do $$
declare t text;
begin
  foreach t in array array['stores','menus','stock_levels','alert_prefs'] loop
    execute format('drop policy if exists own_all on public.%I', t);
    execute format(
      'create policy own_all on public.%I for all
         using (auth.uid() = user_id) with check (auth.uid() = user_id)', t);
  end loop;
end $$;
