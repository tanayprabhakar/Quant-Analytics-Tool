import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Filter, ArrowUpDown, ArrowUp, ArrowDown, BarChart3, X, RefreshCw, AlertCircle, Columns } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';
const API_KEY = import.meta.env.VITE_API_KEY || '';
const AUTH_HEADERS = API_KEY ? { 'X-API-Key': API_KEY } : {};

/* ── Signal / Label color maps ── */
const SIG = { Strong: { bg: 'bg-emerald-500/15', text: 'text-emerald-400', dot: 'bg-emerald-400' }, Watch: { bg: 'bg-amber-500/15', text: 'text-amber-400', dot: 'bg-amber-400' }, Weak: { bg: 'bg-zinc-700/30', text: 'text-zinc-500', dot: 'bg-zinc-500' } };
const TREND_C = { Uptrend: 'text-emerald-400', Sideways: 'text-amber-400', Downtrend: 'text-rose-400' };
const VOL_C = { Low: 'text-emerald-400', Normal: 'text-zinc-300', High: 'text-rose-400' };
const pctFmt = (v) => v == null ? '—' : `${(v * 100).toFixed(1)}%`;
const pctColor = (v) => v >= 0 ? 'text-emerald-400' : 'text-rose-400';

/* ── Chip toggle button ── */
const Chip = ({ label, active, onClick }) => (
    <button onClick={onClick}
        className={`px-2.5 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider transition-all border ${active
            ? 'bg-white/10 border-white/20 text-zinc-200'
            : 'bg-transparent border-white/5 text-zinc-600 hover:text-zinc-400 hover:border-white/10'
        }`}>{label}</button>
);

/* ── Mini Histogram (canvas-based) ── */
const MomentumHistogram = ({ data, selected, height = 120 }) => {
    const canvasRef = useRef(null);
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas || !data.length) return;
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        const w = canvas.clientWidth; const h = canvas.clientHeight;
        canvas.width = w * dpr; canvas.height = h * dpr;
        ctx.scale(dpr, dpr);
        ctx.clearRect(0, 0, w, h);

        const vals = data.map(d => d.momentum_90d);
        const min = Math.min(...vals); const max = Math.max(...vals);
        const range = max - min || 1;
        const bins = 30; const binW = range / bins;
        const counts = new Array(bins).fill(0);
        const binStocks = new Array(bins).fill(null).map(() => new Set());
        vals.forEach((v, i) => { const b = Math.min(Math.floor((v - min) / binW), bins - 1); counts[b]++; binStocks[b].add(data[i].symbol); });
        const maxCount = Math.max(...counts);
        const barW = (w - 20) / bins;
        const selectedSet = new Set(selected);

        for (let i = 0; i < bins; i++) {
            const barH = maxCount > 0 ? (counts[i] / maxCount) * (h - 24) : 0;
            const x = 10 + i * barW;
            const hasSelected = [...binStocks[i]].some(s => selectedSet.has(s));
            ctx.fillStyle = hasSelected ? 'rgba(99,102,241,0.7)' : 'rgba(255,255,255,0.08)';
            ctx.fillRect(x, h - 12 - barH, barW - 1, barH);
        }
        // X-axis labels
        ctx.fillStyle = '#52525b'; ctx.font = '9px Inter, sans-serif'; ctx.textAlign = 'center';
        ctx.fillText(`${(min * 100).toFixed(0)}%`, 10, h - 1);
        ctx.fillText(`${(max * 100).toFixed(0)}%`, w - 10, h - 1);
        ctx.fillText('Momentum 90D', w / 2, h - 1);
    }, [data, selected]);

    return <canvas ref={canvasRef} style={{ width: '100%', height }} className="rounded-lg" />;
};

