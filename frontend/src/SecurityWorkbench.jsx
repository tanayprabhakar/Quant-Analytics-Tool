import React, { useState, useEffect } from 'react';
import Plot from 'react-plotly.js';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

const MetricCard = ({ label, value, subtext, color = "text-white" }) => (
    <div className="bg-black/20 p-4 rounded-lg border border-white/5 hover:border-white/10 transition-colors">
        <div className="text-[10px] font-semibold text-zinc-500 uppercase tracking-widest mb-1">{label}</div>
        <div className={`text-xl font-bold tracking-tight ${color}`}>{value}</div>
        {subtext && <div className="text-xs text-zinc-600 mt-1">{subtext}</div>}
    </div>
);

const SectionHeader = ({ title }) => (
    <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-4 pl-1 border-l-2 border-zinc-700">{title}</h3>
);

function SecurityWorkbench({ symbol, onSymbolChange }) {
    const [overview, setOverview] = useState(null);
    const [performance, setPerformance] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [searchTerm, setSearchTerm] = useState("");
    const [tickerList, setTickerList] = useState([]);
    const [showDropdown, setShowDropdown] = useState(false);

    const handleSearch = (e) => {
        if (e.key === 'Enter') {
            let s = searchTerm.toUpperCase();
            if (!s.endsWith('.NS') && !s.endsWith('.BO') && !s.includes('.')) s += '.NS';
            onSymbolChange(s);
            setShowDropdown(false);
            setSearchTerm("");
        }
    };

    // Fetch Ticker List on Mount
    useEffect(() => {
        fetch(`${API_BASE}/market/tickers`)
            .then(res => res.json())
            .then(data => setTickerList(data))
            .catch(err => console.error("Failed to load ticker list", err));
    }, []);

    const filteredTickers = tickerList.filter(t =>
        t.label.toLowerCase().includes(searchTerm.toLowerCase())
    ).slice(0, 8); // Limit to 8 results

    useEffect(() => {
        console.log("SecurityWorkbench mounted for:", symbol);
        if (!symbol) return;

        const fetchData = async () => {
            setLoading(true);
            setError(null);
            try {
                const [overRes, perfRes] = await Promise.all([
                    fetch(`${API_BASE}/security/overview/${symbol}`),
                    fetch(`${API_BASE}/security/performance/${symbol}`)
                ]);

                if (!overRes.ok || !perfRes.ok) throw new Error("Failed to fetch security data");

                setOverview(await overRes.json());
                setPerformance(await perfRes.json());
            } catch (err) {
                console.error("SecurityWorkbench Error:", err);
                setError(err.message);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [symbol]);

    if (!symbol) return <div className="text-zinc-500 text-center mt-20">Select a stock to view details</div>;
    // Loading state needs to be below Header if we want Search always visible, 
    // BUT we want to replace the whole view on load?
    // Let's keep separate loading for content vs header. 
    // Actually, simple is fine: Just render Header always? No, data dependency.

    // Fallback if loading/error, but we ideally want SEARCH accessible even if error.
    // For now, let's inject a specialized "Search Header" at top of component that renders BEFORE loading checks.

    // Chart Data Prep
    const chartData = performance?.data || [];
    const dates = chartData.map(d => d.date);

    // Candlestick Trace
    const candlestick = {
        x: dates,
        open: chartData.map(d => d.open),
        high: chartData.map(d => d.high),
        low: chartData.map(d => d.low),
        close: chartData.map(d => d.close),
        type: 'candlestick',
        name: symbol,
        decreasing: { line: { color: '#ef4444' } }, // Red-500
        increasing: { line: { color: '#10b981' } }, // Emerald-500
    };

    // SMA Traces
    const sma50 = {
        x: dates,
        y: chartData.map(d => d.sma_50),
        type: 'scatter',
        mode: 'lines',
        name: '50 DMA',
        line: { color: '#3b82f6', width: 1.5 } // Blue-500
    };

    const sma200 = {
        x: dates,
        y: chartData.map(d => d.sma_200),
        type: 'scatter',
        mode: 'lines',
        name: '200 DMA',
        line: { color: '#f59e0b', width: 1.5 } // Amber-500
    };

    // Volume Trace
    const volume = {
        x: dates,
        y: chartData.map(d => d.volume),
        type: 'bar',
        name: 'Volume',
        marker: { color: '#71717a' }, // Zinc-500
        yaxis: 'y2',
        opacity: 0.3
    };

    // Relative Performance Trace
    const relativePerf = {
        x: dates,
        y: chartData.map(d => d.relative_perf),
        type: 'scatter',
        mode: 'lines',
        name: `Rel vs ^NSEI`,
        line: { color: '#8b5cf6', width: 2 }, // Violet-500
        fill: 'tozeroy',
        fillcolor: 'rgba(139, 92, 246, 0.1)'
    };

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Global Search Header */}
            <div className="flex justify-between items-center bg-zinc-900/30 backdrop-blur-xl border border-white/10 p-4 rounded-xl shadow-lg">
                <div className="flex items-center gap-4 w-full">
                    <div className="relative w-full max-w-sm">
                        <input
                            type="text"
                            placeholder="Search Ticker (e.g. TCS)"
                            className="w-full bg-black/20 border border-white/10 rounded-lg px-4 py-2 text-sm text-white focus:outline-none focus:border-blue-500 transition-colors"
                            value={searchTerm}
                            onChange={(e) => {
                                setSearchTerm(e.target.value);
                                setShowDropdown(true);
                            }}
                            onFocus={() => setShowDropdown(true)}
                            onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
                            onKeyDown={handleSearch}
                        />
                        <span className="absolute right-3 top-2.5 text-xs text-zinc-500">ENTER</span>

                        {/* Dropdown */}
                        {showDropdown && searchTerm && filteredTickers.length > 0 && (
                            <div className="absolute top-full left-0 right-0 mt-2 bg-zinc-900 border border-white/10 rounded-lg shadow-xl z-50 overflow-hidden">
                                {filteredTickers.map((ticker) => (
                                    <div
                                        key={ticker.value}
                                        className="px-4 py-2 text-sm text-zinc-300 hover:bg-white/5 cursor-pointer flex justify-between items-center"
                                        onClick={() => {
                                            onSymbolChange(ticker.value);
                                            setSearchTerm("");
                                            setShowDropdown(false);
                                        }}
                                    >
                                        <span className="font-bold">{ticker.label}</span>
                                        <span className="text-xs text-zinc-500 bg-black/30 px-1.5 py-0.5 rounded">NSE</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                    <div className="h-6 w-px bg-white/10 mx-2"></div>
                    <h2 className="text-xl font-bold text-white tracking-tight">{symbol.replace('.NS', '')}</h2>
                </div>
                {overview && (
                    <div className="text-right flex items-center gap-4">
                        <div className="text-right">
                            <div className="text-2xl font-mono font-bold text-white">
                                {(performance?.data && performance.data.length > 0) ? performance.data[performance.data.length - 1]?.close.toFixed(2) : "N/A"}
                            </div>
                            <div className={`text-sm font-bold ${overview.header.return_1d >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                {overview.header.return_1d > 0 ? '+' : ''}{overview.header.return_1d}%
                            </div>
                            <div className="text-xs text-zinc-500 uppercase tracking-wider">Last Close</div>
                        </div>
                        <span className="px-3 py-1 bg-white/10 text-xs font-semibold rounded text-zinc-300 hidden md:block border border-white/5">{overview.header.sector}</span>
                    </div>
                )}
            </div>

            {(loading) ? (
                <div className="flex justify-center h-64 items-center"><div className="animate-spin rounded-full h-8 w-8 border-t-2 border-white"></div></div>
            ) : (error) ? (
                <div className="text-red-400 text-center p-10 border border-red-500/20 rounded-xl bg-red-500/5">{error}</div>
            ) : (
                <>
                    {/* Main Content (Chart etc) */}
                    {/* Main Chart + Volume */}
                    <div className="bg-zinc-900/30 backdrop-blur-xl border border-white/10 p-4 rounded-xl shadow-xl h-[500px]">
                        <Plot
                            data={[candlestick, sma50, sma200, volume]}
                            layout={{
                                autosize: true,
                                margin: { l: 50, r: 40, t: 30, b: 40 },
                                showlegend: true,
                                legend: { x: 0, y: 1, orientation: 'h', font: { color: '#a1a1aa' } },
                                paper_bgcolor: 'rgba(0,0,0,0)',
                                plot_bgcolor: 'rgba(0,0,0,0)',
                                xaxis: {
                                    gridcolor: '#27272a',
                                    tickfont: { color: '#71717a' },
                                    rangeslider: { visible: false }
                                },
                                yaxis: {
                                    domain: [0.3, 1], // Price takes top 70%
                                    gridcolor: '#27272a',
                                    tickfont: { color: '#71717a' }
                                },
                                yaxis2: {
                                    domain: [0, 0.2], // Volume takes bottom 20%
                                    showgrid: false,
                                    tickfont: { color: '#71717a' }
                                }
                            }}
                            useResizeHandler={true}
                            style={{ width: '100%', height: '100%' }}
                            config={{ displayModeBar: false }}
                        />
                    </div>

                    {/* Relative Performance Chart */}
                    <div className="bg-zinc-900/30 backdrop-blur-xl border border-white/10 p-4 rounded-xl shadow-xl h-[250px]">
                        <Plot
                            data={[relativePerf]}
                            layout={{
                                autosize: true,
                                margin: { l: 50, r: 40, t: 30, b: 40 },
                                showlegend: true,
                                legend: { x: 0, y: 1, orientation: 'h', font: { color: '#a1a1aa' } },
                                paper_bgcolor: 'rgba(0,0,0,0)',
                                plot_bgcolor: 'rgba(0,0,0,0)',
                                xaxis: {
                                    gridcolor: '#27272a',
                                    tickfont: { color: '#71717a' },
                                    rangeslider: { visible: false }
                                },
                                yaxis: {
                                    gridcolor: '#27272a',
                                    tickfont: { color: '#71717a' },
                                    title: { text: 'Relative Performance (%)', font: { color: '#a1a1aa' } }
                                }
                            }}
                            useResizeHandler={true}
                            style={{ width: '100%', height: '100%' }}
                            config={{ displayModeBar: false }}
                        />
                    </div>

                    {/* Data Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">

                        {/* Fundamentals */}
                        <div className="bg-zinc-900/30 backdrop-blur-xl border border-white/10 p-6 rounded-xl shadow-lg">
                            <SectionHeader title="Fundamentals" />
                            <div className="space-y-3">
                                <div className="flex justify-between py-2 border-b border-white/5">
                                    <span className="text-zinc-400 text-sm">Market Cap</span>
                                    <span className="text-white font-mono">{(overview.fundamentals.market_cap / 10000000).toFixed(0)} Cr</span>
                                </div>
                                <div className="flex justify-between py-2 border-b border-white/5">
                                    <span className="text-zinc-400 text-sm">P/E Ratio</span>
                                    <span className="text-white font-mono">{overview.fundamentals.pe_ratio?.toFixed(2) || 'N/A'}</span>
                                </div>
                                <div className="flex justify-between py-2 border-b border-white/5">
                                    <span className="text-zinc-400 text-sm">EPS (TTM)</span>
                                    <span className="text-white font-mono">{overview.fundamentals.eps?.toFixed(2) || 'N/A'}</span>
                                </div>
                            </div>
                        </div>

                        {/* Risk Metrics */}
                        <div className="bg-zinc-900/30 backdrop-blur-xl border border-white/10 p-6 rounded-xl shadow-lg">
                            <SectionHeader title="Risk Profile" />
                            <div className="grid grid-cols-2 gap-4">
                                <MetricCard
                                    label="Beta (1Y)"
                                    value={overview.risk.beta}
                                    color={overview.risk.beta > 1.2 ? "text-orange-400" : "text-emerald-400"}
                                />
                                <MetricCard
                                    label="Max Drawdown"
                                    value={`${overview.risk.max_drawdown_1y}%`}
                                    color="text-red-400"
                                />
                                <div className="col-span-2">
                                    <MetricCard
                                        label="Annualized Volatility (30D)"
                                        value={`${overview.risk.volatility_30d}%`}
                                        subtext="Standard Deviation of Log Returns"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Factor Exposure */}
                        <div className="bg-zinc-900/30 backdrop-blur-xl border border-white/10 p-6 rounded-xl shadow-lg">
                            <SectionHeader title="Factor Momentum" />
                            <div className="flex flex-col items-center justify-center h-full pb-6">
                                <div className="relative h-24 w-24 mb-4 flex items-center justify-center">
                                    <svg className="h-full w-full -rotate-90 text-zinc-800" viewBox="0 0 36 36">
                                        <path className="stroke-current" strokeWidth="3" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                                    </svg>
                                    <svg className="absolute h-full w-full -rotate-90 text-blue-500 overflow-visible" viewBox="0 0 36 36">
                                        <path
                                            className="stroke-current transition-all duration-1000 ease-out"
                                            strokeDasharray={`${overview.factors.momentum_percentile}, 100`}
                                            strokeWidth="3"
                                            fill="none"
                                            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                                        />
                                    </svg>
                                    <div className="absolute flex flex-col items-center">
                                        <span className="text-2xl font-bold text-white">{overview.factors.momentum_percentile}</span>
                                        <span className="text-[9px] uppercase text-zinc-500">Percentile</span>
                                    </div>
                                </div>
                                <div className="grid grid-cols-2 gap-x-8 gap-y-4 w-full px-4">
                                    <div className="text-center">
                                        <div className="text-zinc-400 text-[10px] uppercase tracking-wider mb-1">Momentum (30D)</div>
                                        <div className={`text-lg font-mono font-bold ${overview.factors.momentum_30d > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                            {overview.factors.momentum_30d > 0 ? '+' : ''}{(overview.factors.momentum_30d * 100).toFixed(1)}%
                                        </div>
                                    </div>
                                    <div className="text-center">
                                        <div className="text-zinc-400 text-[10px] uppercase tracking-wider mb-1">Momentum (90D)</div>
                                        <div className={`text-lg font-mono font-bold ${overview.factors.momentum_90d > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                            {overview.factors.momentum_90d > 0 ? '+' : ''}{(overview.factors.momentum_90d * 100).toFixed(1)}%
                                        </div>
                                    </div>
                                    <div className="col-span-2 border-t border-white/10 pt-3 mt-1 flex justify-between items-center px-4">
                                        <span className="text-xs text-zinc-400 uppercase">Trend State</span>
                                        <span className={`text-sm font-bold uppercase ${overview.factors.trend === 'Rising' ? 'text-emerald-400' : overview.factors.trend === 'Falling' ? 'text-red-400' : 'text-zinc-400'}`}>
                                            {overview.factors.trend}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        </div>

                    </div>

                    {/* Relative Performance Chart */}
                    <div className="bg-zinc-900/30 backdrop-blur-xl border border-white/10 p-4 rounded-xl shadow-lg h-[300px]">
                        <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-4 pl-1 border-l-2 border-purple-500">Relative Performance vs NIFTY 50 (Normalized)</h3>
                        <Plot
                            data={[relativePerf]}
                            layout={{
                                autosize: true,
                                margin: { l: 40, r: 20, t: 10, b: 40 },
                                showlegend: false,
                                paper_bgcolor: 'rgba(0,0,0,0)',
                                plot_bgcolor: 'rgba(0,0,0,0)',
                                xaxis: {
                                    gridcolor: '#27272a',
                                    tickfont: { color: '#71717a' }
                                },
                                yaxis: {
                                    gridcolor: '#27272a',
                                    tickfont: { color: '#71717a' },
                                    title: 'Relative Strength'
                                }
                            }}
                            useResizeHandler={true}
                            style={{ width: '100%', height: '100%' }}
                            config={{ displayModeBar: false }}
                        />
                    </div>

                </>
            )}
        </div>
    );
}

export default SecurityWorkbench;
