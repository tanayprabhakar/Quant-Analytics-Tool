"""
regime_engine.py
================
Data acquisition and regime classification engine for NIFTY 50 market regime analysis.

This module:
  1. Fetches daily OHLCV data for NIFTY 50 and its constituent stocks.
  2. Computes momentum factors (30, 60, 90, 180-day).
  3. Computes rolling annualized volatility (σ30, σ90).
  4. Computes market breadth proxies (Advance-Decline Ratio, % Above 50-DMA, Positive Momentum Breadth).
  5. Classifies market regimes (Bull, Bear, High Volatility, Low Volatility, Transition).

All calculations use rolling windows with NO look-ahead bias.
"""

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import yfinance as yf
import logging
from typing import Tuple, Dict

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ─────────────────────────────────────────────────────────────────────────────
# NIFTY 50 Constituent Symbols (Yahoo Finance tickers)
# We use a representative basket — enough for breadth calculations
# ─────────────────────────────────────────────────────────────────────────────
NIFTY50_CONSTITUENTS = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "ITC.NS", "LT.NS", "AXISBANK.NS", "BAJFINANCE.NS", "BAJAJ-AUTO.NS",
    "KOTAKBANK.NS", "SBIN.NS", "HINDUNILVR.NS", "BHARTIARTL.NS", "ULTRACEMCO.NS",
    "TITAN.NS", "MARUTI.NS", "JSWSTEEL.NS", "SUNPHARMA.NS", "DRREDDY.NS",
    "HCLTECH.NS", "TECHM.NS", "WIPRO.NS", "EICHERMOT.NS", "DIVISLAB.NS",
    "NESTLEIND.NS", "ONGC.NS", "NTPC.NS", "POWERGRID.NS", "TATASTEEL.NS",
    "ADANIPORTS.NS", "BPCL.NS", "COALINDIA.NS", "GRASIM.NS", "HEROMOTOCO.NS",
    "INDUSINDBK.NS", "BRITANNIA.NS", "SBILIFE.NS", "M&M.NS", "HINDALCO.NS",
    "CIPLA.NS", "APOLLOHOSP.NS", "ASIANPAINT.NS", "ADANIENT.NS", "TATAMOTORS.NS",
    "HDFCLIFE.NS", "DMART.NS", "TATACONSUM.NS", "BAJAJFINSV.NS", "SHREECEM.NS"
]

BENCHMARK = "^NSEI"
START_DATE = "2020-06-01"  # Extra buffer for rolling windows
END_DATE = "2026-03-31"
ANALYSIS_START = "2021-01-01"

# Annualisation factor
TRADING_DAYS = 252


def fetch_benchmark_data() -> pd.DataFrame:
    """
    Fetch NIFTY 50 index OHLCV data from Yahoo Finance.
    Returns DataFrame indexed by date with columns: Open, High, Low, Close, Volume.
    """
    logger.info(f"Fetching benchmark data: {BENCHMARK} ({START_DATE} → {END_DATE})")
    ticker = yf.Ticker(BENCHMARK)
    df = ticker.history(start=START_DATE, end=END_DATE, auto_adjust=True)

    if df.empty:
        raise RuntimeError(f"No data returned for {BENCHMARK}. Check network / ticker.")

    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]
    logger.info(f"  Benchmark: {len(df)} trading days fetched ({df.index[0].date()} → {df.index[-1].date()})")
    return df


def fetch_constituents_data() -> pd.DataFrame:
    """
    Fetch daily close prices for all NIFTY 50 constituents.
    Returns a DataFrame with date index and symbol columns.
    """
    logger.info(f"Fetching constituent close prices for {len(NIFTY50_CONSTITUENTS)} stocks...")
    frames = {}
    failed = []

    for sym in NIFTY50_CONSTITUENTS:
        try:
            t = yf.Ticker(sym)
            h = t.history(start=START_DATE, end=END_DATE, auto_adjust=True)
            if not h.empty:
                h.index = pd.to_datetime(h.index).tz_localize(None)
                frames[sym] = h["Close"]
        except Exception as e:
            failed.append(sym)
            logger.warning(f"  Failed: {sym} — {e}")

    if failed:
        logger.warning(f"  {len(failed)} stocks failed to download: {failed}")

    panel = pd.DataFrame(frames)
    panel = panel.sort_index()
    logger.info(f"  Constituents panel: {panel.shape[0]} days × {panel.shape[1]} stocks")
    return panel


def compute_momentum_factors(benchmark: pd.DataFrame) -> pd.DataFrame:
    """
    Compute momentum factors for the benchmark (30, 60, 90, 180-day).
    Momentum = (Close_t / Close_{t-n}) - 1
    """
    df = pd.DataFrame(index=benchmark.index)
    for window in [30, 60, 90, 180]:
        df[f"mom_{window}d"] = benchmark["close"].pct_change(periods=window)
    return df


def compute_volatility(benchmark: pd.DataFrame) -> pd.DataFrame:
    """
    Compute rolling annualized volatility (σ30, σ90) from log returns.
    """
    log_ret = np.log(benchmark["close"] / benchmark["close"].shift(1))
    df = pd.DataFrame(index=benchmark.index)
    df["log_return"] = log_ret
    df["sigma_30"] = log_ret.rolling(window=30).std() * np.sqrt(TRADING_DAYS)
    df["sigma_90"] = log_ret.rolling(window=90).std() * np.sqrt(TRADING_DAYS)
    return df


