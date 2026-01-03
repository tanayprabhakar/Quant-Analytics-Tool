
import React, { useState, useEffect } from 'react';
import {
    Activity, Play, Settings, Calendar,
    TrendingUp, TrendingDown, DollarSign, Shield,
    BarChart2, RefreshCw
} from 'lucide-react';
import Plot from 'react-plotly.js';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

const ResearchLab = () => {
    // State
    const [params, setParams] = useState({
        factor: 'momentum',
        lookback_days: 90,
        top_n: 10,
        start: '2023-01-01',
        end: '2025-12-31',
        rebalance: 'monthly'
    });

    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    // Handlers
    const runBacktest = async () => {
        setLoading(true);
        setError(null);
        setResult(null);

        try {
            const res = await fetch(`${API_BASE}/research/backtest`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params)
            });

            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.detail || "Backtest failed");
            }

            setResult(data);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    // Chart Data Preparation
    const getChartData = () => {
        if (!result?.equity_curve) return [];

        const dates = result.equity_curve.map(d => d.date); // DD-MM-YYYY
        // Plotly might prefer YYYY-MM-DD, but usually parses local
        // Let's reformat if needed, but try direct first.

        return [
            {
                x: dates,
                y: result.equity_curve.map(d => d.benchmark),
                type: 'scatter',
                mode: 'lines',
                name: 'Benchmark (Equal Weight)',
                line: { color: '#ffffff', width: 2, dash: 'dot' }
            },
            {
                x: dates,
                y: result.equity_curve.map(d => d.portfolio),
                type: 'scatter',
                mode: 'lines',
                name: `Strategy (${params.factor.toUpperCase()})`,
                line: { color: '#3b82f6', width: 3 }
            }
        ];
    };

    return (
        <div className="max-w-7xl mx-auto space-y-6 animate-fade-in p-2">

            {/* Header */}
            <div className="flex justify-between items-center mb-4">
                <div>
                    <h2 className="text-2xl font-bold text-white flex items-center gap-2">
                        <Activity className="text-blue-500" />
                        Research Lab
                    </h2>
                    <p className="text-zinc-400 text-sm">Factor Research & Backtesting Environment</p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">

                {/* Left Panel: Configuration */}
                <div className="lg:col-span-1 space-y-6">
                    <div className="bg-zinc-900/50 border border-white/10 rounded-xl p-5 shadow-xl backdrop-blur-sm">
                        <h3 className="text-sm font-semibold text-zinc-300 mb-4 flex items-center gap-2">
                            <Settings size={16} /> Configuration
                        </h3>

                        <div className="space-y-4">
                            {/* Factor Select */}
                            <div>
                                <label className="text-xs text-zinc-500 uppercase font-bold mb-2 block">Factor Strategy</label>
                                <div className="grid grid-cols-1 gap-2">
                                    {[
                                        { id: 'momentum', label: 'Momentum', icon: TrendingUp },
                                        { id: 'low-vol', label: 'Low Volatility', icon: Shield },
                                        { id: 'value', label: 'Value (P/E)', icon: DollarSign },
                                    ].map(f => (
                                        <button
                                            key={f.id}
                                            onClick={() => setParams({ ...params, factor: f.id })}
                                            className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all border ${params.factor === f.id
                                                    ? 'bg-blue-600/20 border-blue-500/50 text-blue-100'
                                                    : 'bg-black/20 border-white/5 text-zinc-400 hover:bg-white/5'
                                                }`}
                                        >
                                            <f.icon size={16} />
                                            {f.label}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {/* Params */}
                            <div>
                                <label className="text-xs text-zinc-500 uppercase font-bold mb-2 block">
                                    Lookback (Days): <span className="text-white">{params.lookback_days}</span>
                                </label>
                                <input
                                    type="range" min="30" max="365" step="30"
                                    value={params.lookback_days}
                                    onChange={(e) => setParams({ ...params, lookback_days: Number(e.target.value) })}
                                    className="w-full accent-blue-500"
                                />
                            </div>

                            <div>
                                <label className="text-xs text-zinc-500 uppercase font-bold mb-2 block">
                                    Top N Stocks: <span className="text-white">{params.top_n}</span>
                                </label>
                                <input
                                    type="range" min="5" max="25" step="5"
                                    value={params.top_n}
                                    onChange={(e) => setParams({ ...params, top_n: Number(e.target.value) })}
                                    className="w-full accent-blue-500"
                                />
                            </div>

                            {/* Dates */}
                            <div className="grid grid-cols-2 gap-2">
                                <div>
                                    <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">Start</label>
                                    <input
                                        type="date"
                                        value={params.start}
                                        onChange={(e) => setParams({ ...params, start: e.target.value })}
                                        className="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-zinc-200"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">End</label>
                                    <input
                                        type="date"
                                        value={params.end}
                                        onChange={(e) => setParams({ ...params, end: e.target.value })}
                                        className="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-zinc-200"
                                    />
                                </div>
                            </div>

                            {/* Run Button */}
                            <button
                                onClick={runBacktest}
                                disabled={loading}
                                className={`w-full py-3 rounded-lg font-bold flex items-center justify-center gap-2 mt-4 transition-all ${loading
                                        ? 'bg-zinc-700 text-zinc-400 cursor-not-allowed'
                                        : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-lg shadow-blue-500/20'
                                    }`}
                            >
                                {loading ? <RefreshCw className="animate-spin" /> : <Play size={18} fill="currentColor" />}
                                Run Backtest
                            </button>
                        </div>
                    </div>

                    {/* Last Run Info */}
                    {result && (
                        <div className="text-xs text-zinc-500 text-center font-mono">
                            Run ID: {result.run_id?.slice(0, 8)}
                        </div>
                    )}
                </div>

                {/* Right Panel: Results */}
                <div className="lg:col-span-3 space-y-6">
                    {/* Metrics Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        {[
                            { label: 'CAGR', value: result ? (result.summary.cagr * 100).toFixed(2) + '%' : '-', color: 'text-green-400' },
                            { label: 'Sharpe Ratio', value: result ? result.summary.sharpe : '-', color: 'text-blue-400' },
                            { label: 'Volatility', value: result ? (result.summary.volatility * 100).toFixed(2) + '%' : '-', color: 'text-orange-400' },
                            { label: 'Max Drawdown', value: result ? (result.summary.max_drawdown * 100).toFixed(2) + '%' : '-', color: 'text-red-400' }
                        ].map((m, i) => (
                            <div key={i} className="bg-zinc-900/30 border border-white/10 rounded-xl p-4 flex flex-col items-center justify-center">
                                <div className="text-xs text-zinc-500 uppercase tracking-widest mb-1">{m.label}</div>
                                <div className={`text-xl font-bold font-mono ${m.color}`}>{m.value}</div>
                            </div>
                        ))}
                    </div>

                    {/* Chart Area */}
                    <div className="bg-zinc-900/50 border border-white/10 rounded-xl p-1 shadow-inner min-h-[400px] relative">
                        {error && (
                            <div className="absolute inset-0 flex items-center justify-center text-red-400 bg-black/50 rounded-xl z-10 backdrop-blur-sm p-4 text-center">
                                <div>
                                    <p className="font-bold mb-2">Backtest Error</p>
                                    <p className="text-sm font-mono bg-black/50 p-2 rounded">{error}</p>
                                </div>
                            </div>
                        )}

                        {!result && !loading && !error && (
                            <div className="absolute inset-0 flex flex-col items-center justify-center text-zinc-600">
                                <BarChart2 size={48} className="mb-4 opacity-50" />
                                <p>Configure parameters and run backtest to see results.</p>
                            </div>
                        )}

                        <div className="w-full h-[450px]">
                            {result && (
                                <Plot
                                    data={getChartData()}
                                    layout={{
                                        autosize: true,
                                        paper_bgcolor: 'rgba(0,0,0,0)',
                                        plot_bgcolor: 'rgba(0,0,0,0)',
                                        font: { color: '#a1a1aa' },
                                        margin: { t: 30, r: 20, l: 40, b: 40 },
                                        xaxis: {
                                            gridcolor: 'rgba(255,255,255,0.05)',
                                            zerolinecolor: 'rgba(255,255,255,0.05)'
                                        },
                                        yaxis: {
                                            gridcolor: 'rgba(255,255,255,0.05)',
                                            zerolinecolor: 'rgba(255,255,255,0.05)',
                                            tickformat: '.2f'
                                        },
                                        legend: { orientation: 'h', y: 1.05 }
                                    }}
                                    style={{ width: '100%', height: '100%' }}
                                    config={{ displayModeBar: false }}
                                />
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ResearchLab;
