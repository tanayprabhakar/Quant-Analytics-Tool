import React, { useState, useEffect } from 'react';
import Plot from 'react-plotly.js';

// Reuse API_BASE from App.jsx logic (passed as prop or re-defined)
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

const GlassCard = ({ children, title, className = "" }) => (
    <div className={`bg-zinc-900/30 backdrop-blur-xl border border-white/10 rounded-xl p-6 shadow-2xl flex flex-col ${className}`}>
        {title && <h3 className="text-lg font-medium text-zinc-100 mb-5 pb-3 border-b border-white/5 tracking-tight">{title}</h3>}
        {children}
    </div>
);

const StatBox = ({ label, value, subValue, color = "text-zinc-100" }) => (
    <div className="bg-black/20 p-4 rounded-lg border border-white/5 hover:border-white/10 transition-colors">
        <div className="text-[10px] font-semibold text-zinc-500 uppercase tracking-widest mb-1.5">{label}</div>
        <div className={`text-2xl font-bold tracking-tight ${color}`}>{value}</div>
        {subValue && <div className="text-xs text-zinc-500 mt-1">{subValue}</div>}
    </div>
);

function MarketMonitor({ onSymbolClick }) {
    const [summary, setSummary] = useState(null);
    const [breadth, setBreadth] = useState(null);
    const [leaders, setLeaders] = useState(null);
    const [momentum, setMomentum] = useState(null);
    const [loading, setLoading] = useState(true);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [sumRes, breadthRes, leadRes, momRes] = await Promise.all([
                fetch(`${API_BASE}/market/summary`),
                fetch(`${API_BASE}/market/breadth`),
                fetch(`${API_BASE}/market/leaders`),
                // Momentum Snapshot: Reuse existing endpoint with 30D lookback
                fetch(`${API_BASE}/india/factors/momentum?lookback_days=30&top_n=5`)
            ]);

            setSummary(await sumRes.json());
            setBreadth(await breadthRes.json());
            setLeaders(await leadRes.json());
            setMomentum(await momRes.json());

        } catch (error) {
            console.error("Error fetching market data:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    if (loading) {
        return (
            <div className="flex h-96 items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-400"></div>
            </div>
        );
    }

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 animate-fade-in">
            {/* Panel A: Market Summary */}
            <GlassCard title={`Market Summary (${summary?.benchmark || "NIFTY"})`}>
                <div className="grid grid-cols-2 gap-4 mb-6">
                    <StatBox
                        label="1D Return"
                        value={summary?.returns["1D"] + "%"}
                        color={summary?.returns["1D"] >= 0 ? "text-green-400" : "text-red-400"}
                    />
                    <StatBox
                        label="YTD Return"
                        value={summary?.returns["YTD"] + "%"}
                        color={summary?.returns["YTD"] >= 0 ? "text-blue-400" : "text-orange-400"}
                    />
                </div>

                <h4 className="text-sm font-medium text-slate-400 mb-3 uppercase">Volatility (Annualized)</h4>
                <div className="space-y-4">
                    <div>
                        <div className="flex justify-between text-sm mb-1">
                            <span>30-Day Volatility</span>
                            <span className="text-slate-200">{summary?.volatility["30D"]}</span>
                        </div>
                        <div className="h-2 bg-slate-700/50 rounded-full overflow-hidden">
                            <div className="h-full bg-purple-500/80 rounded-full" style={{ width: `${Math.min(summary?.volatility["30D"] * 100, 100)}%` }}></div>
                        </div>
                    </div>
                    <div>
                        <div className="flex justify-between text-sm mb-1">
                            <span>90-Day Volatility</span>
                            <span className="text-slate-200">{summary?.volatility["90D"]}</span>
                        </div>
                        <div className="h-2 bg-slate-700/50 rounded-full overflow-hidden">
                            <div className="h-full bg-indigo-500/80 rounded-full" style={{ width: `${Math.min(summary?.volatility["90D"] * 100, 100)}%` }}></div>
                        </div>
                    </div>
                </div>
            </GlassCard>

            {/* Panel B: Market Breadth */}
            <GlassCard title="Market Breadth">
                <div className="flex items-center justify-center mb-8 mt-2">
                    <div className="text-center px-6 border-r border-white/10">
                        <div className="text-3xl font-bold text-green-400">{breadth?.advancers}</div>
                        <div className="text-xs text-slate-500 uppercase">Advancers</div>
                    </div>
                    <div className="text-center px-6">
                        <div className="text-3xl font-bold text-red-400">{breadth?.decliners}</div>
                        <div className="text-xs text-slate-500 uppercase">Decliners</div>
                    </div>
                </div>

                <div className="space-y-6">
                    <div className="bg-white/5 p-4 rounded-xl border border-white/5">
                        <div className="flex justify-between items-center mb-2">
                            <span className="text-sm text-slate-300">Stocks &gt; 50-Day MA</span>
                            <span className="font-bold text-blue-300">{breadth?.percent_above_50dma}%</span>
                        </div>
                        <div className="w-full bg-slate-700/50 rounded-full h-2.5">
                            <div className="bg-blue-500 h-2.5 rounded-full relative transition-all duration-1000" style={{ width: `${breadth?.percent_above_50dma}%` }}>
                            </div>
                        </div>
                    </div>

                    <div className="bg-white/5 p-4 rounded-xl border border-white/5">
                        <div className="flex justify-between items-center mb-2">
                            <span className="text-sm text-slate-300">Positive Momentum (30D)</span>
                            <span className="font-bold text-teal-300">{breadth?.percent_positive_30d_momentum}%</span>
                        </div>
                        <div className="w-full bg-slate-700/50 rounded-full h-2.5">
                            <div className="bg-teal-500 h-2.5 rounded-full relative transition-all duration-1000" style={{ width: `${breadth?.percent_positive_30d_momentum}%` }}>
                            </div>
                        </div>
                    </div>
                </div>
            </GlassCard>

            {/* Panel C: Leaders & Laggards */}
            <GlassCard title="Leaders & Laggards (1D)" className="md:col-span-2 lg:col-span-1">
                <div className="grid grid-cols-2 gap-4 h-full">
                    <div className="bg-green-900/10 rounded-xl p-3 border border-green-500/10">
                        <h4 className="text-xs font-bold text-green-400 uppercase mb-3">Top Gainers</h4>
                        <ul className="space-y-2">
                            {leaders?.gainers.map((stock) => (
                                <li key={stock.symbol} className="flex justify-between items-center text-sm">
                                    <span className="text-slate-300 truncate w-24">{stock.symbol.replace('.NS', '')}</span>
                                    <span className="font-mono text-green-400">+{stock.return_1d}%</span>
                                </li>
                            ))}
                        </ul>
                    </div>
                    <div className="bg-red-900/10 rounded-xl p-3 border border-red-500/10">
                        <h4 className="text-xs font-bold text-red-400 uppercase mb-3">Top Losers</h4>
                        <ul className="space-y-2">
                            {leaders?.losers.map((stock) => (
                                <li key={stock.symbol} className="flex justify-between items-center text-sm">
                                    <span className="text-slate-300 truncate w-24">{stock.symbol.replace('.NS', '')}</span>
                                    <span className="font-mono text-red-400">{stock.return_1d}%</span>
                                </li>
                            ))}
                        </ul>
                    </div>
                </div>
            </GlassCard>

            {/* Panel D: Momentum Snapshot */}
            <GlassCard title="Momentum Leaders (30D)" className="md:col-span-2 lg:col-span-1">
                <div className="overflow-x-auto">
                    <table className="w-full text-sm text-left">
                        <thead className="text-xs text-slate-500 uppercase bg-white/5">
                            <tr>
                                <th className="px-4 py-3 rounded-l-lg">Symbol</th>
                                <th className="px-4 py-3 text-right">Score</th>
                                <th className="px-4 py-3 text-right rounded-r-lg">Price</th>
                            </tr>
                        </thead>
                        <tbody>
                            {momentum?.results?.map((item, idx) => (
                                <tr key={item.symbol} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                                    <td className="px-4 py-3 font-medium text-slate-200">
                                        <div className="flex items-center gap-2">
                                            <span className="text-slate-500 text-xs">#{idx + 1}</span>
                                            <button
                                                onClick={() => onSymbolClick && onSymbolClick(item.symbol)}
                                                className="text-slate-200 hover:text-blue-400 transition-colors cursor-pointer"
                                            >
                                                {item.symbol.replace('.NS', '')}
                                            </button>
                                        </div>
                                    </td>
                                    <td className="px-4 py-3 text-right font-mono text-blue-300">
                                        {(item.momentum * 100).toFixed(1)}%
                                    </td>
                                    <td className="px-4 py-3 text-right font-mono text-slate-400">
                                        {item.latest.toFixed(0)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </GlassCard>
        </div>
    );
}

export default MarketMonitor;
