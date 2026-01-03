-- Migration: Add Fundamentals Snapshot Table
-- Purpose: Store point-in-time fundamental data (P/E, Market Cap) for Value Screener.
-- Rules: No overwriting existing tables. Database is source of truth.

create table if not exists fundamentals_snapshot (
    symbol text not null,
    as_of_date date not null,
    market_cap bigint,
    pe_ratio numeric,
    eps numeric,
    sector text,
    source text default 'yfinance',
    created_at timestamp with time zone default now(),
    primary key (symbol, as_of_date)
);

-- Index for faster queries in screeners
create index if not exists idx_fundamentals_as_of on fundamentals_snapshot(as_of_date);
