import React, { useState, useEffect, useCallback } from 'react';
import Plot from 'react-plotly.js';
import MarketMonitor from './MarketMonitor';
import SecurityWorkbench from './SecurityWorkbench';

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

    // Navigation State
    const [activeTab, setActiveTab] = useState('monitor'); // 'monitor' or 'inspector'

    return (
        <div className="min-h-screen font-sans text-zinc-100 p-6 md:p-12 selection:bg-white/20">
            <header className="max-w-7xl mx-auto mb-10 flex flex-col md:flex-row justify-between items-center gap-6">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight text-white">
                        College OpenBB India
                    </h1>
                    <p className="text-zinc-400 text-sm mt-1 font-medium">Quantitative Momentum Screener & Backtester</p>
                </div>

                {/* Navigation Tabs */}
                <div className="flex bg-zinc-900/50 backdrop-blur-md p-1.5 rounded-full border border-white/10 shadow-lg">
                    <button
                        onClick={() => setActiveTab('monitor')}
                        className={`px-5 py-2 rounded-full text-sm font-medium transition-all duration-300 ${activeTab === 'monitor' ? 'bg-white text-black shadow-sm' : 'text-zinc-400 hover:text-zinc-200 hover:bg-white/5'}`}
                    >
                        Market Monitor
                    </button>
                    <button
                        onClick={() => setActiveTab('inspector')}
                        className={`px-5 py-2 rounded-full text-sm font-medium transition-all duration-300 ${activeTab === 'inspector' ? 'bg-white text-black shadow-sm' : 'text-zinc-400 hover:text-zinc-200 hover:bg-white/5'}`}
                    >
                        Stock Inspector
                    </button>
                </div>

                <div className="flex items-center gap-6">
                    {activeTab === 'inspector' && <button
                        onClick={runBacktest}
                        className="px-4 py-2 bg-zinc-100 hover:bg-white text-black text-sm font-semibold rounded-lg shadow-lg transition-all border border-transparent hover:scale-105"
                    >
                        Run Backtest
                    </button>}
                    <div className="flex flex-col items-end">
                        <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold mb-1">Status</span>
                        <span className="flex items-center gap-2 text-xs font-medium text-emerald-400 bg-emerald-400/10 px-2 py-1 rounded-full border border-emerald-400/20">
                            <span className="relative flex h-1.5 w-1.5">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
                            </span>
                            Connected
                        </span>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto">
                {activeTab === 'monitor' ? (
                    <MarketMonitor onSymbolClick={(symbol) => {
                        setSelectedSymbol(symbol);
                        setActiveTab('inspector');
                    }} />
                ) : (
                    <SecurityWorkbench
                        symbol={selectedSymbol}
                        onSymbolChange={setSelectedSymbol}
                    />
                )}
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
