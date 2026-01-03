
import React, { useState, useEffect } from 'react';
import {
    PieChart, Plus, Trash2, Play,
    TrendingUp, TrendingDown, Layers, Activity
} from 'lucide-react';
import Plot from 'react-plotly.js';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

const PortfolioAnalytics = () => {
    // State
    const [holdings, setHoldings] = useState([
        { symbol: 'RELIANCE.NS', weight: 0.5 },
        { symbol: 'TCS.NS', weight: 0.5 }
    ]);
    const [dates, setDates] = useState({ start: '2024-01-01', end: '2024-12-31' });
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    // Helpers
    const totalWeight = holdings.reduce((sum, h) => sum + h.weight, 0);
    const isValid = Math.abs(totalWeight - 1.0) < 0.01;

    const addHolding = () => {
        setHoldings([...holdings, { symbol: '', weight: 0.1 }]);
    };

    const removeHolding = (idx) => {
        setHoldings(holdings.filter((_, i) => i !== idx));
    };

    const updateHolding = (idx, field, value) => {
        const newHoldings = [...holdings];
        newHoldings[idx][field] = value;
        setHoldings(newHoldings);
    };

    const runAnalysis = async () => {
        if (!isValid) return;
        setLoading(true);
        setError(null);
        setResult(null);

        const payload = {
            symbols: holdings.map(h => h.symbol),
            weights: holdings.map(h => h.weight),
            start: dates.start,
            end: dates.end,
            benchmark: '^NSEI'
        };

        try {
            const res = await fetch(`${API_BASE}/portfolio/analyze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();

            if (!res.ok) throw new Error(data.detail || 'Analysis failed');

            setResult(data);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    // Visualization Data
    const getEquityData = () => {
        if (!result) return [];
        return [
            {
                x: result.equity_curve.map(d => d.date),
                y: result.equity_curve.map(d => d.benchmark),
                name: 'Benchmark (NIFTY)',
                type: 'scatter',
                mode: 'lines',
                line: { color: '#ffffff', dash: 'dot', width: 2 }
            },
            {
                x: result.equity_curve.map(d => d.date),
                y: result.equity_curve.map(d => d.portfolio),
                name: 'Portfolio',
                type: 'scatter',
                mode: 'lines',
                line: { color: '#3b82f6', width: 3 }
            }
        ];
    };

    const getHeatmapData = () => {
        if (!result) return [];
        const matrix = result.correlation_matrix;
        const keys = Object.keys(matrix[0]).filter(k => k !== 'symbol');
        const z = matrix.map(row => keys.map(k => row[k]));

        return [{
            z: z,
            x: keys,
            y: matrix.map(m => m.symbol),
            type: 'heatmap',
            colorscale: 'RdBu',
            zmin: -1,
            zmax: 1
        }];
    };

    return (
        <div className="max-w-7xl mx-auto space-y-6 animate-fade-in p-2">

            <div className="flex justify-between items-center mb-4">
                <div>
                    <h2 className="text-2xl font-bold text-white flex items-center gap-2">
                        <PieChart className="text-purple-500" />
                        Portfolio Analytics
                    </h2>
                    <p className="text-zinc-400 text-sm">Institutional-Grade Risk & Attribution</p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                {/* Left: Builder */}
                <div className="lg:col-span-1 space-y-6">
                    <div className="bg-zinc-900/50 border border-white/10 rounded-xl p-5 shadow-xl backdrop-blur-sm">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-sm font-semibold text-zinc-300">Composition</h3>
                            <button onClick={addHolding} className="p-1 hover:bg-white/10 rounded">
                                <Plus size={16} className="text-zinc-400" />
                            </button>
                        </div>

                        <div className="space-y-3 max-h-[300px] overflow-y-auto pr-1">
                            {holdings.map((h, i) => (
                                <div key={i} className="flex gap-2 items-center">
                                    <input
                                        className="bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-white flex-1"
                                        placeholder="Symbol (e.g. TCS.NS)"
                                        value={h.symbol}
                                        onChange={(e) => updateHolding(i, 'symbol', e.target.value)}
                                    />
                                    <input
                                        type="number" step="0.05"
                                        className="bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-white w-20 text-right"
                                        placeholder="Wgt"
                                        value={h.weight}
                                        onChange={(e) => updateHolding(i, 'weight', parseFloat(e.target.value))}
                                    />
                                    <button onClick={() => removeHolding(i)} className="text-zinc-600 hover:text-red-400">
                                        <Trash2 size={14} />
                                    </button>
                                </div>
                            ))}
                        </div>

                        <div className="mt-4 pt-4 border-t border-white/5 flex justify-between items-center">
                            <span className="text-xs text-zinc-500">Total Weight</span>
                            <span className={`font-mono font-bold ${isValid ? 'text-green-400' : 'text-red-400'}`}>
                                {(totalWeight * 100).toFixed(0)}%
                            </span>
                        </div>

                        <div className="grid grid-cols-2 gap-2 mt-4">
                            <input
                                type="date" value={dates.start}
                                onChange={(e) => setDates({ ...dates, start: e.target.value })}
                                className="bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-zinc-400"
                            />
                            <input
                                type="date" value={dates.end}
                                onChange={(e) => setDates({ ...dates, end: e.target.value })}
                                className="bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-zinc-400"
                            />
                        </div>

                        <button
                            onClick={runAnalysis}
                            disabled={!isValid || loading}
                            className={`w-full py-3 rounded-lg font-bold flex items-center justify-center gap-2 mt-4 transition-all ${loading || !isValid
                                    ? 'bg-zinc-800 text-zinc-500 cursor-not-allowed'
                                    : 'bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white shadow-lg shadow-purple-500/20'
                                }`}
                        >
                            {loading ? <Activity className="animate-spin" /> : <Play size={18} fill="currentColor" />}
                            Run Analysis
                        </button>

                        {error && (
                            <div className="mt-3 p-2 bg-red-500/10 border border-red-500/20 rounded text-xs text-red-400">
                                {error}
                            </div>
                        )}
                    </div>
                </div>

                {/* Right: Dashboard */}
                <div className="lg:col-span-2 space-y-6">
                    {result && (
                        <>
                            {/* Stats */}
                            <div className="grid grid-cols-4 gap-4">
                                {[
                                    { l: 'CAGR', v: (result.summary.cagr * 100).toFixed(2) + '%', c: 'text-green-400' },
                                    { l: 'Vol (Ann)', v: (result.summary.volatility * 100).toFixed(2) + '%', c: 'text-orange-400' },
                                    { l: 'Beta', v: result.summary.beta, c: 'text-blue-400' },
                                    { l: 'Max DD', v: (result.summary.max_drawdown * 100).toFixed(2) + '%', c: 'text-red-400' }
                                ].map((s, i) => (
                                    <div key={i} className="bg-zinc-900/30 border border-white/10 rounded-xl p-4 flex flex-col items-center">
                                        <div className="text-xs text-zinc-500 uppercase tracking-widest mb-1">{s.l}</div>
                                        <div className={`text-xl font-bold font-mono ${s.c}`}>{s.v}</div>
                                    </div>
                                ))}
                            </div>

                            {/* Chart */}
                            <div className="bg-zinc-900/50 border border-white/10 rounded-xl p-1 h-[300px]">
                                <Plot
                                    data={getEquityData()}
                                    layout={{
                                        autosize: true,
                                        paper_bgcolor: 'rgba(0,0,0,0)',
                                        plot_bgcolor: 'rgba(0,0,0,0)',
                                        font: { color: '#a1a1aa' },
                                        margin: { t: 20, r: 20, l: 40, b: 30 },
                                        xaxis: { gridcolor: 'rgba(255,255,255,0.05)' },
                                        yaxis: { gridcolor: 'rgba(255,255,255,0.05)' },
                                        legend: { orientation: 'h', y: 1.1 }
                                    }}
                                    style={{ width: '100%', height: '100%' }}
                                    config={{ displayModeBar: false }}
                                />
                            </div>

                            {/* Attribution & Correlation */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                {/* Attribution Table */}
                                <div className="bg-zinc-900/50 border border-white/10 rounded-xl p-4 overflow-hidden">
                                    <h4 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
                                        <Layers size={14} /> Attribution
                                    </h4>
                                    <div className="overflow-x-auto">
                                        <table className="w-full text-left border-collapse">
                                            <thead>
                                                <tr className="text-xs text-zinc-500 border-b border-white/5">
                                                    <th className="pb-2 font-medium">Symbol</th>
                                                    <th className="pb-2 font-medium text-right">Ret Contrib</th>
                                                    <th className="pb-2 font-medium text-right">Risk Contrib</th>
                                                </tr>
                                            </thead>
                                            <tbody className="text-sm">
                                                {result.attribution.map(a => (
                                                    <tr key={a.symbol} className="border-b border-white/5 last:border-0 hover:bg-white/5">
                                                        <td className="py-2 text-zinc-300 font-mono">{a.symbol}</td>
                                                        <td className={`py-2 text-right font-mono ${a.return_contribution >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                            {a.return_contribution}
                                                        </td>
                                                        <td className="py-2 text-right font-mono text-zinc-400">
                                                            {a.risk_contribution}
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>

                                {/* Correlation Heatmap */}
                                <div className="bg-zinc-900/50 border border-white/10 rounded-xl p-1 h-[250px]">
                                    <Plot
                                        data={getHeatmapData()}
                                        layout={{
                                            autosize: true,
                                            title: {
                                                text: 'Correlation Matrix',
                                                font: { size: 12, color: '#71717a' },
                                                x: 0.05,
                                                y: 0.95
                                            },
                                            paper_bgcolor: 'rgba(0,0,0,0)',
                                            plot_bgcolor: 'rgba(0,0,0,0)',
                                            font: { color: '#a1a1aa', size: 10 },
                                            margin: { t: 30, r: 10, l: 30, b: 30 },
                                        }}
                                        style={{ width: '100%', height: '100%' }}
                                        config={{ displayModeBar: false }}
                                    />
                                </div>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};

export default PortfolioAnalytics;