def compute_breadth(constituents: pd.DataFrame) -> pd.DataFrame:
    """
    Compute market breadth metrics from constituent daily closes:
      1. Advance-Decline Ratio (daily)
      2. % Above 50-DMA
      3. Positive Momentum Breadth (% of stocks with positive 30-day return)
    """
    daily_returns = constituents.pct_change()

    # Advance-Decline Ratio
    advancers = (daily_returns > 0).sum(axis=1)
    decliners = (daily_returns < 0).sum(axis=1)
    adr = advancers / decliners.replace(0, np.nan)

    # % Above 50-DMA
    ma_50 = constituents.rolling(window=50).mean()
    above_50dma_count = (constituents > ma_50).sum(axis=1)
    total_stocks = constituents.notna().sum(axis=1)
    pct_above_50dma = (above_50dma_count / total_stocks) * 100

    # Positive Momentum Breadth (30-day)
    mom_30 = constituents.pct_change(periods=30)
    pct_pos_momentum = (mom_30 > 0).sum(axis=1) / mom_30.notna().sum(axis=1) * 100

    df = pd.DataFrame({
        "adv_dec_ratio": adr,
        "pct_above_50dma": pct_above_50dma,
        "pct_pos_momentum": pct_pos_momentum,
    }, index=constituents.index)

    # Smooth to reduce noise (5-day rolling mean)
    for col in df.columns:
        df[col] = df[col].rolling(5, min_periods=1).mean()

    return df


def classify_regimes(momentum: pd.DataFrame,
                     volatility: pd.DataFrame,
                     breadth: pd.DataFrame) -> pd.Series:
    """
    Classify market regimes based on multi-factor logic.
    
    Regime definitions:
      - Bull:       Momentum > 0 AND Breadth > 60%
      - Bear:       Momentum < 0 AND Breadth < 40%
      - High Vol:   σ30 >> σ90 (breakout: σ30 > σ90 × 1.3)
      - Low Vol:    σ30 ≈ σ90 AND both < median(σ90)
      - Transition: Conflicting signals
    
    Priority order: High Vol > Bull/Bear > Low Vol > Transition
    """
    df = pd.DataFrame(index=momentum.index)
    df["mom_30"] = momentum["mom_30d"]
    df["sigma_30"] = volatility["sigma_30"]
    df["sigma_90"] = volatility["sigma_90"]
    df["breadth"] = breadth["pct_above_50dma"]

    # Median volatility for "low" threshold (rolling to avoid look-ahead)
    df["sigma_90_expanding_med"] = df["sigma_90"].expanding(min_periods=60).median()

    regime = pd.Series("Transition", index=df.index, dtype="object")

    # Low Volatility: σ30 ≈ σ90 (ratio between 0.8–1.2) AND both below historical median
    low_vol_mask = (
        (df["sigma_30"] / df["sigma_90"].replace(0, np.nan)).between(0.8, 1.2)
        & (df["sigma_30"] < df["sigma_90_expanding_med"])
        & (df["sigma_90"] < df["sigma_90_expanding_med"])
    )
    regime[low_vol_mask] = "Low Volatility"

    # Bull Regime
    bull_mask = (df["mom_30"] > 0) & (df["breadth"] > 60)
    regime[bull_mask] = "Bull"

    # Bear Regime
    bear_mask = (df["mom_30"] < 0) & (df["breadth"] < 40)
    regime[bear_mask] = "Bear"

    # High Volatility (highest priority — overrides Bull/Bear if vol is spiking)
    high_vol_mask = df["sigma_30"] > (df["sigma_90"] * 1.3)
    regime[high_vol_mask] = "High Volatility"

    return regime


def build_analysis_dataset() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Master pipeline: fetch data, compute indicators, classify regimes.
    Returns:
      - master_df: Full analysis dataset (benchmark + indicators + regime)
      - constituents_panel: Constituent close prices
    """
    benchmark = fetch_benchmark_data()
    constituents = fetch_constituents_data()

    momentum = compute_momentum_factors(benchmark)
    volatility = compute_volatility(benchmark)
    breadth = compute_breadth(constituents)

    # Align all dataframes on the benchmark index
    master = benchmark.copy()
    master = master.join(momentum, how="left")
    master = master.join(volatility, how="left")
    master = master.join(breadth, how="left")

    # Drop rows with insufficient data (warm-up period)
    master = master.dropna(subset=["sigma_90", "mom_30d", "pct_above_50dma"])

    # Classify regimes
    master["regime"] = classify_regimes(
        master[["mom_30d", "mom_60d", "mom_90d", "mom_180d"]],
        master[["sigma_30", "sigma_90"]],
        master[["pct_above_50dma", "pct_pos_momentum", "adv_dec_ratio"]]
    )

    # Filter to analysis window
    master = master[master.index >= ANALYSIS_START]

    logger.info(f"Analysis dataset: {len(master)} rows, {ANALYSIS_START} → {master.index[-1].date()}")
    logger.info(f"Regime distribution:\n{master['regime'].value_counts().to_string()}")

    return master, constituents


# ─────────────────────────────────────────────────────────────────────────────
# Regime colour palette — muted, publication-ready
# ─────────────────────────────────────────────────────────────────────────────
REGIME_COLORS: Dict[str, str] = {
    "Bull":            "#2d6a4f",  # deep forest green
    "Bear":            "#9d0208",  # dark crimson
    "High Volatility": "#e85d04",  # burnt orange
    "Low Volatility":  "#457b9d",  # steel blue
    "Transition":      "#adb5bd",  # neutral grey
}

REGIME_ORDER = ["Bull", "Bear", "High Volatility", "Low Volatility", "Transition"]
