import React, { useState, useEffect } from 'react';
import { Activity, Zap, BarChart3, Globe, AlertCircle, TrendingUp } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';
const API_KEY = import.meta.env.VITE_API_KEY || '';
const AUTH_HEADERS = API_KEY ? { 'X-API-Key': API_KEY } : {};

/* ── Helpers ── */
const regimeColor = (regime) => {
    if (regime === 'Risk-On') return { bg: 'bg-emerald-500/15', text: 'text-emerald-400', dot: 'bg-emerald-400' };
    if (regime === 'Risk-Off') return { bg: 'bg-rose-500/15', text: 'text-rose-400', dot: 'bg-rose-400' };
    return { bg: 'bg-amber-500/15', text: 'text-amber-400', dot: 'bg-amber-400' };
};
const pctColor = (v) => v >= 0 ? 'text-emerald-400' : 'text-rose-400';
const pctSign = (v) => v > 0 ? `+${v}` : `${v}`;

/* ── Shared Panel ── */
const Panel = ({ children, title, icon: Icon, className = '' }) => (
    <div className={`bg-zinc-900/50 border border-white/[0.04] rounded-xl flex flex-col ${className}`}>
        {title && (
            <div className="flex items-center gap-1.5 px-4 pt-3 pb-2">
                {Icon && <Icon className="w-3 h-3 text-zinc-600" />}
                <span className="text-[10px] font-semibold text-zinc-500 uppercase tracking-[0.12em]">{title}</span>
            </div>
        )}
        <div className="px-4 pb-3 flex-1">{children}</div>
    </div>
);

/* ── Breadth Bar ── */
const BreadthBar = ({ label, value, color }) => (
    <div className="flex items-center gap-3">
        <span className="text-[10px] font-medium text-zinc-500 w-16 shrink-0">{label}</span>
        <div className="flex-1 h-1.5 bg-zinc-800/80 rounded-full overflow-hidden">
            <div className={`h-full ${color} rounded-full transition-all duration-1000`} style={{ width: `${value}%` }} />
        </div>
        <span className="text-[11px] font-bold text-zinc-300 w-10 text-right tabular-nums">{value}%</span>
    </div>
);