/* ── Comparison Panel ── */
const ComparisonPanel = ({ stocks, onClose }) => {
    if (!stocks.length) return null;
    const metrics = [
        { key: 'momentum_30d', label: 'Mom 30D', fmt: pctFmt },
        { key: 'momentum_90d', label: 'Mom 90D', fmt: pctFmt },
        { key: 'momentum_percentile', label: 'Mom %ile', fmt: v => `${v?.toFixed(0)}%` },
        { key: 'volatility_30d', label: 'Vol 30D', fmt: pctFmt },
        { key: 'vol_label', label: 'Vol Label', fmt: v => v },
        { key: 'relative_1m', label: 'Rel 1M', fmt: pctFmt },
        { key: 'relative_label', label: 'Rel Str', fmt: v => v },
        { key: 'price_vs_50dma', label: 'vs 50DMA', fmt: pctFmt },
        { key: 'trend_label', label: 'Trend', fmt: v => v },
        { key: 'signal', label: 'Signal', fmt: v => v },
        { key: 'sector', label: 'Sector', fmt: v => v },
    ];
    return (
        <div className="bg-zinc-900/60 border border-white/[0.06] rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
                <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest flex items-center gap-1.5"><Columns className="w-3 h-3" />Comparison</span>
                <button onClick={onClose} className="text-zinc-600 hover:text-zinc-300 transition-colors"><X className="w-3.5 h-3.5" /></button>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-left">
                    <thead><tr className="border-b border-white/5">
                        <th className="py-1.5 pr-4 text-[9px] text-zinc-600 font-semibold uppercase">Metric</th>
                        {stocks.map(s => <th key={s.symbol} className="py-1.5 px-3 text-[10px] font-bold text-zinc-300">{s.symbol.replace('.NS', '')}</th>)}
                    </tr></thead>
                    <tbody className="divide-y divide-white/[0.03]">
                        {metrics.map(m => (
                            <tr key={m.key} className="hover:bg-white/[0.015]">
                                <td className="py-1.5 pr-4 text-[10px] text-zinc-500 font-medium">{m.label}</td>
                                {stocks.map(s => <td key={s.symbol} className="py-1.5 px-3 text-[11px] font-mono text-zinc-300">{m.fmt(s[m.key])}</td>)}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

/* ── Main Screener ── */
const Screeners = ({ onSymbolClick }) => {
    const [raw, setRaw] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    // Filters
    const [filters, setFilters] = useState({
        momMin: '', momMax: '',
        vol: new Set(),       // Low, Normal, High
        trend: new Set(),     // Uptrend, Sideways, Downtrend
        rel: new Set(),       // Outperforming, Underperforming
        signal: new Set(),    // Strong, Watch, Weak
        sectors: new Set(),
    });

    // Sort
    const [sortKey, setSortKey] = useState('momentum_90d');
    const [sortDir, setSortDir] = useState('desc');

    // Comparison
    const [compareSet, setCompareSet] = useState(new Set());

    // Fetch
    const fetchData = useCallback(async () => {
        setLoading(true); setError(null);
        try {
            const res = await fetch(`${API_BASE}/screeners/multi`, { headers: AUTH_HEADERS });
            if (!res.ok) throw new Error(`Server error: ${res.status}`);
            const json = await res.json();
            if (json.error) throw new Error(json.error);
            setRaw(json);
        } catch (e) { setError(e.message); }
        finally { setLoading(false); }
    }, []);

    useEffect(() => { fetchData(); }, [fetchData]);

    // Toggle helper
    const toggleSet = (field, val) => {
        setFilters(f => {
            const s = new Set(f[field]);
            s.has(val) ? s.delete(val) : s.add(val);
            return { ...f, [field]: s };
        });
    };

    const clearFilters = () => setFilters({ momMin: '', momMax: '', vol: new Set(), trend: new Set(), rel: new Set(), signal: new Set(), sectors: new Set() });

    // All sectors (from data)
    const allSectors = useMemo(() => {
        if (!raw?.results) return [];
        return [...new Set(raw.results.map(r => r.sector).filter(s => s && s !== '—'))].sort();
    }, [raw]);

    // ── FILTER + SORT pipeline (useMemo, no API calls) ──
    const filtered = useMemo(() => {
        if (!raw?.results) return [];
        let data = raw.results;

        // Momentum range
        if (filters.momMin !== '') {
            const min = parseFloat(filters.momMin) / 100;
            data = data.filter(d => d.momentum_90d >= min);
        }
        if (filters.momMax !== '') {
            const max = parseFloat(filters.momMax) / 100;
            data = data.filter(d => d.momentum_90d <= max);
        }

        // Chip filters
        if (filters.vol.size) data = data.filter(d => filters.vol.has(d.vol_label));
        if (filters.trend.size) data = data.filter(d => filters.trend.has(d.trend_label));
        if (filters.rel.size) data = data.filter(d => filters.rel.has(d.relative_label));
        if (filters.signal.size) data = data.filter(d => filters.signal.has(d.signal));
        if (filters.sectors.size) data = data.filter(d => filters.sectors.has(d.sector));

        // Sort
        const dir = sortDir === 'asc' ? 1 : -1;
        data = [...data].sort((a, b) => {
            const va = a[sortKey], vb = b[sortKey];
            if (typeof va === 'string') return va.localeCompare(vb) * dir;
            return ((va ?? 0) - (vb ?? 0)) * dir;
        });

        return data;
    }, [raw, filters, sortKey, sortDir]);

    // Comparison stocks
    const compareStocks = useMemo(() => filtered.filter(d => compareSet.has(d.symbol)), [filtered, compareSet]);

    const handleSort = (key) => {
        if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
        else { setSortKey(key); setSortDir('desc'); }
    };

    const SortIcon = ({ col }) => {
        if (sortKey !== col) return <ArrowUpDown className="w-2.5 h-2.5 text-zinc-700" />;
        return sortDir === 'asc' ? <ArrowUp className="w-2.5 h-2.5 text-indigo-400" /> : <ArrowDown className="w-2.5 h-2.5 text-indigo-400" />;
    };

    const activeFilterCount = (filters.vol.size > 0 ? 1 : 0) + (filters.trend.size > 0 ? 1 : 0) + (filters.rel.size > 0 ? 1 : 0) + (filters.signal.size > 0 ? 1 : 0) + (filters.sectors.size > 0 ? 1 : 0) + (filters.momMin !== '' ? 1 : 0) + (filters.momMax !== '' ? 1 : 0);

    // ── Loading / Error ──
    if (loading) return (
        <div className="flex flex-col h-72 items-center justify-center gap-3">
            <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-indigo-500" />
            <p className="text-zinc-600 text-[10px] font-medium animate-pulse uppercase tracking-widest">Computing multi-factor screen…</p>
        </div>
    );
    if (error) return (
        <div className="bg-rose-500/10 border border-rose-500/20 p-4 rounded-xl text-rose-400 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" /><span>{error}</span>
            <button onClick={fetchData} className="ml-auto px-3 py-1 bg-rose-500/20 hover:bg-rose-500/30 rounded-lg text-rose-300 font-semibold"><RefreshCw className="w-3 h-3" /></button>
        </div>
    );

    const columns = [
        { key: '_check', label: '', w: 'w-8', sortable: false },
        { key: 'rank', label: '#', w: 'w-10', sortable: true },
        { key: 'symbol', label: 'Symbol', w: '', sortable: true },
        { key: 'momentum_30d', label: '30D', w: 'w-16', sortable: true },
        { key: 'momentum_90d', label: '90D', w: 'w-16', sortable: true },
        { key: 'momentum_percentile', label: '%ile', w: 'w-14', sortable: true },
        { key: 'volatility_30d', label: 'Vol', w: 'w-16', sortable: true },
        { key: 'relative_1m', label: 'Rel', w: 'w-16', sortable: true },
        { key: 'trend_label', label: 'Trend', w: 'w-20', sortable: true },
        { key: 'signal', label: 'Signal', w: 'w-20', sortable: true },
        { key: 'sector', label: 'Sector', w: 'w-24', sortable: true },
    ];

    return (
        <div className="max-w-[1400px] mx-auto space-y-4 animate-fade-in">
            {/* ── Header ── */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-xl font-bold text-white tracking-tight">Equity Screener</h2>
                    <p className="text-zinc-500 text-xs mt-0.5">{filtered.length} of {raw?.total || 0} stocks · as of {raw?.as_of || '...'}</p>
                </div>
                <div className="flex items-center gap-3">
                    {compareSet.size > 0 && <span className="text-[10px] font-bold text-indigo-400 bg-indigo-500/10 px-2 py-1 rounded-md">{compareSet.size} selected</span>}
                    {activeFilterCount > 0 && <button onClick={clearFilters} className="text-[10px] text-zinc-500 hover:text-zinc-300 font-medium flex items-center gap-1"><X className="w-3 h-3" />Clear filters</button>}
                    <button onClick={fetchData} className="p-1.5 rounded-lg hover:bg-white/5 text-zinc-500 hover:text-zinc-300 transition-colors"><RefreshCw className="w-3.5 h-3.5" /></button>
                </div>
            </div>

            {/* ── Main Layout ── */}
            <div className="flex gap-4">
                {/* ── Filter Panel (Left) ── */}
                <div className="w-48 shrink-0 space-y-4">
                    <div className="bg-zinc-900/50 border border-white/[0.04] rounded-xl p-3 space-y-4">
                        <div className="flex items-center gap-1.5 mb-1"><Filter className="w-3 h-3 text-zinc-600" /><span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Filters</span></div>

                        {/* Momentum Range */}
                        <div>
                            <span className="text-[9px] font-bold text-zinc-600 uppercase block mb-1.5">Momentum 90D (%)</span>
                            <div className="flex gap-1.5">
                                <input type="number" placeholder="Min" value={filters.momMin} onChange={e => setFilters(f => ({ ...f, momMin: e.target.value }))}
                                    className="w-full bg-black/30 border border-white/5 rounded px-1.5 py-1 text-[10px] text-zinc-300 focus:outline-none focus:border-indigo-500/50 placeholder:text-zinc-700" />
                                <input type="number" placeholder="Max" value={filters.momMax} onChange={e => setFilters(f => ({ ...f, momMax: e.target.value }))}
                                    className="w-full bg-black/30 border border-white/5 rounded px-1.5 py-1 text-[10px] text-zinc-300 focus:outline-none focus:border-indigo-500/50 placeholder:text-zinc-700" />
                            </div>
                        </div>

                        {/* Volatility */}
                        <div>
                            <span className="text-[9px] font-bold text-zinc-600 uppercase block mb-1.5">Volatility</span>
                            <div className="flex flex-wrap gap-1">{['Low', 'Normal', 'High'].map(v => <Chip key={v} label={v} active={filters.vol.has(v)} onClick={() => toggleSet('vol', v)} />)}</div>
                        </div>

                        {/* Trend */}
                        <div>
                            <span className="text-[9px] font-bold text-zinc-600 uppercase block mb-1.5">Trend</span>
                            <div className="flex flex-wrap gap-1">{['Uptrend', 'Sideways', 'Downtrend'].map(v => <Chip key={v} label={v} active={filters.trend.has(v)} onClick={() => toggleSet('trend', v)} />)}</div>
                        </div>

                        {/* Relative */}
                        <div>
                            <span className="text-[9px] font-bold text-zinc-600 uppercase block mb-1.5">Relative Strength</span>
                            <div className="flex flex-wrap gap-1">{['Outperforming', 'Underperforming'].map(v => <Chip key={v} label={v.slice(0, 6)} active={filters.rel.has(v)} onClick={() => toggleSet('rel', v)} />)}</div>
                        </div>

                        {/* Signal */}
                        <div>
                            <span className="text-[9px] font-bold text-zinc-600 uppercase block mb-1.5">Signal</span>
                            <div className="flex flex-wrap gap-1">{['Strong', 'Watch', 'Weak'].map(v => <Chip key={v} label={v} active={filters.signal.has(v)} onClick={() => toggleSet('signal', v)} />)}</div>
                        </div>

                        {/* Sector */}
                        <div>
                            <span className="text-[9px] font-bold text-zinc-600 uppercase block mb-1.5">Sector</span>
                            <select multiple value={[...filters.sectors]} onChange={e => { const opts = [...e.target.selectedOptions].map(o => o.value); setFilters(f => ({ ...f, sectors: new Set(opts) })); }}
                                className="w-full bg-black/30 border border-white/5 rounded px-1.5 py-1 text-[10px] text-zinc-400 focus:outline-none focus:border-indigo-500/50 h-24 [&>option]:py-0.5">
                                {allSectors.map(s => <option key={s} value={s}>{s}</option>)}
                            </select>
                            {filters.sectors.size > 0 && <button onClick={() => setFilters(f => ({ ...f, sectors: new Set() }))} className="text-[9px] text-zinc-600 hover:text-zinc-400 mt-1">Clear sectors</button>}
                        </div>
                    </div>

                    {/* Distribution */}
                    <div className="bg-zinc-900/50 border border-white/[0.04] rounded-xl p-3">
                        <div className="flex items-center gap-1.5 mb-2"><BarChart3 className="w-3 h-3 text-zinc-600" /><span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Distribution</span></div>
                        <MomentumHistogram data={filtered} selected={[...compareSet]} height={100} />
                    </div>
                </div>

                {/* ── Table (Right) ── */}
                <div className="flex-1 min-w-0">
                    <div className="bg-zinc-900/30 border border-white/[0.04] rounded-xl overflow-hidden">
                        <div className="overflow-x-auto max-h-[72vh] overflow-y-auto">
                            <table className="w-full text-left">
                                <thead className="sticky top-0 z-10 bg-zinc-900/95 backdrop-blur-sm">
                                    <tr className="border-b border-white/[0.06]">
                                        {columns.map(c => (
                                            <th key={c.key}
                                                className={`px-2 py-2.5 text-[9px] font-bold text-zinc-500 uppercase tracking-wider ${c.w} ${c.sortable ? 'cursor-pointer select-none hover:text-zinc-300' : ''}`}
                                                onClick={() => c.sortable && handleSort(c.key)}>
                                                <div className="flex items-center gap-1">{c.label}{c.sortable && <SortIcon col={c.key} />}</div>
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-white/[0.03]">
                                    {filtered.map(row => {
                                        const sc = SIG[row.signal] || SIG.Weak;
                                        const isCompare = compareSet.has(row.symbol);
                                        return (
                                            <tr key={row.symbol}
                                                className={`transition-colors hover:bg-white/[0.02] ${isCompare ? 'bg-indigo-500/5' : ''}`}>
                                                {/* Checkbox */}
                                                <td className="px-2 py-1.5">
                                                    <input type="checkbox" checked={isCompare}
                                                        onChange={() => setCompareSet(s => { const n = new Set(s); n.has(row.symbol) ? n.delete(row.symbol) : n.add(row.symbol); return n; })}
                                                        className="w-3 h-3 rounded border-zinc-700 bg-transparent accent-indigo-500 cursor-pointer" />
                                                </td>
                                                {/* Rank */}
                                                <td className="px-2 py-1.5 text-[10px] text-zinc-600 font-mono">{row.rank}</td>
                                                {/* Symbol */}
                                                <td className="px-2 py-1.5">
                                                    <button onClick={() => onSymbolClick?.(row.symbol)}
                                                        className="text-[11px] font-bold text-zinc-300 hover:text-indigo-400 transition-colors">
                                                        {row.symbol.replace('.NS', '')}
                                                    </button>
                                                </td>
                                                {/* Mom 30D */}
                                                <td className={`px-2 py-1.5 text-[10px] font-mono tabular-nums ${pctColor(row.momentum_30d)}`}>{pctFmt(row.momentum_30d)}</td>
                                                {/* Mom 90D */}
                                                <td className={`px-2 py-1.5 text-[10px] font-mono tabular-nums font-bold ${pctColor(row.momentum_90d)}`}>{pctFmt(row.momentum_90d)}</td>
                                                {/* Percentile */}
                                                <td className="px-2 py-1.5">
                                                    <div className="flex items-center gap-1.5">
                                                        <div className="w-8 h-1 bg-zinc-800 rounded-full overflow-hidden"><div className="h-full bg-indigo-500 rounded-full" style={{ width: `${row.momentum_percentile}%` }} /></div>
                                                        <span className="text-[9px] font-mono text-zinc-400">{row.momentum_percentile.toFixed(0)}</span>
                                                    </div>
                                                </td>
                                                {/* Volatility */}
                                                <td className={`px-2 py-1.5 text-[10px] font-medium ${VOL_C[row.vol_label] || 'text-zinc-400'}`}>{row.vol_label}</td>
                                                {/* Relative */}
                                                <td className={`px-2 py-1.5 text-[10px] font-mono tabular-nums ${pctColor(row.relative_1m)}`}>{pctFmt(row.relative_1m)}</td>
                                                {/* Trend */}
                                                <td className={`px-2 py-1.5 text-[10px] font-medium ${TREND_C[row.trend_label] || 'text-zinc-400'}`}>{row.trend_label}</td>
                                                {/* Signal */}
                                                <td className="px-2 py-1.5">
                                                    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded ${sc.bg}`}>
                                                        <span className={`w-1 h-1 rounded-full ${sc.dot}`} />
                                                        <span className={`text-[9px] font-bold uppercase ${sc.text}`}>{row.signal}</span>
                                                    </span>
                                                </td>
                                                {/* Sector */}
                                                <td className="px-2 py-1.5 text-[10px] text-zinc-500 truncate max-w-[80px]">{row.sector}</td>
                                            </tr>
                                        );
                                    })}
                                    {filtered.length === 0 && (
                                        <tr><td colSpan={columns.length} className="px-4 py-12 text-center text-zinc-600 text-xs">No stocks match current filters</td></tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    {/* Comparison */}
                    {compareStocks.length > 0 && (
                        <div className="mt-4">
                            <ComparisonPanel stocks={compareStocks} onClose={() => setCompareSet(new Set())} />
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default Screeners;
