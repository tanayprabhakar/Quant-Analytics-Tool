import React, { useState, useEffect, useCallback, memo } from 'react';
import StockChart from './components/StockChart';
import AnalystHeader from './components/AnalystHeader';
import AnalyticsGrid from './components/AnalyticsGrid';
import useDerivedSignals from './hooks/useDerivedSignals';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

function SecurityWorkbench({ symbol, onSymbolChange }) {
    const [overview, setOverview] = useState(null);
    const [performance, setPerformance] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [tickerList, setTickerList] = useState([]);
    const [showDropdown, setShowDropdown] = useState(false);

    // Derived signals — memoized, no API calls
    const signals = useDerivedSignals(overview, performance);

    const handleSearch = useCallback((e) => {
        if (e.key === 'Enter') {
            let s = searchTerm.toUpperCase();
            if (!s.endsWith('.NS') && !s.endsWith('.BO') && !s.includes('.')) s += '.NS';
            onSymbolChange(s);
            setShowDropdown(false);
            setSearchTerm('');
        }
    }, [searchTerm, onSymbolChange]);

    const handleTickerSelect = useCallback((ticker) => {
        onSymbolChange(ticker.value);
        setSearchTerm('');
        setShowDropdown(false);
    }, [onSymbolChange]);

    // Fetch Ticker List on Mount
    useEffect(() => {
        fetch(`${API_BASE}/market/tickers`)
            .then(res => res.json())
            .then(data => setTickerList(data))
            .catch(err => console.error('Failed to load ticker list', err));
    }, []);

    const filteredTickers = tickerList.filter(t => {
        const q = searchTerm.toLowerCase();
        return t.label.toLowerCase().includes(q)
            || (t.name && t.name.toLowerCase().includes(q))
            || (t.sector && t.sector.toLowerCase().includes(q));
    }).slice(0, 10);

    // Fetch Data — runs once per symbol change
    useEffect(() => {
        if (!symbol) return;

        const fetchData = async () => {
            setLoading(true);
            setError(null);
            try {
                const [overRes, perfRes] = await Promise.all([
                    fetch(`${API_BASE}/security/overview/${symbol}`),
                    fetch(`${API_BASE}/security/performance/${symbol}`),
                ]);

                if (!overRes.ok || !perfRes.ok) throw new Error('Failed to fetch security data');

                setOverview(await overRes.json());
                setPerformance(await perfRes.json());
            } catch (err) {
                console.error('SecurityWorkbench Error:', err);
                setError(err.message);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [symbol]);

    if (!symbol) {
        return (
            <div className="flex items-center justify-center h-full text-zinc-500 text-sm">
                Select a stock to view details
            </div>
        );
    }

    return (
        <div className="flex flex-col h-[calc(100vh-80px)] gap-1.5 animate-fade-in">
            {/* Row 1: Search + Analyst Header */}
            <div className="flex gap-1.5 flex-shrink-0">
                {/* Search */}
                <div className="relative w-72 flex-shrink-0">
                    <div className="relative">
                        <svg className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-zinc-600 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
                        <input
                            type="text"
                            placeholder="Search by name or symbol..."
                            className="w-full bg-zinc-900/40 border border-white/5 rounded-lg pl-8 pr-8 py-2 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-indigo-500/50 focus:bg-zinc-900/60 transition-all"
                            value={searchTerm}
                            onChange={(e) => { setSearchTerm(e.target.value); setShowDropdown(true); }}
                            onFocus={() => setShowDropdown(true)}
                            onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                    if (filteredTickers.length > 0) {
                                        handleTickerSelect(filteredTickers[0]);
                                    } else {
                                        let s = searchTerm.toUpperCase();
                                        if (!s.endsWith('.NS') && !s.endsWith('.BO') && !s.includes('.')) s += '.NS';
                                        onSymbolChange(s);
                                        setShowDropdown(false);
                                        setSearchTerm('');
                                    }
                                }
                            }}
                        />
                        {searchTerm && (
                            <button
                                className="absolute right-2 top-2 text-zinc-600 hover:text-zinc-300 transition-colors p-0.5"
                                onMouseDown={(e) => { e.preventDefault(); setSearchTerm(''); setShowDropdown(false); }}
                            >
                                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
                            </button>
                        )}
                    </div>

                    {showDropdown && searchTerm.length > 0 && (
                        <div className="absolute top-full left-0 right-0 mt-1.5 bg-zinc-900/95 backdrop-blur-xl border border-white/10 rounded-xl shadow-2xl shadow-black/40 z-50 overflow-hidden max-h-80 overflow-y-auto">
                            {filteredTickers.length > 0 ? (
                                <>
                                    <div className="px-3 py-1.5 text-[9px] font-bold text-zinc-600 uppercase tracking-widest border-b border-white/5">
                                        {filteredTickers.length} result{filteredTickers.length !== 1 ? 's' : ''}
                                    </div>
                                    {filteredTickers.map((ticker, i) => (
                                        <div
                                            key={ticker.value}
                                            className={`px-3 py-2 cursor-pointer flex items-center gap-3 transition-colors hover:bg-indigo-500/10 ${i === 0 ? 'bg-white/[0.02]' : ''} border-b border-white/[0.02] last:border-0`}
                                            onClick={() => handleTickerSelect(ticker)}
                                        >
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-[11px] font-bold text-zinc-200">{ticker.name}</span>
                                                </div>
                                                <div className="flex items-center gap-2 mt-0.5">
                                                    <span className="text-[10px] font-mono font-semibold text-indigo-400/80">{ticker.label}</span>
                                                    {ticker.sector && <span className="text-[8px] text-zinc-600 bg-white/[0.03] px-1.5 py-0.5 rounded">{ticker.sector}</span>}
                                                </div>
                                            </div>
                                            <span className="text-[8px] text-zinc-700 bg-zinc-800/80 px-1.5 py-0.5 rounded font-bold uppercase shrink-0">NSE</span>
                                        </div>
                                    ))}
                                </>
                            ) : (
                                <div className="px-3 py-4 text-center">
                                    <p className="text-zinc-500 text-xs">No matches found</p>
                                    <p className="text-zinc-700 text-[10px] mt-0.5">Press Enter to search "{searchTerm.toUpperCase()}"</p>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Analyst Header fills remaining space */}
                <div className="flex-1 min-w-0">
                    <AnalystHeader overview={overview} signals={signals} />
                </div>
            </div>

            {/* Row 2: Chart (fills available space) */}
            {loading ? (
                <div className="flex-1 flex items-center justify-center">
                    <div className="flex flex-col items-center gap-2">
                        <div className="animate-spin rounded-full h-6 w-6 border-t-2 border-blue-500" />
                        <span className="text-[10px] text-zinc-500 uppercase tracking-wider">Loading {symbol}...</span>
                    </div>
                </div>
            ) : error ? (
                <div className="flex-1 flex items-center justify-center">
                    <div className="text-red-400 text-sm border border-red-500/20 rounded-lg bg-red-500/5 px-6 py-4">
                        {error}
                    </div>
                </div>
            ) : (
                <>
                    <div className="flex-1 min-h-0">
                        <StockChart performanceData={performance} symbol={symbol} />
                    </div>

                    {/* Row 3: Analytics Grid */}
                    <div className="flex-shrink-0">
                        <AnalyticsGrid overview={overview} signals={signals} />
                    </div>
                </>
            )}
        </div>
    );
}

export default memo(SecurityWorkbench);
