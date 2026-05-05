"""
visualizations.py
=================
Publication-quality market regime visualizations for NIFTY 50.

Generates 4 research-grade plots:
  1. Regime Overlay on NIFTY Price (matplotlib)
  2. HMM State Probability Heatmap (matplotlib/seaborn)
  3. Markov Transition Matrix (matplotlib/seaborn)
  4. 3D Regime Surface (plotly)

All plots are saved at ≥300 DPI in the output/ directory.
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for server/CI
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
from matplotlib.colors import LinearSegmentedColormap
import seaborn as sns
from scipy.ndimage import gaussian_filter1d

import logging

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Global Style Configuration
# ─────────────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family":        "sans-serif",
    "font.sans-serif":    ["Inter", "Helvetica Neue", "Arial", "DejaVu Sans"],
    "font.size":          10,
    "axes.titlesize":     13,
    "axes.labelsize":     11,
    "xtick.labelsize":    9,
    "ytick.labelsize":    9,
    "legend.fontsize":    9,
    "figure.titlesize":   15,
    "axes.grid":          True,
    "grid.alpha":         0.25,
    "grid.linewidth":     0.5,
    "axes.linewidth":     0.8,
    "axes.edgecolor":     "#4a4a4a",
    "axes.facecolor":     "#fafafa",
    "figure.facecolor":   "#ffffff",
    "savefig.dpi":        300,
    "savefig.bbox":       "tight",
    "savefig.pad_inches": 0.15,
})

from regime_engine import REGIME_COLORS, REGIME_ORDER


def _detect_regime_shifts(regime_series: pd.Series) -> pd.DataFrame:
    """Detect points where the regime changes. Returns a DataFrame of shift dates and new regimes."""
    shifts = regime_series != regime_series.shift(1)
    shift_dates = regime_series[shifts].reset_index()
    shift_dates.columns = ["date", "regime"]
    return shift_dates


# ═════════════════════════════════════════════════════════════════════════════
# PLOT 1: Regime Overlay on NIFTY Price
# ═════════════════════════════════════════════════════════════════════════════

def plot_regime_overlay(df: pd.DataFrame, output_path: str = "output/01_regime_overlay.png"):
    """
    Time-series plot of NIFTY 50 close price with regime-colored background bands
    and secondary volatility axis.
    """
    logger.info("Generating Plot 1: Regime Overlay on NIFTY Price...")

    fig, ax1 = plt.subplots(figsize=(16, 7))

    # ── Regime background bands ──
    regime_series = df["regime"]
    dates = df.index
    prev_regime = regime_series.iloc[0]
    band_start = dates[0]

    for i in range(1, len(regime_series)):
        if regime_series.iloc[i] != prev_regime or i == len(regime_series) - 1:
            band_end = dates[i]
            color = REGIME_COLORS.get(prev_regime, "#cccccc")
            ax1.axvspan(band_start, band_end, alpha=0.18, color=color, linewidth=0)
            band_start = band_end
            prev_regime = regime_series.iloc[i]

    # Final band
    color = REGIME_COLORS.get(prev_regime, "#cccccc")
    ax1.axvspan(band_start, dates[-1], alpha=0.18, color=color, linewidth=0)

    # ── NIFTY Price line ──
    ax1.plot(dates, df["close"], color="#1a1a2e", linewidth=1.2, label="NIFTY 50 Close", zorder=3)
    ax1.set_ylabel("NIFTY 50 Index Level", color="#1a1a2e", fontweight="bold")
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    # ── Secondary axis: Volatility ──
    ax2 = ax1.twinx()
    ax2.fill_between(dates, df["sigma_30"] * 100, alpha=0.12, color="#e85d04", label="σ₃₀ (30-day)")
    ax2.plot(dates, df["sigma_30"] * 100, color="#e85d04", linewidth=0.7, alpha=0.7)
    ax2.plot(dates, df["sigma_90"] * 100, color="#457b9d", linewidth=0.7, alpha=0.7, linestyle="--", label="σ₉₀ (90-day)")
    ax2.set_ylabel("Annualized Volatility (%)", color="#666666")
    ax2.tick_params(axis="y", colors="#888888")
    ax2.set_ylim(0, df["sigma_30"].max() * 100 * 2.5)

    # ── Annotate key regime shifts ──
    shifts = _detect_regime_shifts(regime_series)
    # Only annotate significant shifts (skip if gap < 15 trading days)
    last_annotated = None
    for _, row in shifts.iterrows():
        if last_annotated is not None and (row["date"] - last_annotated).days < 30:
            continue
        price_at_shift = df.loc[row["date"], "close"] if row["date"] in df.index else None
        if price_at_shift is not None:
            ax1.annotate(
                row["regime"],
                xy=(row["date"], price_at_shift),
                xytext=(0, 22),
                textcoords="offset points",
                fontsize=6.5,
                fontweight="bold",
                color=REGIME_COLORS.get(row["regime"], "#333"),
                ha="center",
                arrowprops=dict(arrowstyle="-", color="#aaa", linewidth=0.5),
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="#ddd", alpha=0.85),
                zorder=5
            )
            last_annotated = row["date"]

    # ── Legend ──
    regime_patches = [mpatches.Patch(color=REGIME_COLORS[r], alpha=0.35, label=r) for r in REGIME_ORDER]
    legend1 = ax1.legend(handles=regime_patches, loc="upper left", framealpha=0.9,
                         edgecolor="#ccc", title="Market Regime", title_fontsize=9)
    ax1.add_artist(legend1)
    ax2.legend(loc="upper right", framealpha=0.9, edgecolor="#ccc")

    # ── Formatting ──
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax1.set_xlabel("")
    ax1.set_title("NIFTY 50 — Market Regime Classification\n(Jan 2021 – Mar 2026)",
                   fontweight="bold", pad=12)

    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    logger.info(f"  Saved → {output_path}")


# ═════════════════════════════════════════════════════════════════════════════
# PLOT 2: HMM State Probability Heatmap
# ═════════════════════════════════════════════════════════════════════════════

def plot_hmm_heatmap(df: pd.DataFrame, output_path: str = "output/02_hmm_state_probabilities.png"):
    """
    Fit a 4-state Gaussian HMM on (returns, σ30, momentum_30d) and plot
    state posterior probabilities as a heatmap.
    """
    from hmmlearn.hmm import GaussianHMM
    from sklearn.preprocessing import StandardScaler

    logger.info("Generating Plot 2: HMM State Probability Heatmap...")

    # ── Prepare features ──
    features = df[["log_return", "sigma_30", "mom_30d"]].dropna().copy()
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(features.values)

    # ── Fit HMM (4 states) ──
    n_states = 4
    model = GaussianHMM(
        n_components=n_states,
        covariance_type="full",
        n_iter=500,
        random_state=42,
        tol=1e-4
    )
    model.fit(X_scaled)
    posteriors = model.predict_proba(X_scaled)  # shape: (T, n_states)

    # ── Label states interpretably ──
    # Use state means to assign labels: highest return mean = Bull, lowest = Bear, etc.
    state_means = scaler.inverse_transform(model.means_)
    # state_means columns: [return, sigma_30, momentum_30d]

    ret_means = state_means[:, 0]
    vol_means = state_means[:, 1]

    label_map = {}
    remaining = list(range(n_states))

    # Bull: highest return mean
    bull_idx = remaining[np.argmax([ret_means[i] for i in remaining])]
    label_map[bull_idx] = "Bull"
    remaining.remove(bull_idx)

    # Bear: lowest return mean
    bear_idx = remaining[np.argmin([ret_means[i] for i in remaining])]
    label_map[bear_idx] = "Bear"
    remaining.remove(bear_idx)

    # High Volatility: highest vol mean among remaining
    hvol_idx = remaining[np.argmax([vol_means[i] for i in remaining])]
    label_map[hvol_idx] = "High Volatility"
    remaining.remove(hvol_idx)

    # Neutral: last remaining
    label_map[remaining[0]] = "Neutral"

    state_labels = [label_map[i] for i in range(n_states)]

    # ── Smooth posteriors (Gaussian filter for visual continuity) ──
    posteriors_smooth = np.zeros_like(posteriors)
    for s in range(n_states):
        posteriors_smooth[:, s] = gaussian_filter1d(posteriors[:, s], sigma=3)

    # Re-normalize after smoothing
    row_sums = posteriors_smooth.sum(axis=1, keepdims=True)
    posteriors_smooth = posteriors_smooth / row_sums

    # ── Reorder states for visual consistency ──
    desired_order = ["Bull", "Neutral", "High Volatility", "Bear"]
    reorder = [list(label_map.values()).index(d) if d in label_map.values() else 0 for d in desired_order]
    ordered_labels = [state_labels[i] for i in reorder]
    posteriors_ordered = posteriors_smooth[:, reorder]

    # ── Plot ──
    fig, ax = plt.subplots(figsize=(16, 4.5))

    # Custom colourmap: white → deep blue
    cmap = LinearSegmentedColormap.from_list("prob", ["#f8f9fa", "#264653", "#1a1a2e"], N=256)

    im = ax.imshow(
        posteriors_ordered.T,
        aspect="auto",
        interpolation="bilinear",
        cmap=cmap,
        vmin=0, vmax=1,
        extent=[0, len(features), -0.5, n_states - 0.5],
        origin="lower"
    )

    # Y-axis labels
    ax.set_yticks(range(n_states))
    ax.set_yticklabels(ordered_labels, fontweight="bold")

    # X-axis dates
    n_ticks = 12
    tick_positions = np.linspace(0, len(features) - 1, n_ticks, dtype=int)
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(
        [features.index[i].strftime("%b '%y") for i in tick_positions],
        rotation=45, ha="right"
    )

    # Colourbar
    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02, aspect=30)
    cbar.set_label("State Probability", fontsize=10)
    cbar.ax.tick_params(labelsize=8)

    ax.set_title("Hidden Markov Model — State Posterior Probabilities\n(4-State Gaussian HMM on Returns × Volatility × Momentum)",
                  fontweight="bold", pad=12)
    ax.set_xlabel("")

    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    logger.info(f"  Saved → {output_path}")

    return model, label_map, state_labels


# ═════════════════════════════════════════════════════════════════════════════
# PLOT 3: Markov Transition Matrix
# ═════════════════════════════════════════════════════════════════════════════

def plot_transition_matrix(df: pd.DataFrame, output_path: str = "output/03_transition_matrix.png"):
    """
    Compute and visualize the Markov transition probability matrix
    between regime states.
    """
    logger.info("Generating Plot 3: Markov Transition Matrix...")

    regimes = df["regime"].values
    unique_regimes = REGIME_ORDER  # Fixed order for consistency

    n = len(unique_regimes)
    counts = np.zeros((n, n), dtype=float)

    for t in range(len(regimes) - 1):
        from_r = regimes[t]
        to_r = regimes[t + 1]
        if from_r in unique_regimes and to_r in unique_regimes:
            i = unique_regimes.index(from_r)
            j = unique_regimes.index(to_r)
            counts[i, j] += 1

    # Normalize rows to get probabilities
    row_sums = counts.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1  # Avoid division by zero
    trans_matrix = counts / row_sums

    # ── Plot ──
    fig, ax = plt.subplots(figsize=(8, 6.5))

    # Custom diverging colourmap centred on persistence
    cmap = LinearSegmentedColormap.from_list(
        "trans", ["#f8f9fa", "#457b9d", "#1d3557"], N=256
    )

    # Mask zero-count transitions
    mask = (counts == 0)

    sns.heatmap(
        trans_matrix,
        annot=True,
        fmt=".3f",
        cmap=cmap,
        vmin=0, vmax=1,
        linewidths=1.5,
        linecolor="#e0e0e0",
        square=True,
        cbar_kws={"shrink": 0.75, "label": "Transition Probability"},
        xticklabels=unique_regimes,
        yticklabels=unique_regimes,
        ax=ax,
        mask=mask,
        annot_kws={"size": 12, "fontweight": "bold"}
    )

    # Highlight diagonal (persistence)
    for i in range(n):
        rect = plt.Rectangle((i, i), 1, 1, fill=False, edgecolor="#e85d04",
                               linewidth=2.5, zorder=5)
        ax.add_patch(rect)

    ax.set_xlabel("To →", fontweight="bold", fontsize=12, labelpad=10)
    ax.set_ylabel("← From", fontweight="bold", fontsize=12, labelpad=10)
    ax.set_title("Markov Regime Transition Matrix\n(Row-Stochastic: Rows Sum to 1.0)",
                  fontweight="bold", pad=15)

    # Add row-sum verification text
    for i in range(n):
        row_sum = trans_matrix[i, :].sum()
        ax.text(n + 0.2, i + 0.5, f"Σ = {row_sum:.3f}",
                va="center", fontsize=8, color="#666", fontstyle="italic")

    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
    plt.setp(ax.yaxis.get_majorticklabels(), rotation=0)

    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    logger.info(f"  Saved → {output_path}")

    return trans_matrix


# ═════════════════════════════════════════════════════════════════════════════
# PLOT 4: 3D Regime Surface
# ═════════════════════════════════════════════════════════════════════════════

def plot_3d_regime_surface(df: pd.DataFrame, output_path: str = "output/04_3d_regime_surface.html",
                            static_path: str = "output/04_3d_regime_surface.png"):
    """
    3D scatter plot: Volatility (σ30) × Momentum (30d) × Breadth (% Above 50DMA)
    coloured by regime. Uses Plotly for interactivity + static export.
    """
    import plotly.graph_objects as go
    import plotly.io as pio

    logger.info("Generating Plot 4: 3D Regime Surface...")

    plot_df = df[["sigma_30", "mom_30d", "pct_above_50dma", "regime"]].dropna().copy()
    plot_df["sigma_30_pct"] = plot_df["sigma_30"] * 100
    plot_df["mom_30d_pct"] = plot_df["mom_30d"] * 100

    # Plotly colour map (muted, professional)
    plotly_colors = {
        "Bull":            "#2d6a4f",
        "Bear":            "#9d0208",
        "High Volatility": "#e85d04",
        "Low Volatility":  "#457b9d",
        "Transition":      "#adb5bd",
    }

    fig = go.Figure()

    for regime in REGIME_ORDER:
        subset = plot_df[plot_df["regime"] == regime]
        if subset.empty:
            continue

        fig.add_trace(go.Scatter3d(
            x=subset["sigma_30_pct"],
            y=subset["mom_30d_pct"],
            z=subset["pct_above_50dma"],
            mode="markers",
            name=regime,
            marker=dict(
                size=3,
                color=plotly_colors.get(regime, "#888"),
                opacity=0.55,
                line=dict(width=0.3, color="rgba(0,0,0,0.15)")
            ),
            text=[f"Date: {d.strftime('%d %b %Y')}<br>"
                  f"σ₃₀: {row['sigma_30_pct']:.1f}%<br>"
                  f"Mom: {row['mom_30d_pct']:.1f}%<br>"
                  f"Breadth: {row['pct_above_50dma']:.1f}%"
                  for d, row in subset.iterrows()],
            hoverinfo="text+name"
        ))

    # Cluster centroids
    for regime in REGIME_ORDER:
        subset = plot_df[plot_df["regime"] == regime]
        if len(subset) < 5:
            continue
        cx = subset["sigma_30_pct"].median()
        cy = subset["mom_30d_pct"].median()
        cz = subset["pct_above_50dma"].median()

        fig.add_trace(go.Scatter3d(
            x=[cx], y=[cy], z=[cz],
            mode="markers+text",
            name=f"{regime} (centroid)",
            marker=dict(
                size=10,
                color=plotly_colors.get(regime, "#888"),
                opacity=0.95,
                symbol="diamond",
                line=dict(width=1.5, color="#1a1a2e")
            ),
            text=[regime],
            textposition="top center",
            textfont=dict(size=10, color="#1a1a2e"),
            showlegend=False,
            hoverinfo="text"
        ))

    fig.update_layout(
        title=dict(
            text="3D Regime Space — Volatility × Momentum × Breadth<br>"
                 "<sub>Each point = 1 trading day; diamonds = regime centroids</sub>",
            font=dict(size=16, color="#1a1a2e"),
            x=0.5
        ),
        scene=dict(
            xaxis_title="Annualized Volatility σ₃₀ (%)",
            yaxis_title="30-Day Momentum (%)",
            zaxis_title="Breadth: % Above 50-DMA",
            xaxis=dict(backgroundcolor="#fafafa", gridcolor="#e0e0e0"),
            yaxis=dict(backgroundcolor="#fafafa", gridcolor="#e0e0e0"),
            zaxis=dict(backgroundcolor="#fafafa", gridcolor="#e0e0e0"),
            camera=dict(eye=dict(x=1.6, y=-1.8, z=0.8)),
        ),
        legend=dict(
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#ccc",
            borderwidth=1,
            font=dict(size=11),
            itemsizing="constant"
        ),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#fafafa",
        margin=dict(l=20, r=20, t=80, b=20),
        width=1100,
        height=750,
    )

    # Save interactive HTML
    fig.write_html(output_path, include_plotlyjs="cdn")
    logger.info(f"  Saved interactive → {output_path}")

    # Save static PNG
    try:
        fig.write_image(static_path, width=1100, height=750, scale=3)
        logger.info(f"  Saved static → {static_path}")
    except Exception as e:
        logger.warning(f"  Static PNG export failed (kaleido may be missing): {e}")
        logger.info("  Interactive HTML still available.")
