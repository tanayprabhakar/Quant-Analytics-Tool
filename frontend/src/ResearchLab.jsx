import React, { useState, useMemo } from 'react';
import { Activity, Play, Plus, X, RefreshCw, TrendingUp, Shield, DollarSign } from 'lucide-react';
import Plot from 'react-plotly.js';

const API = import.meta.env.VITE_API_BASE || 'http://localhost:8000';
const FACTORS = [
    { id: 'momentum', label: 'Momentum', icon: TrendingUp },
    { id: 'low-vol', label: 'Low Vol', icon: Shield },
    { id: 'value', label: 'Value', icon: DollarSign },
];
const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444'];
const DARK_LAYOUT = { autosize: true, paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', font: { color: '#a1a1aa', size: 10 }, margin: { t: 30, r: 20, l: 45, b: 35 }, xaxis: { gridcolor: 'rgba(255,255,255,0.04)' }, yaxis: { gridcolor: 'rgba(255,255,255,0.04)', tickformat: '.2f' }, legend: { orientation: 'h', y: 1.08, font: { size: 9 } } };
const pf = (v) => v != null ? `${(v * 100).toFixed(1)}%` : '—';

const ResearchLab = () => {
    const [strategies, setStrategies] = useState([{ factor: 'momentum', lookback_days: 90, top_n: 10 }]);
    const [dateRange, setDateRange] = useState({ start: '2024-01-01', end: '2025-04-01' });
    const [results, setResults] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    // Heatmap
    const [heatmapData, setHeatmapData] = useState(null);
    const [heatLoading, setHeatLoading] = useState(false);
    const [heatFactor, setHeatFactor] = useState('momentum');

    const addStrategy = () => { if (strategies.length < 4) setStrategies(s => [...s, { factor: 'momentum', lookback_days: 60, top_n: 10 }]); };
    const removeStrategy = (i) => setStrategies(s => s.filter((_, j) => j !== i));
    const updateStrategy = (i, field, val) => setStrategies(s => s.map((st, j) => j === i ? { ...st, [field]: val } : st));

    const runAll = async () => {
        setLoading(true); setError(null); setResults(null);
        try {
            const res = await fetch(`${API}/research/multi`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ strategies, ...dateRange, rebalance: 'monthly' }) });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed');
            setResults(data);
        } catch (e) { setError(e.message); }
        finally { setLoading(false); }
    };

    const runHeatmap = async () => {
        setHeatLoading(true); setHeatmapData(null);
        try {
            const res = await fetch(`${API}/research/heatmap`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ factor: heatFactor, lookbacks: [30, 60, 90, 120], top_ns: [5, 10, 15, 20], ...dateRange, rebalance: 'monthly' }) });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed');
            setHeatmapData(data);
        } catch (e) { setError(e.message); }
        finally { setHeatLoading(false); }
    };

    // Parse date strings DD-MM-YYYY to YYYY-MM-DD for Plotly
    const pDate = (d) => { const p = d.split('-'); return `${p[2]}-${p[1]}-${p[0]}`; };

    const strats = results?.strategies?.filter(s => !s.error) || [];

    // ── Interpretation ──
    const interpretation = useMemo(() => {
        if (!strats.length) return [];
        const lines = [];
        strats.forEach(s => {
            const sm = s.summary;
            const rm = s.regime_metrics || {};
            lines.push(`**${s.name}**: CAGR ${pf(sm.cagr)}, Sharpe ${sm.sharpe?.toFixed(2)}, MaxDD ${pf(sm.max_drawdown)}`);
            if (rm.bull?.days > 0 && rm.bear?.days > 0) {
                const bullS = rm.bull.sharpe, bearS = rm.bear.sharpe;
                if (bullS > 0.5 && bearS < -0.5) lines.push(`  → Strong in bull markets (Sharpe ${bullS.toFixed(2)}), breaks in bear (${bearS.toFixed(2)})`);
                else if (bullS < 0 && bearS < 0) lines.push(`  → Underperforms in both regimes — factor may be weak`);
                else lines.push(`  → Bull Sharpe ${bullS.toFixed(2)}, Bear Sharpe ${bearS.toFixed(2)}`);
            }
            if (s.turnover > 0.6) lines.push(`  → High turnover (${(s.turnover * 100).toFixed(0)}%) — transaction costs will erode returns`);
            if (s.recovery_days) lines.push(`  → Max drawdown recovery: ${s.recovery_days} days`);
        });
        if (strats.length > 1) {
            const best = strats.reduce((a, b) => a.summary.sharpe > b.summary.sharpe ? a : b);
            lines.push(`\n**Best risk-adjusted**: ${best.name} (Sharpe ${best.summary.sharpe?.toFixed(2)})`);
        }
        return lines;
    }, [strats]);

    return (
        <div className="max-w-[1400px] mx-auto space-y-4 animate-fade-in p-2">
            {/* Header */}
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-bold text-white flex items-center gap-2"><Activity className="text-blue-500 w-5 h-5" />Research Lab</h2>
                    <p className="text-zinc-500 text-xs">Multi-Strategy Factor Research & Robustness Testing</p>
                </div>
            </div>

            {/* Strategy Builder */}
            <div className="bg-zinc-900/50 border border-white/[0.06] rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Strategy Builder</span>
                    <div className="flex gap-2">
                        <button onClick={addStrategy} disabled={strategies.length >= 4} className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 disabled:text-zinc-700 flex items-center gap-1"><Plus className="w-3 h-3" />Add</button>
                    </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                    {strategies.map((s, i) => (
                        <div key={i} className="bg-black/20 border border-white/5 rounded-lg p-3 relative" style={{ borderLeftColor: COLORS[i], borderLeftWidth: 3 }}>
                            {strategies.length > 1 && <button onClick={() => removeStrategy(i)} className="absolute top-1.5 right-1.5 text-zinc-700 hover:text-zinc-400"><X className="w-3 h-3" /></button>}
                            <select value={s.factor} onChange={e => updateStrategy(i, 'factor', e.target.value)} className="w-full bg-black/30 border border-white/5 rounded px-2 py-1 text-[10px] text-zinc-300 mb-2 focus:outline-none">
                                {FACTORS.map(f => <option key={f.id} value={f.id}>{f.label}</option>)}
                            </select>
                            <div className="flex gap-2">
                                <div className="flex-1"><label className="text-[8px] text-zinc-600 uppercase block">Lookback</label>
                                    <input type="number" value={s.lookback_days} onChange={e => updateStrategy(i, 'lookback_days', +e.target.value)} className="w-full bg-black/30 border border-white/5 rounded px-2 py-1 text-[10px] text-zinc-300 focus:outline-none" /></div>
                                <div className="flex-1"><label className="text-[8px] text-zinc-600 uppercase block">Top N</label>
                                    <input type="number" value={s.top_n} onChange={e => updateStrategy(i, 'top_n', +e.target.value)} className="w-full bg-black/30 border border-white/5 rounded px-2 py-1 text-[10px] text-zinc-300 focus:outline-none" /></div>
                            </div>
                        </div>
                    ))}
                </div>
                <div className="flex items-center gap-3 mt-3">
                    <div className="flex gap-2">
                        <input type="date" value={dateRange.start} onChange={e => setDateRange(d => ({ ...d, start: e.target.value }))} className="bg-black/30 border border-white/5 rounded px-2 py-1 text-[10px] text-zinc-300 focus:outline-none" />
                        <input type="date" value={dateRange.end} onChange={e => setDateRange(d => ({ ...d, end: e.target.value }))} className="bg-black/30 border border-white/5 rounded px-2 py-1 text-[10px] text-zinc-300 focus:outline-none" />
                    </div>
                    <button onClick={runAll} disabled={loading} className={`px-5 py-2 rounded-lg text-xs font-bold flex items-center gap-2 transition-all ${loading ? 'bg-zinc-700 text-zinc-400' : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-lg shadow-blue-500/20'}`}>
                        {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" fill="currentColor" />}Run All
                    </button>
                </div>
            </div>

            {error && <div className="bg-rose-500/10 border border-rose-500/20 p-3 rounded-lg text-rose-400 text-xs">{error}</div>}

            {strats.length > 0 && (<>
                {/* Summary Metrics Table */}
                <div className="bg-zinc-900/30 border border-white/[0.06] rounded-xl overflow-hidden">
                    <table className="w-full text-left">
                        <thead><tr className="border-b border-white/5 text-[9px] text-zinc-500 uppercase">
                            <th className="px-3 py-2">Strategy</th><th className="px-3 py-2 text-right">CAGR</th><th className="px-3 py-2 text-right">Sharpe</th><th className="px-3 py-2 text-right">Volatility</th><th className="px-3 py-2 text-right">Max DD</th><th className="px-3 py-2 text-right">Turnover</th><th className="px-3 py-2 text-right">Recovery</th>
                        </tr></thead>
                        <tbody className="divide-y divide-white/[0.03]">
                            {strats.map((s, i) => (
                                <tr key={i} className="hover:bg-white/[0.02]">
                                    <td className="px-3 py-2 text-[11px] font-bold text-zinc-300"><span className="inline-block w-2 h-2 rounded-full mr-2" style={{ background: s.color }} />{s.name}</td>
                                    <td className={`px-3 py-2 text-[11px] font-mono text-right ${s.summary.cagr >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{pf(s.summary.cagr)}</td>
                                    <td className="px-3 py-2 text-[11px] font-mono text-right text-zinc-300">{s.summary.sharpe?.toFixed(2)}</td>
                                    <td className="px-3 py-2 text-[11px] font-mono text-right text-zinc-400">{pf(s.summary.volatility)}</td>
                                    <td className="px-3 py-2 text-[11px] font-mono text-right text-rose-400">{pf(s.summary.max_drawdown)}</td>
                                    <td className="px-3 py-2 text-[11px] font-mono text-right text-zinc-400">{(s.turnover * 100).toFixed(0)}%</td>
                                    <td className="px-3 py-2 text-[11px] font-mono text-right text-zinc-500">{s.recovery_days ? `${s.recovery_days}d` : '—'}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* Equity Curve */}
                <div className="bg-zinc-900/30 border border-white/[0.06] rounded-xl p-2">
                    <div style={{ width: '100%', height: 350 }}>
                    <Plot data={[
                        ...strats.map(s => ({ x: s.equity_curve.map(d => pDate(d.date)), y: s.equity_curve.map(d => d.portfolio), type: 'scatter', mode: 'lines', name: s.name, line: { color: s.color, width: 2 } })),
                        ...(strats[0]?.nifty_curve?.length ? [{ x: strats[0].nifty_curve.map(d => pDate(d.date)), y: strats[0].nifty_curve.map(d => d.value), type: 'scatter', mode: 'lines', name: 'NIFTY 50', line: { color: '#ffffff', width: 1.5, dash: 'dot' } }] : []),
                        { x: strats[0].equity_curve.map(d => pDate(d.date)), y: strats[0].equity_curve.map(d => d.benchmark), type: 'scatter', mode: 'lines', name: 'Equal Weight', line: { color: '#71717a', width: 1, dash: 'dash' } },
                    ]} layout={{ ...DARK_LAYOUT, height: 350, title: { text: 'Equity Curves', font: { color: '#e4e4e7', size: 12 } } }} useResizeHandler={true} style={{ width: '100%', height: '100%' }} config={{ displayModeBar: false }} />
                    </div>
                </div>

                {/* Row: Drawdown + Rolling Sharpe */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div className="bg-zinc-900/30 border border-white/[0.06] rounded-xl p-2">
                        <div style={{ width: '100%', height: 240 }}>
                        <Plot data={strats.map(s => ({ x: s.drawdown_curve.map(d => pDate(d.date)), y: s.drawdown_curve.map(d => d.dd), type: 'scatter', mode: 'lines', name: s.name, line: { color: s.color, width: 1.5 }, fill: 'tozeroy', fillcolor: s.color + '10' }))} layout={{ ...DARK_LAYOUT, height: 240, title: { text: 'Drawdown', font: { color: '#e4e4e7', size: 11 } }, yaxis: { ...DARK_LAYOUT.yaxis, tickformat: '.0%' } }} useResizeHandler={true} style={{ width: '100%', height: '100%' }} config={{ displayModeBar: false }} />
                        </div>
                    </div>
                    <div className="bg-zinc-900/30 border border-white/[0.06] rounded-xl p-2">
                        <div style={{ width: '100%', height: 240 }}>
                        <Plot data={strats.filter(s => s.rolling_sharpe?.length).map(s => ({ x: s.rolling_sharpe.map(d => pDate(d.date)), y: s.rolling_sharpe.map(d => d.sharpe), type: 'scatter', mode: 'lines', name: s.name, line: { color: s.color, width: 1.5 } }))} layout={{ ...DARK_LAYOUT, height: 240, title: { text: 'Rolling Sharpe (6M)', font: { color: '#e4e4e7', size: 11 } }, shapes: [{ type: 'line', x0: 0, x1: 1, xref: 'paper', y0: 0, y1: 0, line: { color: '#3f3f46', width: 1, dash: 'dash' } }] }} useResizeHandler={true} style={{ width: '100%', height: '100%' }} config={{ displayModeBar: false }} />
                        </div>
                    </div>
                </div>

                {/* Regime Analysis */}
                <div className="bg-zinc-900/30 border border-white/[0.06] rounded-xl overflow-hidden">
                    <div className="px-3 py-2 border-b border-white/5"><span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Regime Analysis</span></div>
                    <div className="grid grid-cols-3 divide-x divide-white/[0.03]">
                        {['bull', 'bear', 'sideways'].map(regime => (
                            <div key={regime} className="p-3">
                                <div className="text-[10px] font-bold uppercase mb-2 flex items-center gap-1.5" style={{ color: regime === 'bull' ? '#10b981' : regime === 'bear' ? '#ef4444' : '#f59e0b' }}>
                                    <span className="w-2 h-2 rounded-full inline-block" style={{ background: regime === 'bull' ? '#10b981' : regime === 'bear' ? '#ef4444' : '#f59e0b' }} />{regime}
                                </div>
                                {strats.map((s, i) => {
                                    const rm = s.regime_metrics?.[regime];
                                    if (!rm || rm.days === 0) return <div key={i} className="text-[9px] text-zinc-700 mb-1">{s.name}: No data</div>;
                                    return (
                                        <div key={i} className="flex items-center gap-2 mb-1.5">
                                            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: s.color }} />
                                            <span className="text-[10px] text-zinc-400 flex-1 truncate">{s.name}</span>
                                            <span className={`text-[10px] font-mono font-bold ${rm.sharpe >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{rm.sharpe.toFixed(2)}</span>
                                            <span className="text-[8px] text-zinc-600">{rm.days}d</span>
                                        </div>
                                    );
                                })}
                            </div>
                        ))}
                    </div>
                </div>

                {/* Interpretation */}
                {interpretation.length > 0 && (
                    <div className="bg-zinc-900/30 border border-white/[0.06] rounded-xl p-4">
                        <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">Interpretation</div>
                        <div className="space-y-1">
                            {interpretation.map((line, i) => (
                                <p key={i} className="text-[11px] text-zinc-400 leading-relaxed" dangerouslySetInnerHTML={{ __html: line.replace(/\*\*(.*?)\*\*/g, '<span class="text-zinc-200 font-bold">$1</span>').replace(/→/g, '<span class="text-indigo-400">→</span>') }} />
                            ))}
                        </div>
                    </div>
                )}
            </>)}

            {/* Heatmap Section */}
            <div className="bg-zinc-900/30 border border-white/[0.06] rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Parameter Heatmap</span>
                    <div className="flex items-center gap-2">
                        <select value={heatFactor} onChange={e => setHeatFactor(e.target.value)} className="bg-black/30 border border-white/5 rounded px-2 py-1 text-[10px] text-zinc-300 focus:outline-none">
                            {FACTORS.map(f => <option key={f.id} value={f.id}>{f.label}</option>)}
                        </select>
                        <button onClick={runHeatmap} disabled={heatLoading} className={`px-3 py-1 rounded-lg text-[10px] font-bold ${heatLoading ? 'bg-zinc-700 text-zinc-500' : 'bg-indigo-600 hover:bg-indigo-500 text-white'}`}>
                            {heatLoading ? 'Running...' : 'Generate'}
                        </button>
                    </div>
                </div>
                {heatmapData && (() => {
                    const lbs = heatmapData.lookbacks;
                    const tns = heatmapData.top_ns;
                    const z = lbs.map(lb => tns.map(tn => { const r = heatmapData.rows.find(x => x.lookback === lb && x.top_n === tn); return r ? r.sharpe : 0; }));
                    return <div style={{ width: '100%', height: 280 }}><Plot data={[{ z, x: tns.map(t => `Top ${t}`), y: lbs.map(l => `${l}D`), type: 'heatmap', colorscale: [[0, '#450a0a'], [0.5, '#1c1917'], [1, '#052e16']], text: z.map(row => row.map(v => v.toFixed(2))), texttemplate: '%{text}', textfont: { color: '#e4e4e7', size: 12 }, hoverinfo: 'z' }]} layout={{ ...DARK_LAYOUT, height: 280, title: { text: `Sharpe Ratio: ${heatFactor}`, font: { color: '#e4e4e7', size: 11 } }, xaxis: { ...DARK_LAYOUT.xaxis, title: 'Top N' }, yaxis: { ...DARK_LAYOUT.yaxis, title: 'Lookback', tickformat: '' } }} useResizeHandler={true} style={{ width: '100%', height: '100%' }} config={{ displayModeBar: false }} /></div>;
                })()}
                {!heatmapData && !heatLoading && <p className="text-zinc-700 text-[10px] text-center py-6">Click Generate to run parameter sweep</p>}
            </div>
        </div>
    );
};

export default ResearchLab;
