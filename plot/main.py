#!/usr/bin/env python3
"""
main.py
=======
Market Regime Visualization Suite — Entry Point

Orchestrates the full pipeline:
  1. Fetch and prepare NIFTY 50 + constituent data
  2. Compute indicators (momentum, volatility, breadth)
  3. Classify market regimes
  4. Generate all 4 publication-quality visualizations

Usage:
  cd plot/
  pip install -r requirements.txt
  python main.py

Output:
  output/
    01_regime_overlay.png          (300 DPI)
    02_hmm_state_probabilities.png (300 DPI)
    03_transition_matrix.png       (300 DPI)
    04_3d_regime_surface.html      (interactive Plotly)
    04_3d_regime_surface.png       (static 300 DPI)
    analysis_summary.csv           (full dataset export)
"""

import os
import sys
import time
import logging
import warnings

warnings.filterwarnings("ignore")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


def main():
    t0 = time.time()
    logger.info("=" * 70)
    logger.info("  NIFTY 50 Market Regime Visualization Suite")
    logger.info("  Analysis Window: January 2021 – March 2026")
    logger.info("=" * 70)

    # ── Create output directory ──
    os.makedirs("output", exist_ok=True)

    # ── Step 1: Build analysis dataset ──
    logger.info("\n─── STEP 1: Data Acquisition & Feature Engineering ───")
    from regime_engine import build_analysis_dataset
    master_df, constituents = build_analysis_dataset()

    # Export dataset for reproducibility
    master_df.to_csv("output/analysis_summary.csv")
    logger.info(f"  Dataset exported → output/analysis_summary.csv")

    # Print summary statistics
    logger.info(f"\n  Dataset shape: {master_df.shape}")
    logger.info(f"  Date range:    {master_df.index[0].date()} → {master_df.index[-1].date()}")
    logger.info(f"  NIFTY range:   {master_df['close'].min():,.0f} → {master_df['close'].max():,.0f}")
    logger.info(f"\n  Regime Distribution:")
    for regime, count in master_df['regime'].value_counts().items():
        pct = count / len(master_df) * 100
        logger.info(f"    {regime:20s}: {count:4d} days ({pct:5.1f}%)")

    # ── Step 2: Generate visualizations ──
    logger.info("\n─── STEP 2: Generating Visualizations ───")

    from visualizations import (
        plot_regime_overlay,
        plot_hmm_heatmap,
        plot_transition_matrix,
        plot_3d_regime_surface,
    )

    # Plot 1: Regime Overlay
    plot_regime_overlay(master_df, "output/01_regime_overlay.png")

    # Plot 2: HMM Heatmap
    hmm_model, label_map, state_labels = plot_hmm_heatmap(
        master_df, "output/02_hmm_state_probabilities.png"
    )
    logger.info(f"  HMM state labels: {state_labels}")
    logger.info(f"  HMM log-likelihood: {hmm_model.score(master_df[['log_return', 'sigma_30', 'mom_30d']].dropna().values):.2f}")

    # Plot 3: Transition Matrix
    trans_matrix = plot_transition_matrix(
        master_df, "output/03_transition_matrix.png"
    )

    # Print transition matrix
    from regime_engine import REGIME_ORDER
    import numpy as np
    logger.info("\n  Transition Matrix (rows = From, cols = To):")
    header = "                    " + "  ".join(f"{r:>14s}" for r in REGIME_ORDER)
    logger.info(f"  {header}")
    for i, r_from in enumerate(REGIME_ORDER):
        row = "  ".join(f"{trans_matrix[i, j]:14.4f}" for j in range(len(REGIME_ORDER)))
        logger.info(f"  {r_from:20s}{row}")

    # Plot 4: 3D Regime Surface
    plot_3d_regime_surface(
        master_df,
        "output/04_3d_regime_surface.html",
        "output/04_3d_regime_surface.png"
    )

    # ── Summary ──
    elapsed = time.time() - t0
    logger.info("\n" + "=" * 70)
    logger.info(f"  All visualizations generated in {elapsed:.1f}s")
    logger.info("  Output directory: plot/output/")
    logger.info("=" * 70)

    # List output files
    for f in sorted(os.listdir("output")):
        fpath = os.path.join("output", f)
        size_kb = os.path.getsize(fpath) / 1024
        logger.info(f"    {f:45s}  {size_kb:8.1f} KB")

    logger.info("\n  Done. ✓")


if __name__ == "__main__":
    main()
