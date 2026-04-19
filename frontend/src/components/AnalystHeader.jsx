import React, { memo } from 'react';

/**
 * Bloomberg-style analyst summary header.
 * Compact 2-line bar showing price, change, sector, risk, trend, and position.
 */
function AnalystHeader({ overview, signals }) {
    if (!overview) return null;

    const { header, fundamentals, risk, factors } = overview;
    const price = header?.last_close;
    const change = header?.return_1d;
    const isPositive = change >= 0;

    return (
        <div className="bg-zinc-900/40 backdrop-blur-xl border border-white/5 rounded-lg px-4 py-2">
            {/* Line 1: Symbol, Price, Change */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <span className="text-lg font-bold text-white tracking-tight font-mono">
                        {overview.symbol?.replace('.NS', '')}
                    </span>
                    <span className="text-lg font-bold text-white font-mono">
                        ₹{price?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                    <span className={`text-sm font-bold font-mono px-1.5 py-0.5 rounded ${isPositive ? 'text-emerald-400 bg-emerald-400/10' : 'text-red-400 bg-red-400/10'
                        }`}>
                        {isPositive ? '+' : ''}{change}%
                        <span className="ml-1">{isPositive ? '▲' : '▼'}</span>
                    </span>
                </div>
                <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 bg-white/5 border border-white/5 text-[10px] font-semibold rounded text-zinc-400 uppercase tracking-wider">
                        {header?.sector || 'N/A'}
                    </span>
                </div>
            </div>

            {/* Line 2: Key metrics bar */}
            <div className="flex items-center gap-1.5 mt-1 text-[11px] text-zinc-400  flex-wrap">
                <MetricPill label="Beta" value={risk?.beta} warn={risk?.beta > 1.2} />
                <Sep />
                <MetricPill label="Vol" value={`${risk?.volatility_30d}%`} />
                <Sep />
                <MetricPill label="P/E" value={fundamentals?.pe_ratio?.toFixed(1) || 'N/A'} badge={signals?.valuationSignal} />
                <Sep />
                <MetricPill label="Mom 90D" value={`${(factors?.momentum_90d * 100).toFixed(1)}%`} badge={signals?.momentumSignal} />
                <Sep />
                <span className={`font-semibold ${signals?.trendState?.color || 'text-zinc-400'}`}>
                    Trend: {signals?.trendState?.label} {signals?.trendState?.icon}
                </span>
                <Sep />
                <span className="text-zinc-500">
                    {signals?.maPosition?.label}
                </span>
            </div>
        </div>
    );
}

const Sep = () => <span className="text-zinc-700 select-none">│</span>;

const MetricPill = ({ label, value, warn, badge }) => (
    <span className="inline-flex items-center gap-1">
        <span className="text-zinc-500">{label}:</span>
        <span className={`font-mono font-semibold ${warn ? 'text-orange-400' : 'text-zinc-300'}`}>{value}</span>
        {badge && <span className={`text-[9px] font-bold ${badge.color}`}>({badge.label})</span>}
    </span>
);

export default memo(AnalystHeader);
