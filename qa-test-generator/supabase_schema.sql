-- Run this once in your Supabase SQL Editor
-- Project: QA Test Generator

create table if not exists test_suites (
  id            uuid        default gen_random_uuid() primary key,
  feature_name  text        not null,
  generated_at  timestamptz not null,
  domain        text,
  score         float       default 0,
  total_tests   int         default 0,
  manual_count  int         default 0,
  api_count     int         default 0,
  ui_count      int         default 0,
  suite_json    jsonb       not null,
  output_md     text,
  created_at    timestamptz default now()
);

-- Index for fast sorting and search
create index if not exists idx_test_suites_generated_at on test_suites (generated_at desc);
create index if not exists idx_test_suites_feature_name on test_suites using gin (to_tsvector('english', feature_name));
create index if not exists idx_test_suites_score        on test_suites (score desc);

-- Enable Row Level Security
alter table test_suites enable row level security;

-- Allow full access via the anon key (sufficient for a Capstone demo)
create policy "public_access" on test_suites
  for all
  using (true)
  with check (true);
