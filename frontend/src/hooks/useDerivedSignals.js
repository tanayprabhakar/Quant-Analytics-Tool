import { useMemo } from 'react';

/**
 * Compute client-side derived signals from cached data.
 * All computations are memoized — only rerun when deps change.
 */
export default function useDerivedSignals(overview, performance) {
    // Trend State
    const trendState = useMemo(() => {
        if (!performance?.data?.length || !overview) return { label: '—', color: 'text-zinc-400', icon: '—' };

        const data = performance.data;
        const last = data[data.length - 1];
        if (!last) return { label: '—', color: 'text-zinc-400', icon: '—' };

        const price = last.close;
        const ma50 = last.sma_50;
        const ma200 = last.sma_200;

        if (price == null || ma50 == null || ma200 == null) {
            return { label: 'NO DATA', color: 'text-zinc-500', icon: '—' };
        }

        if (price > ma50 && ma50 > ma200) return { label: 'STRONG UPTREND', color: 'text-emerald-400', icon: '▲' };
        if (price > ma50 && ma50 <= ma200) return { label: 'RECOVERY', color: 'text-blue-400', icon: '↗' };
        if (price < ma50 && ma50 > ma200) return { label: 'PULLBACK', color: 'text-amber-400', icon: '↘' };
        if (price < ma50 && ma50 < ma200) return { label: 'DOWNTREND', color: 'text-red-400', icon: '▼' };
        return { label: 'SIDEWAYS', color: 'text-zinc-400', icon: '→' };
    }, [performance, overview]);

    // Position relative to moving averages
    const maPosition = useMemo(() => {
        if (!performance?.data?.length) return { above50: false, above200: false, label: '—' };
        const last = performance.data[performance.data.length - 1];
        if (!last) return { above50: false, above200: false, label: '—' };

        const above50 = last.close > (last.sma_50 || 0);
        const above200 = last.close > (last.sma_200 || 0);

        let label = 'Below all DMAs';
        if (above50 && above200) label = 'Above 50 & 200 DMA ✅';
        else if (above50) label = 'Above 50 DMA only';
        else if (above200) label = 'Above 200 DMA only';
        else label = 'Below 50 & 200 DMA ⚠️';

        return { above50, above200, label };
    }, [performance]);

    // Drawdown from rolling max
    const drawdown = useMemo(() => {
        if (!performance?.data?.length) return { current: 0, max: 0 };

        const closes = performance.data.map(d => d.close).filter(Boolean);
        if (closes.length === 0) return { current: 0, max: 0 };

        let rollingMax = -Infinity;
        let maxDrawdown = 0;

        for (let i = 0; i < closes.length; i++) {
            if (closes[i] > rollingMax) rollingMax = closes[i];
            const dd = (closes[i] / rollingMax) - 1;
            if (dd < maxDrawdown) maxDrawdown = dd;
        }

        const currentPrice = closes[closes.length - 1];
        const currentDD = rollingMax > 0 ? (currentPrice / rollingMax) - 1 : 0;

        return {
            current: (currentDD * 100).toFixed(1),
            max: (maxDrawdown * 100).toFixed(1),
        };
    }, [performance]);

    // Relative strength (stock vs index cumulative return)
    const relativeStrength = useMemo(() => {
        if (!performance?.data?.length) return { value: 0, label: '—' };

        const data = performance.data;
        const first = data[0];
        const last = data[data.length - 1];

        if (!first?.close || !last?.close) return { value: 0, label: '—' };

        const stockReturn = (last.close / first.close) - 1;
        // relative_perf is already normalized in backend
        const relPerf = last.relative_perf;
        const relStr = relPerf != null ? ((relPerf - 1) * 100).toFixed(1) : '—';

        return {
            value: parseFloat(relStr) || 0,
            stockReturn: (stockReturn * 100).toFixed(1),
            label: relPerf > 1.05 ? 'Outperforming' : relPerf < 0.95 ? 'Underperforming' : 'In-line',
            color: relPerf > 1.0 ? 'text-emerald-400' : 'text-red-400',
        };
    }, [performance]);

    // Valuation signal from P/E
    const valuationSignal = useMemo(() => {
        if (!overview?.fundamentals) return { label: '—', color: 'text-zinc-400' };
        const pe = overview.fundamentals.pe_ratio;
        if (!pe || pe <= 0) return { label: 'N/A', color: 'text-zinc-500' };
        if (pe < 15) return { label: 'Cheap', color: 'text-emerald-400' };
        if (pe < 25) return { label: 'Neutral', color: 'text-amber-400' };
        return { label: 'Expensive', color: 'text-red-400' };
    }, [overview]);

    // Momentum signal
    const momentumSignal = useMemo(() => {
        if (!overview?.factors) return { label: '—', color: 'text-zinc-400' };
        const m90 = overview.factors.momentum_90d;
        if (m90 > 0.1) return { label: 'Strong', color: 'text-emerald-400' };
        if (m90 > 0) return { label: 'Mild', color: 'text-blue-400' };
        if (m90 > -0.1) return { label: 'Weak', color: 'text-amber-400' };
        return { label: 'Negative', color: 'text-red-400' };
    }, [overview]);

    return {
        trendState,
        maPosition,
        drawdown,
        relativeStrength,
        valuationSignal,
        momentumSignal,
    };
}