/* ── Main Component ── */
function MarketMonitor({ onSymbolClick }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchData = async () => {
        setError(null);
        try {
            const res = await fetch(`${API_BASE}/market/advanced_monitor`, { headers: AUTH_HEADERS });
            if (!res.ok) throw new Error(`Server error: ${res.status}`);
            const json = await res.json();
            if (json.error) throw new Error(json.error);
            setData(json);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
        const t = setInterval(fetchData, 60000);
        return () => clearInterval(t);
    }, []);

    /* ── Loading ── */
    if (loading) return (
        <div className="flex flex-col h-72 items-center justify-center gap-3">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-indigo-500" />
            <p className="text-zinc-600 text-[10px] font-medium animate-pulse uppercase tracking-widest">
                Loading Market Structure…
            </p>
        </div>
    );

    /* ── Error / No Data ── */
    if (error || !data) return (
        <div className="bg-rose-500/10 border border-rose-500/20 p-4 rounded-xl text-rose-400 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error || 'No data received from server'}</span>
            <button
                onClick={() => { setLoading(true); fetchData(); }}
                className="ml-auto px-3 py-1 bg-rose-500/20 hover:bg-rose-500/30 rounded-lg text-rose-300 font-semibold transition-colors"
            >
                Retry
            </button>
        </div>
    );

    const { regime, trend, indices = [], breadth = {}, momentum = {}, sectors = [], volatility = {}, leaders = [], laggards = [], as_of, universe_count } = data;
    const rc = regimeColor(regime);
    const breadthStats = breadth.stats || {};

    return (
        <div className="space-y-4">

            {/* ═══ ROW 1: REGIME STRIP ═══ */}
            <div className={`${rc.bg} border border-white/[0.04] rounded-xl px-5 py-3 flex flex-wrap items-center gap-x-8 gap-y-2`}>
                <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${rc.dot} animate-pulse`} />
                    <span className={`text-sm font-bold ${rc.text}`}>{regime}</span>
                    <span className="text-[10px] text-zinc-500 font-medium">Regime</span>
                </div>
                <div className="h-4 w-px bg-white/10" />
                <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-zinc-500 font-medium">Trend</span>
                    <span className={`text-xs font-bold ${trend === 'Bullish' ? 'text-emerald-400' : 'text-rose-400'}`}>{trend}</span>
                </div>
                <div className="h-4 w-px bg-white/10" />
                <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-zinc-500 font-medium">Breadth</span>
                    <span className={`text-xs font-bold ${(breadthStats.pct_above_50 || 0) > 60 ? 'text-emerald-400'
                            : (breadthStats.pct_above_50 || 0) < 40 ? 'text-rose-400'
                                : 'text-amber-400'
                        }`}>
                        {(breadthStats.pct_above_50 || 0) > 60 ? 'Strong' : (breadthStats.pct_above_50 || 0) < 40 ? 'Weak' : 'Mixed'}
                    </span>
                </div>
                <div className="h-4 w-px bg-white/10" />
                <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-zinc-500 font-medium">Volatility</span>
                    <span className={`text-xs font-bold ${volatility.status === 'Low' ? 'text-emerald-400'
                            : volatility.status === 'High' ? 'text-rose-400'
                                : 'text-zinc-300'
                        }`}>
                        {volatility.status} ({volatility.value}%)
                    </span>
                </div>
                <div className="ml-auto text-[9px] text-zinc-600 font-medium tabular-nums">
                    {universe_count || '—'} stocks · {as_of}
                </div>
            </div>

            {/* ═══ ROW 2: INDEX TERMINAL + MOVERS ═══ */}
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
                <Panel title="Index Structure" icon={Globe} className="lg:col-span-3">
                    <table className="w-full text-left">
                        <thead>
                            <tr className="text-[9px] text-zinc-600 uppercase tracking-wider border-b border-white/[0.04]">
                                <th className="pb-2 font-semibold">Index</th>
                                <th className="pb-2 text-right font-semibold">Price</th>
                                <th className="pb-2 text-right font-semibold">1D</th>
                                <th className="pb-2 text-right font-semibold">vs 50D</th>
                                <th className="pb-2 text-right font-semibold">52W Hi</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/[0.03]">
                            {indices.map(idx => (
                                <tr key={idx.symbol} className="hover:bg-white/[0.015] transition-colors">
                                    <td className="py-2.5 text-xs font-semibold text-zinc-300">{idx.name}</td>
                                    <td className="py-2.5 text-right text-[11px] font-mono text-zinc-400 tabular-nums">{idx.price.toLocaleString()}</td>
                                    <td className={`py-2.5 text-right text-[11px] font-bold tabular-nums ${pctColor(idx.change_1d)}`}>{pctSign(idx.change_1d)}%</td>
                                    <td className={`py-2.5 text-right text-[11px] font-medium tabular-nums ${idx.vs_50dma >= 0 ? 'text-indigo-400' : 'text-zinc-500'}`}>{pctSign(idx.vs_50dma)}%</td>
                                    <td className="py-2.5 text-right text-[11px] font-medium tabular-nums text-zinc-500">
                                        {idx.dist_52w_high === 0
                                            ? <span className="text-emerald-400 font-bold text-[9px] uppercase">ATH</span>
                                            : `${idx.dist_52w_high}%`}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </Panel>

                <Panel title="Top Movers" icon={TrendingUp} className="lg:col-span-2">
                    <div className="space-y-1.5">
                        {leaders.slice(0, 4).map(s => (
                            <button key={s.symbol} onClick={() => onSymbolClick?.(s.symbol)}
                                className="w-full flex items-center justify-between py-1.5 px-1 rounded-md hover:bg-white/[0.03] transition-colors group">
                                <span className="text-[11px] font-semibold text-zinc-300 group-hover:text-white">{s.symbol.replace('.NS', '')}</span>
                                <div className="flex items-center gap-2">
                                    {s.vol_ratio >= 1.5 && (
                                        <span className="text-[8px] font-bold text-amber-500/70 bg-amber-500/10 px-1 py-0.5 rounded uppercase">
                                            {s.vol_ratio}x vol
                                        </span>
                                    )}
                                    <span className="text-[11px] font-bold text-emerald-400 tabular-nums">+{s.return_1d}%</span>
                                </div>
                            </button>
                        ))}
                    </div>
                    <div className="border-t border-white/[0.04] mt-2 pt-2 space-y-1.5">
                        {laggards.slice(0, 4).map(s => (
                            <button key={s.symbol} onClick={() => onSymbolClick?.(s.symbol)}
                                className="w-full flex items-center justify-between py-1.5 px-1 rounded-md hover:bg-white/[0.03] transition-colors group">
                                <span className="text-[11px] font-semibold text-zinc-300 group-hover:text-white">{s.symbol.replace('.NS', '')}</span>
                                <div className="flex items-center gap-2">
                                    {s.vol_ratio >= 1.5 && (
                                        <span className="text-[8px] font-bold text-amber-500/70 bg-amber-500/10 px-1 py-0.5 rounded uppercase">
                                            {s.vol_ratio}x vol
                                        </span>
                                    )}
                                    <span className="text-[11px] font-bold text-rose-400 tabular-nums">{s.return_1d}%</span>
                                </div>
                            </button>
                        ))}
                    </div>
                </Panel>
            </div>

            {/* ═══ ROW 3: BREADTH + MOMENTUM ═══ */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Panel title="Breadth Health" icon={Activity}>
                    <div className="space-y-3">
                        <BreadthBar label="20 DMA" value={breadthStats.pct_above_20 || 0} color="bg-indigo-500" />
                        <BreadthBar label="50 DMA" value={breadthStats.pct_above_50 || 0} color="bg-purple-500" />
                    </div>
                    <div className="mt-3 pt-2 border-t border-white/[0.04] flex justify-between text-[10px] font-medium text-zinc-500">
                        <span>A/D Ratio</span>
                        <span className={(breadth.advancers || 0) >= (breadth.decliners || 0) ? 'text-emerald-400' : 'text-rose-400'}>
                            {breadth.advancers || 0} / {breadth.decliners || 0}
                            <span className="text-zinc-600 ml-1">({((breadth.advancers || 0) / ((breadth.decliners || 1))).toFixed(1)}x)</span>
                        </span>
                    </div>
                </Panel>

                <Panel title="Momentum Breadth" icon={Zap}>
                    <div className="grid grid-cols-2 gap-3 h-full">
                        <div className="flex flex-col items-center justify-center bg-white/[0.02] rounded-lg border border-white/[0.04] py-4">
                            <span className="text-2xl font-bold text-zinc-200 tabular-nums">{momentum.pct_positive_30d ?? 0}%</span>
                            <span className="text-[9px] text-zinc-500 font-semibold uppercase mt-1">Positive 30D</span>
                        </div>
                        <div className="flex flex-col items-center justify-center bg-white/[0.02] rounded-lg border border-white/[0.04] py-4">
                            <span className="text-2xl font-bold text-indigo-400 tabular-nums">{momentum.pct_top_decile ?? 0}%</span>
                            <span className="text-[9px] text-zinc-500 font-semibold uppercase mt-1">Top Decile</span>
                        </div>
                    </div>
                </Panel>
            </div>

            {/* ═══ ROW 4: SECTOR ROTATION ═══ */}
            <Panel title={`Sector Rotation · ${sectors.length} sectors`} icon={BarChart3}>
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-2">
                    {sectors.map(s => (
                        <div key={s.sector}
                            className="p-2.5 bg-white/[0.015] border border-white/[0.04] rounded-lg hover:border-white/[0.08] transition-all">
                            <div className="flex items-baseline justify-between mb-1">
                                <span className="text-[11px] font-semibold text-zinc-300">{s.sector}</span>
                                <span className="text-[9px] text-zinc-600 tabular-nums">{s.count}</span>
                            </div>
                            <div className="flex items-baseline justify-between">
                                <span className={`text-xs font-bold tabular-nums ${pctColor(s.change_1d)}`}>{pctSign(s.change_1d)}%</span>
                                <span className={`text-[9px] font-medium tabular-nums ${pctColor(s.change_1w)} opacity-60`}>{pctSign(s.change_1w)}% w</span>
                            </div>
                        </div>
                    ))}
                </div>
            </Panel>

        </div>
    );
}

export default MarketMonitor;
