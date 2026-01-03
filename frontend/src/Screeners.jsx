
import React, { useState, useEffect } from 'react';
import { RefreshCw, TrendingUp, Shield, DollarSign } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

const Screeners = ({ onSymbolClick }) => {
    const [activeScreener, setActiveScreener] = useState('momentum'); // momentum, low-vol, value
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [params, setParams] = useState({ top_n: 20, lookback_days: 90 });

    const fetchScreener = async () => {
        setLoading(true);
        setError(null);
        try {
            // Adjust params based on type if needed, but endpoint accepts generic
            const query = new URLSearchParams({
                top_n: params.top_n,
                lookback_days: params.lookback_days
            });

            const res = await fetch(`${API_BASE}/screeners/${activeScreener}?${query}`);
            if (!res.ok) throw new Error("Failed to fetch screener data");
            const json = await res.json();
            setData(json);
        } catch (err) {
            setError(err.message);
            setData(null);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchScreener();
    }, [activeScreener, params]);

    // Helpers for display
    const getMetricLabel = (type) => {
        switch (type) {
            case 'momentum': return 'Momentum Score';
            case 'low-vol': return 'Volatility (30D)';
            case 'value': return 'P/E Ratio';
            default: return 'Score';
        }
    };

    const formatMetric = (val, type) => {
        if (val === undefined || val === null) return 'N/A';
        switch (type) {
            case 'momentum': return (val * 100).toFixed(1) + '%';
            case 'low-vol': return (val * 100).toFixed(1) + '%';
            case 'value': return val.toFixed(2);
            default: return val;
        }
    };

    return (
        <div className="max-w-7xl mx-auto space-y-8 animate-fade-in">
            {/* Header / Selector */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                <div>
                    <h2 className="text-2xl font-bold text-white tracking-tight">Equity Screeners</h2>
                    <p className="text-zinc-400 text-sm">Quantitative filtering based on proven factors.</p>
                </div>

                <div className="flex bg-zinc-900/50 p-1 rounded-xl border border-white/10">
                    {[
                        { id: 'momentum', label: 'Momentum', icon: TrendingUp },
                        { id: 'low-vol', label: 'Low Volatility', icon: Shield },
                        { id: 'value', label: 'Value', icon: DollarSign },
                    ].map((s) => {
                        const Icon = s.icon;
                        const isActive = activeScreener === s.id;
                        return (
                            <button
                                key={s.id}
                                onClick={() => setActiveScreener(s.id)}
                                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${isActive
                                        ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20'
                                        : 'text-zinc-400 hover:text-white hover:bg-white/5'
                                    }`}
                            >
                                <Icon size={16} />
                                {s.label}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Filters Bar (Read-onlyish or simple) */}
            <div className="bg-zinc-900/30 border border-white/5 rounded-xl p-4 flex gap-6 items-center overflow-x-auto">
                <div className="flex items-center gap-3">
                    <span className="text-xs font-bold text-zinc-500 uppercase">Top N</span>
                    <select
                        value={params.top_n}
                        onChange={(e) => setParams(p => ({ ...p, top_n: Number(e.target.value) }))}
                        className="bg-black/20 border border-white/10 rounded px-2 py-1 text-sm text-zinc-200 focus:outline-none focus:border-blue-500"
                    >
                        <option value="10">10</option>
                        <option value="20">20</option>
                        <option value="50">50</option>
                    </select>
                </div>
                {activeScreener === 'momentum' && (
                    <div className="flex items-center gap-3">
                        <span className="text-xs font-bold text-zinc-500 uppercase">Lookback</span>
                        <select
                            value={params.lookback_days}
                            onChange={(e) => setParams(p => ({ ...p, lookback_days: Number(e.target.value) }))}
                            className="bg-black/20 border border-white/10 rounded px-2 py-1 text-sm text-zinc-200 focus:outline-none focus:border-blue-500"
                        >
                            <option value="30">30 Days</option>
                            <option value="90">90 Days</option>
                            <option value="180">180 Days</option>
                        </select>
                    </div>
                )}

                <div className="flex-1"></div>

                <div className="text-xs text-zinc-500">
                    As of: <span className="text-zinc-300 font-mono">{data?.as_of || '...'}</span>
                </div>
            </div>

            {/* Results Table */}
            <div className="bg-zinc-900/30 backdrop-blur-xl border border-white/10 rounded-xl overflow-hidden min-h-[400px]">
                {loading ? (
                    <div className="flex h-full min-h-[400px] items-center justify-center">
                        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
                    </div>
                ) : error ? (
                    <div className="flex h-full min-h-[400px] items-center justify-center text-red-400">
                        {error}
                    </div>
                ) : (
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="bg-white/5 border-b border-white/5 text-xs text-zinc-500 uppercase tracking-wider">
                                <th className="px-6 py-4 font-semibold w-20">Rank</th>
                                <th className="px-6 py-4 font-semibold">Symbol</th>
                                <th className="px-6 py-4 font-semibold text-right">{getMetricLabel(activeScreener)}</th>
                                <th className="px-6 py-4 font-semibold text-right">Universe</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                            {data?.results?.map((row) => (
                                <tr
                                    key={row.symbol}
                                    className="hover:bg-white/5 transition-colors cursor-pointer group"
                                    onClick={() => onSymbolClick && onSymbolClick(row.symbol)}
                                >
                                    <td className="px-6 py-4 text-zinc-500 font-mono">
                                        #{row.rank}
                                    </td>
                                    <td className="px-6 py-4">
                                        <div className="font-bold text-zinc-200 group-hover:text-blue-400 transition-colors">
                                            {row.symbol.replace('.NS', '')}
                                        </div>
                                        <div className="text-xs text-zinc-600">NSE</div>
                                    </td>
                                    <td className="px-6 py-4 text-right font-mono text-zinc-300">
                                        {formatMetric(row.score, activeScreener)}
                                    </td>
                                    <td className="px-6 py-4 text-right text-xs text-zinc-600">
                                        {data.universe}
                                    </td>
                                </tr>
                            ))}
                            {(!data?.results || data.results.length === 0) && (
                                <tr>
                                    <td colSpan="4" className="px-6 py-12 text-center text-zinc-500">
                                        No matches found for current criteria.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
};

export default Screeners;
