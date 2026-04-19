import React, { memo, useMemo } from 'react';

/**
 * Compact 6-card analytics grid.
 * Each card is small + dense: ~3 lines of data + colored signal badge.
 */
function AnalyticsGrid({ overview, signals }) {
    if (!overview) return null;

    const { fundamentals, risk, factors } = overview;

    const cards = useMemo(() => [
        // Valuation
        {
            title: 'Valuation',
            items: [
                { label: 'P/E', value: fundamentals?.pe_ratio?.toFixed(1) || 'N/A' },
                { label: 'EPS', value: fundamentals?.eps?.toFixed(2) || 'N/A' },
                { label: 'MktCap', value: formatCr(fundamentals?.market_cap) },
            ],
            signal: signals?.valuationSignal,
        },
        // Momentum
        {
            title: 'Momentum',
            items: [
                { label: '30D', value: formatPct(factors?.momentum_30d, true) },
                { label: '90D', value: formatPct(factors?.momentum_90d, true) },
                { label: 'Rank', value: `${factors?.momentum_percentile?.toFixed(0) || '—'} / 100` },
            ],
            signal: signals?.momentumSignal,
        },
        // Trend
        {
            title: 'Trend',
            items: [
                { label: 'State', value: signals?.trendState?.label, color: signals?.trendState?.color },
                { label: 'Position', value: signals?.maPosition?.above50 ? 'Above 50D' : 'Below 50D' },
                { label: '200 DMA', value: signals?.maPosition?.above200 ? 'Above ✅' : 'Below ⚠️' },
            ],
            signal: signals?.trendState,
        },
        // Risk
        {
            title: 'Risk',
            items: [
                { label: 'Beta', value: risk?.beta?.toFixed(2) },
                { label: 'Vol 30D', value: `${risk?.volatility_30d}%` },
                { label: 'MaxDD', value: `${risk?.max_drawdown_1y}%`, color: 'text-red-400' },
            ],
            signal: risk?.beta > 1.2
                ? { label: 'High', color: 'text-orange-400' }
                : { label: 'Normal', color: 'text-emerald-400' },
        },
        // Relative
        {
            title: 'Relative',
            items: [
                { label: 'vs NIFTY', value: `${signals?.relativeStrength?.value > 0 ? '+' : ''}${signals?.relativeStrength?.value}%` },
                { label: 'Stock', value: `${signals?.relativeStrength?.stockReturn}%` },
                { label: 'Verdict', value: signals?.relativeStrength?.label },
            ],
            signal: signals?.relativeStrength,
        },
        // Drawdown
        {
            title: 'Drawdown',
            items: [
                { label: 'Current', value: `${signals?.drawdown?.current}%` },
                { label: 'Max', value: `${signals?.drawdown?.max}%`, color: 'text-red-400' },
                { label: 'Recovery', value: signals?.drawdown?.current > -5 ? 'Near High' : 'In Drawdown' },
            ],
            signal: parseFloat(signals?.drawdown?.current) > -5
                ? { label: 'OK', color: 'text-emerald-400' }
                : { label: 'Deep', color: 'text-red-400' },
        },
    ], [overview, signals]);

    return (
        <div className="grid grid-cols-3 md:grid-cols-6 gap-1.5">
            {cards.map(card => (
                <div
                    key={card.title}
                    className="bg-zinc-900/40 backdrop-blur border border-white/5 rounded-lg px-2.5 py-2 hover:border-white/10 transition-colors"
                >
                    {/* Card header */}
                    <div className="flex items-center justify-between mb-1.5">
                        <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">{card.title}</span>
                        {card.signal && (
                            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded bg-white/5 ${card.signal.color}`}>
                                {card.signal.label}
                            </span>
                        )}
                    </div>

                    {/* Card body */}
                    {card.items.map(item => (
                        <div key={item.label} className="flex justify-between items-center py-0.5">
                            <span className="text-[10px] text-zinc-500">{item.label}</span>
                            <span className={`text-[11px] font-mono font-semibold ${item.color || 'text-zinc-200'}`}>
                                {item.value}
                            </span>
                        </div>
                    ))}
                </div>
            ))}
        </div>
    );
}

function formatCr(val) {
    if (!val || val === 0) return 'N/A';
    const cr = val / 1e7;
    if (cr >= 100000) return `${(cr / 100000).toFixed(1)}L Cr`;
    if (cr >= 1000) return `${(cr / 1000).toFixed(1)}K Cr`;
    return `${cr.toFixed(0)} Cr`;
}

function formatPct(val, multiply = false) {
    if (val == null) return 'N/A';
    const pct = multiply ? val * 100 : val;
    const formatted = pct.toFixed(1);
    return pct > 0 ? `+${formatted}%` : `${formatted}%`;
}

export default memo(AnalyticsGrid);
