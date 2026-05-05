
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# ── Helpers ──

def _safe(v, default=0.0):
    try:
        f = float(v)
        return default if (np.isnan(f) or np.isinf(f)) else f
    except (TypeError, ValueError):
        return default


def _classify_regime(nifty_ret_90d):
    """Classify market regime from 90-day NIFTY return."""
    if nifty_ret_90d > 0.05:
        return "bull"
    elif nifty_ret_90d < -0.05:
        return "bear"
    return "sideways"


class BacktestEngine:
    def __init__(self, engine):
        self.engine = engine

    def fetch_data(self, start_date, end_date):
        query_start = pd.to_datetime(start_date) - timedelta(days=400)
        query = text("""
            SELECT date, symbol, close
            FROM price_daily
            WHERE date >= :start AND date <= :end
            ORDER BY date ASC
        """)
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"start": query_start, "end": end_date})
        if df.empty:
            return pd.DataFrame(), pd.DataFrame()
        prices = df.pivot(index="date", columns="symbol", values="close")
        prices.index = pd.to_datetime(prices.index)
        prices = prices.ffill()

        f_query = text("""
            SELECT symbol, as_of_date, pe_ratio, market_cap
            FROM fundamentals_snapshot
            ORDER BY as_of_date ASC
        """)
        with self.engine.connect() as conn:
            fund_df = pd.read_sql(f_query, conn)
        if not fund_df.empty:
            fund_df["as_of_date"] = pd.to_datetime(fund_df["as_of_date"])
        return prices, fund_df

    def run_simulation(self, params):
        try:
            factor = params.get("factor", "momentum")
            lookback = int(params.get("lookback_days", 90))
            top_n = int(params.get("top_n", 10))
            start_date = pd.to_datetime(params.get("start", "2023-01-01"))
            end_date = pd.to_datetime(params.get("end", datetime.now()))
            rebalance_freq = params.get("rebalance", "monthly")

            prices, fundamentals = self.fetch_data(start_date, end_date)
            if prices.empty:
                return {"error": "No price data available"}

            freq_map = {"monthly": "ME", "quarterly": "QE", "weekly": "W-FRI"}
            freq = freq_map.get(rebalance_freq, "ME")
            rebal_dates = pd.date_range(start=start_date, end=end_date, freq=freq)

            weights = pd.DataFrame(index=prices.index, columns=prices.columns).fillna(0.0)
            sim_prices = prices[prices.index >= (start_date - timedelta(days=lookback * 2))]

            active_dates = [d for d in rebal_dates if d >= start_date]
            if not active_dates and start_date < end_date:
                active_dates = [start_date]
            elif active_dates and active_dates[0] > start_date:
                active_dates.insert(0, start_date)

            turnover_list = []
            prev_selected = set()

            for date in active_dates:
                if date > end_date:
                    break
                valid_days = sim_prices.index[sim_prices.index <= date]
                if valid_days.empty:
                    continue
                obs_date = valid_days[-1]
                loc = sim_prices.index.get_loc(obs_date)
                start_loc = max(0, loc - lookback)
                hist = sim_prices.iloc[start_loc:loc + 1]

                selected = []
                if factor == "momentum":
                    if len(hist) > 1:
                        ret = (hist.iloc[-1] / hist.iloc[0]) - 1
                        ret = ret.dropna()
                        selected = ret.sort_values(ascending=False).head(top_n).index.tolist()
                elif factor == "low-vol":
                    if len(hist) > 10:
                        lrets = np.log(hist / hist.shift(1))
                        vol = lrets.std().dropna()
                        selected = vol.sort_values(ascending=True).head(top_n).index.tolist()
                elif factor == "value":
                    if not fundamentals.empty:
                        valid = fundamentals[fundamentals["as_of_date"] <= obs_date]
                        if not valid.empty:
                            latest = valid.sort_values("as_of_date").groupby("symbol").last()
                            pe = latest["pe_ratio"].dropna()
                            pe = pe[pe > 0]
                            selected = pe.sort_values(ascending=True).head(top_n).index.tolist()

                valid_selected = [s for s in selected if s in prices.columns]

                if valid_selected:
                    w = 1.0 / len(valid_selected)
                    new_w = pd.Series(0.0, index=prices.columns)
                    new_w.loc[valid_selected] = w
                    weights.loc[obs_date] = new_w

                    # Turnover
                    cur_set = set(valid_selected)
                    if prev_selected:
                        changed = len(cur_set.symmetric_difference(prev_selected))
                        total = len(cur_set.union(prev_selected))
                        turnover_list.append(changed / total if total > 0 else 0)
                    prev_selected = cur_set

            weights = weights.replace(0.0, np.nan).ffill().fillna(0.0)
            weights = weights.shift(1).fillna(0.0)
            weights = weights[(weights.index >= start_date) & (weights.index <= end_date)]
            sim_daily_prices = prices[(prices.index >= start_date) & (prices.index <= end_date)]

            common_idx = weights.index.intersection(sim_daily_prices.index)
            weights = weights.loc[common_idx]
            sim_daily_prices = sim_daily_prices.loc[common_idx]

            rets = sim_daily_prices.pct_change().fillna(0.0)
            strat_ret = (weights * rets).sum(axis=1)
            equity_curve = (1 + strat_ret).cumprod()

            # ── Benchmark: Equal-weight universe ──
            bench_ret = rets.mean(axis=1)
            bench_curve = (1 + bench_ret).cumprod()

            # ── NIFTY benchmark ──
            nifty_curve_data = []
            nifty_regime_series = pd.Series("sideways", index=common_idx)
            if "^NSEI" in prices.columns:
                nifty_p = prices.loc[common_idx, "^NSEI"].dropna()
                if not nifty_p.empty:
                    nifty_r = nifty_p.pct_change().fillna(0.0)
                    nifty_eq = (1 + nifty_r).cumprod()
                    nifty_curve_data = [
                        {"date": d.strftime("%d-%m-%Y"), "value": round(float(v), 4)}
                        for d, v in nifty_eq.items()
                    ]
                    # Regime classification using 63-trading-day rolling return
                    nifty_90d = nifty_p / nifty_p.shift(63) - 1
                    nifty_regime_series = nifty_90d.apply(
                        lambda x: _classify_regime(x) if not np.isnan(x) else "sideways"
                    )

            # ── Summary metrics ──
            total_ret = equity_curve.iloc[-1] - 1 if not equity_curve.empty else 0
            days = (end_date - start_date).days
            years = days / 365.25
            cagr = ((total_ret + 1) ** (1 / years)) - 1 if years > 0 else 0
            valid_rets = strat_ret[strat_ret != 0]
            vol = valid_rets.std() * np.sqrt(252) if not valid_rets.empty else 0
            sharpe = (cagr - 0.05) / vol if vol > 0 else 0

            # ── Drawdown analysis ──
            rolling_max = equity_curve.cummax()
            drawdown = (equity_curve - rolling_max) / rolling_max
            max_dd = drawdown.min()

            # Find max drawdown period and recovery
            max_dd_idx = drawdown.idxmin()
            peak_idx = equity_curve.loc[:max_dd_idx].idxmax()
            # Recovery: first date after trough where equity >= peak
            post_trough = equity_curve.loc[max_dd_idx:]
            peak_val = equity_curve.loc[peak_idx]
            recovered = post_trough[post_trough >= peak_val]
            recovery_date = recovered.index[0] if not recovered.empty else None
            recovery_days = (recovery_date - max_dd_idx).days if recovery_date else None

            dd_curve = [
                {"date": d.strftime("%d-%m-%Y"), "dd": round(float(v), 4)}
                for d, v in drawdown.items()
            ]

            # ── Rolling metrics (126-day = 6M) ──
            window = 126
            rolling_sharpe_data = []
            rolling_vol_data = []
            if len(strat_ret) > window:
                roll_mean = strat_ret.rolling(window).mean() * 252
                roll_std = strat_ret.rolling(window).std() * np.sqrt(252)
                roll_sharpe = (roll_mean - 0.05) / roll_std
                roll_sharpe = roll_sharpe.replace([np.inf, -np.inf], np.nan).fillna(0)

                for d in roll_sharpe.index[window:]:
                    rolling_sharpe_data.append({
                        "date": d.strftime("%d-%m-%Y"),
                        "sharpe": round(float(roll_sharpe.loc[d]), 4)
                    })
                    rolling_vol_data.append({
                        "date": d.strftime("%d-%m-%Y"),
                        "vol": round(float(roll_std.loc[d]), 4)
                    })

            # ── Regime-conditional metrics ──
            regime_metrics = {}
            for regime in ["bull", "bear", "sideways"]:
                mask = nifty_regime_series.reindex(strat_ret.index) == regime
                regime_rets = strat_ret[mask]
                if len(regime_rets) > 5:
                    r_ann = regime_rets.mean() * 252
                    r_vol = regime_rets.std() * np.sqrt(252)
                    r_sharpe = (r_ann - 0.05) / r_vol if r_vol > 0 else 0
                    regime_metrics[regime] = {
                        "sharpe": round(_safe(r_sharpe), 4),
                        "ann_return": round(_safe(r_ann), 4),
                        "ann_vol": round(_safe(r_vol), 4),
                        "days": int(mask.sum()),
                    }
                else:
                    regime_metrics[regime] = {"sharpe": 0, "ann_return": 0, "ann_vol": 0, "days": 0}

            # ── Build equity curve JSON ──
            curves = []
            for d in equity_curve.index:
                curves.append({
                    "date": d.strftime("%d-%m-%Y"),
                    "portfolio": round(float(equity_curve.loc[d]), 4),
                    "benchmark": round(float(bench_curve.loc[d]) if d in bench_curve.index else 1.0, 4),
                })

            avg_turnover = round(float(np.mean(turnover_list)), 4) if turnover_list else 0.0

            return {
                "summary": {
                    "cagr": round(_safe(cagr), 4),
                    "volatility": round(_safe(vol), 4),
                    "sharpe": round(_safe(sharpe), 4),
                    "max_drawdown": round(_safe(max_dd), 4),
                },
                "equity_curve": curves,
                "nifty_curve": nifty_curve_data,
                "drawdown_curve": dd_curve,
                "max_dd_start": peak_idx.strftime("%d-%m-%Y") if peak_idx is not None else None,
                "max_dd_end": max_dd_idx.strftime("%d-%m-%Y") if max_dd_idx is not None else None,
                "recovery_days": recovery_days,
                "rolling_sharpe": rolling_sharpe_data,
                "rolling_vol": rolling_vol_data,
                "regime_metrics": regime_metrics,
                "turnover": avg_turnover,
                "holdings_count": int(top_n),
            }

        except Exception as e:
            logger.error(f"Backtest Error: {e}", exc_info=True)
            return {"error": str(e)}


