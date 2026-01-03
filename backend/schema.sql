-- 1. Price Daily Table
create table price_daily (
    symbol text not null,
    date date not null,
    open numeric,
    high numeric,
    low numeric,
    close numeric,
    volume bigint,
    source text default 'yfinance',
    created_at timestamp with time zone default now(),
    primary key (symbol, date)
);

-- 2. Factor Momentum Table
create table factor_momentum (
    symbol text not null,
    as_of_date date not null,
    lookback_days int not null,
    momentum_score numeric not null,
    created_at timestamp with time zone default now(),
    primary key (symbol, as_of_date, lookback_days)
);

-- 3. Runs Table
create table runs (
    run_id uuid default gen_random_uuid() primary key,
    run_type text not null,
    started_at timestamp with time zone default now(),
    finished_at timestamp with time zone,
    status text,
    error text
);
