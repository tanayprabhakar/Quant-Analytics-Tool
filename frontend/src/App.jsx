import React, { useState, useEffect, useCallback } from 'react';
import Plot from 'react-plotly.js';

// 1. API_BASE Resolution
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

function App() {
    // State for selected symbol (default RELIANCE.NS)
    const [selectedSymbol, setSelectedSymbol] = useState('RELIANCE.NS');

    // State for Chart Data
    const [chartData, setChartData] = useState(null);
    const [chartLoading, setChartLoading] = useState(false);
    const [chartError, setChartError] = useState(null);

    // State for Momentum Data
    const [momentumData, setMomentumData] = useState([]);
    const [momentumLoading, setMomentumLoading] = useState(false);
    const [momentumError, setMomentumError] = useState(null);
    const [lastUpdated, setLastUpdated] = useState(null);

    // State for Backtest
    const [backtestLoading, setBacktestLoading] = useState(false);
    const [backtestResult, setBacktestResult] = useState(null);
    const [showBacktestModal, setShowBacktestModal] = useState(false);

    // Helper to fetch chart data
    const fetchChartData = useCallback(async (symbol) => {
        setChartLoading(true);
        setChartError(null);
        try {
            const response = await fetch(`${API_BASE}/india/history/${symbol}?period=6mo`);
            if (!response.ok) throw new Error(response.status === 404 ? 'No data found' : 'Backend error');
            const data = await response.json();
            setChartData(data);
        } catch (err) {
            setChartError(err.message);
            setChartData(null);
        } finally {
            setChartLoading(false);
        }
    }, []);

    // Helper to fetch momentum data
    const fetchMomentumData = useCallback(async () => {
        setMomentumLoading(true);
        setMomentumError(null);
        try {
            const response = await fetch(`${API_BASE}/india/factors/momentum?lookback_days=90&top_n=10`);
            if (!response.ok) throw new Error('Failed to fetch momentum data');
            const data = await response.json();
            setMomentumData(data.results || []);
            setLastUpdated(new Date().toLocaleTimeString());
        } catch (err) {
            setMomentumError(err.message);
        } finally {
            setMomentumLoading(false);
        }
    }, []);

    // Helper to run backtest
    const runBacktest = async () => {
        setBacktestLoading(true);
        setBacktestResult(null);
        setShowBacktestModal(true);
        try {
            const response = await fetch(`${API_BASE}/india/backtest/momentum?lookback_days=90&top_n=10`);
            if (!response.ok) throw new Error('Backtest failed');
            const data = await response.json();
            setBacktestResult(data);
        } catch (err) {
            setBacktestResult({ error: err.message });
        } finally {
            setBacktestLoading(false);
        }
    };

    // Initial Fetch on Mount
    useEffect(() => {
        fetchChartData(selectedSymbol);
        fetchMomentumData();
    }, []);

    const handleSymbolClick = (symbol) => {
        if (symbol === selectedSymbol) return;
        setSelectedSymbol(symbol);
        fetchChartData(symbol);
    };

    // Prepare Plotly Data
    const plotData = chartData ? [
        {
            x: chartData.map(d => d.Date),
            close: chartData.map(d => d.Close),
            high: chartData.map(d => d.High),
            low: chartData.map(d => d.Low),
            open: chartData.map(d => d.Open),
            type: 'candlestick',
            name: 'OHLC',
            increasing: { line: { color: '#4ade80' } },
            decreasing: { line: { color: '#f87171' } }
        }
    ] : [];

    const layout = {
        title: { text: selectedSymbol, font: { color: '#e2e8f0' } },
        dragmode: 'zoom',
        showlegend: false,
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#94a3b8' },
        height: 500,
        margin: { l: 40, r: 40, t: 40, b: 40 },
        xaxis: { gridcolor: '#334155', rangeslider: { visible: false } },
        yaxis: { gridcolor: '#334155' }
    };

    // Backtest Chart Data
    const backtestPlotData = backtestResult?.equity_curve ? [{
        x: backtestResult.equity_curve.map(d => d.date),
        y: backtestResult.equity_curve.map(d => d.value),
        type: 'scatter',
        mode: 'lines',
        name: 'Equity',
        line: { color: '#60a5fa', width: 2 },
        fill: 'tozeroy',
        fillcolor: 'rgba(96, 165, 250, 0.1)'
    }] : [];

    const backtestLayout = {
        title: { text: 'Strategy Equity Curve', font: { color: '#e2e8f0' } },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#94a3b8' },
        xaxis: { gridcolor: '#334155' },
        yaxis: { gridcolor: '#334155' },
        margin: { l: 40, r: 20, t: 40, b: 40 },
    };

    return (
        <div className="min-h-screen font-sans text-slate-100 p-8">
            <header className="max-w-7xl mx-auto mb-8 flex justify-between items-center bg-white/5 backdrop-blur-md border border-white/10 p-6 rounded-2xl shadow-xl">
                <div>
                    <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-cyan-300">
                        College OpenBB India
                    </h1>
                    <p className="text-slate-400 text-sm mt-1">Quantitative Momentum Screener & Backtester</p>
                </div>
                <div className="flex gap-4">
                    <button
                        onClick={runBacktest}
                        className="px-4 py-2 bg-indigo-600/80 hover:bg-indigo-600 text-white rounded-lg shadow-lg backdrop-blur-sm transition-all border border-indigo-400/30 hover:border-indigo-400"
                    >
                        Run Backtest
                    </button>
                    <div className="flex flex-col items-end">
                        <span className="text-xs text-slate-500 uppercase tracking-wider">Data Status</span>
                        <span className="flex items-center gap-2 text-sm text-green-400">
                            <span className="relative flex h-2 w-2">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                            </span>
                            Live Connected
                        </span>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Left Column: Chart */}
                <div className="lg:col-span-2 bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-6 shadow-xl relative min-h-[500px]">
                    {chartLoading && (
                        <div className="absolute inset-0 flex items-center justify-center bg-black/20 backdrop-blur-sm rounded-2xl z-10">
                            <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-400"></div>
                        </div>
                    )}

                    {chartError ? (
                        <div className="flex flex-col items-center justify-center h-full text-red-400 gap-4">
                            <p>Error loading chart: {chartError}</p>
                            <button onClick={() => fetchChartData(selectedSymbol)} className="px-4 py-2 bg-white/10 rounded hover:bg-white/20">Retry</button>
                        </div>
                    ) : (
                        <div className="w-full h-full">
                            {/* Plotly container needs explicit height in flex layout usually */}
                            <Plot
                                data={plotData}
                                layout={layout}
                                useResizeHandler={true}
                                style={{ width: '100%', height: '100%' }}
                                config={{ displayModeBar: false }}
                            />
                        </div>
                    )}
                </div>

                {/* Right Column: Momentum Leaderboard */}
                <div className="bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-6 shadow-xl flex flex-col h-[600px]">
                    <div className="flex justify-between items-center mb-6">
                        <h2 className="text-xl font-semibold text-slate-200">Top Momentum</h2>
                        <button
                            onClick={fetchMomentumData}
                            disabled={momentumLoading}
                            className="p-2 hover:bg-white/10 rounded-full transition-colors disabled:opacity-50"
                            title="Refresh"
                        >
                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                            </svg>
                        </button>
                    </div>

                    {momentumError ? (
                        <div className="text-red-400 text-center p-4 bg-red-900/10 rounded-lg border border-red-500/20">
                            {momentumError}
                        </div>
                    ) : (
                        <div className="overflow-y-auto pr-2 space-y-3 custom-scrollbar flex-1">
                            <div className="grid grid-cols-4 text-xs text-slate-500 px-4 mb-2 font-medium">
                                <span className="col-span-2">Symbol</span>
                                <span className="text-right">Score</span>
                                <span className="text-right">Price</span>
                            </div>
                            {momentumData.map((item, idx) => (
                                <button
                                    key={item.symbol}
                                    onClick={() => handleSymbolClick(item.symbol)}
                                    className={`w-full group flex items-center p-3 rounded-xl border transition-all duration-200 
                                        ${selectedSymbol === item.symbol
                                            ? 'bg-blue-500/20 border-blue-500/50 shadow-[0_0_15px_rgba(59,130,246,0.2)]'
                                            : 'bg-white/5 border-white/5 hover:bg-white/10 hover:border-white/20'}`}
                                >
                                    <div className="flex items-center gap-3 col-span-2 w-1/2">
                                        <span className={`flex items-center justify-center w-6 h-6 rounded text-xs font-bold 
                                            ${idx < 3 ? 'bg-yellow-500/20 text-yellow-500' : 'bg-slate-700 text-slate-400'}`}>
                                            {idx + 1}
                                        </span>
                                        <span className="font-medium text-sm text-slate-200 group-hover:text-white truncate">
                                            {item.symbol.replace('.NS', '')}
                                        </span>
                                    </div>
                                    <div className="w-1/4 text-right text-sm font-mono text-green-400">
                                        +{(item.momentum * 100).toFixed(1)}%
                                    </div>
                                    <div className="w-1/4 text-right text-sm font-mono text-slate-400">
                                        {item.latest.toFixed(0)}
                                    </div>
                                </button>
                            ))}
                        </div>
                    )}
                    {lastUpdated && <div className="mt-4 text-center text-xs text-slate-600">Updated: {lastUpdated}</div>}
                </div>
            </main>

            {/* Backtest Modal */}
            {showBacktestModal && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-[#1e293b] border border-white/10 rounded-2xl w-full max-w-4xl max-h-[90vh] overflow-y-auto shadow-2xl flex flex-col">
                        <div className="p-6 border-b border-white/10 flex justify-between items-center bg-white/5">
                            <h2 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-purple-400">
                                Strategy Backtest Results
                            </h2>
                            <button onClick={() => setShowBacktestModal(false)} className="text-slate-400 hover:text-white">✕</button>
                        </div>

                        <div className="p-8 space-y-8">
                            {backtestLoading ? (
                                <div className="flex flex-col items-center py-20 gap-4">
                                    <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-indigo-500"></div>
                                    <p className="text-slate-400 animate-pulse">Simulating history...</p>
                                </div>
                            ) : backtestResult?.error ? (
                                <div className="p-6 bg-red-900/20 border border-red-500/30 rounded-xl text-red-200">
                                    Backtest Failed: {backtestResult.error}
                                </div>
                            ) : backtestResult ? (
                                <>
                                    {/* Metrics Grid */}
                                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                        {[
                                            { label: 'Total Return', value: (backtestResult.metrics.cumulative_return * 100).toFixed(1) + '%', color: backtestResult.metrics.cumulative_return >= 0 ? 'text-green-400' : 'text-red-400' },
                                            { label: 'Ann. Return', value: (backtestResult.metrics.annualized_return * 100).toFixed(1) + '%', color: 'text-blue-400' },
                                            { label: 'Sharpe Ratio', value: backtestResult.metrics.sharpe_ratio.toFixed(2), color: 'text-purple-400' },
                                            { label: 'Max Drawdown', value: (backtestResult.metrics.max_drawdown * 100).toFixed(1) + '%', color: 'text-red-400' },
                                        ].map((m) => (
                                            <div key={m.label} className="bg-white/5 border border-white/10 p-4 rounded-xl text-center">
                                                <div className="text-xs text-slate-500 uppercase mb-1">{m.label}</div>
                                                <div className={`text-2xl font-bold ${m.color}`}>{m.value}</div>
                                            </div>
                                        ))}
                                    </div>

                                    {/* Equity Curve */}
                                    <div className="bg-white/5 border border-white/10 rounded-2xl p-4 h-[400px]">
                                        <Plot
                                            data={backtestPlotData}
                                            layout={backtestLayout}
                                            useResizeHandler={true}
                                            style={{ width: '100%', height: '100%' }}
                                            config={{ displayModeBar: false }}
                                        />
                                    </div>
                                </>
                            ) : null}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default App;