def do_backtest(engine, params):
    bt = BacktestEngine(engine)
    return bt.run_simulation(params)


# ── Strategy color palette ──
COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444"]


def run_multi_simulation(engine, strategies, start, end, rebalance="monthly"):
    """
    Run multiple strategies on the same date range and return aligned results.
    """
    bt = BacktestEngine(engine)
    results = []
    for i, strat in enumerate(strategies[:4]):  # Max 4
        factor = strat.get("factor", "momentum")
        lb = strat.get("lookback_days", 90)
        tn = strat.get("top_n", 10)
        name = f"{factor.replace('-', ' ').title()} {lb}D / Top {tn}"

        params = {
            "factor": factor,
            "lookback_days": lb,
            "top_n": tn,
            "start": start,
            "end": end,
            "rebalance": rebalance,
        }
        res = bt.run_simulation(params)
        if "error" in res:
            results.append({"name": name, "error": res["error"], "color": COLORS[i]})
        else:
            res["name"] = name
            res["color"] = COLORS[i]
            results.append(res)

    return {"strategies": results}


def run_heatmap(engine, factor, lookbacks, top_ns, start, end, rebalance="monthly"):
    """
    Run parameter grid (lookback × top_n) and return Sharpe + CAGR matrix.
    """
    bt = BacktestEngine(engine)
    rows = []
    for lb in lookbacks:
        for tn in top_ns:
            params = {
                "factor": factor,
                "lookback_days": lb,
                "top_n": tn,
                "start": start,
                "end": end,
                "rebalance": rebalance,
            }
            res = bt.run_simulation(params)
            if "error" not in res:
                rows.append({
                    "lookback": lb,
                    "top_n": tn,
                    "sharpe": res["summary"]["sharpe"],
                    "cagr": res["summary"]["cagr"],
                    "max_dd": res["summary"]["max_drawdown"],
                })
            else:
                rows.append({"lookback": lb, "top_n": tn, "sharpe": 0, "cagr": 0, "max_dd": 0})

    return {"factor": factor, "rows": rows, "lookbacks": lookbacks, "top_ns": top_ns}
