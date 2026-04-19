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

    const filteredTickers = tickerList.filter(t =>
        t.label.toLowerCase().includes(searchTerm.toLowerCase())
    ).slice(0, 8);

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
                <div className="relative w-64 flex-shrink-0">
                    <input
                        type="text"
                        placeholder="Search Ticker..."
                        className="w-full bg-zinc-900/40 border border-white/5 rounded-lg px-3 py-2 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-blue-500/50 transition-colors"
                        value={searchTerm}
                        onChange={(e) => { setSearchTerm(e.target.value); setShowDropdown(true); }}
                        onFocus={() => setShowDropdown(true)}
                        onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
                        onKeyDown={handleSearch}
                    />
                    <span className="absolute right-2.5 top-2.5 text-[9px] text-zinc-600 font-mono">↵</span>

                    {showDropdown && searchTerm && filteredTickers.length > 0 && (
                        <div className="absolute top-full left-0 right-0 mt-1 bg-zinc-900 border border-white/10 rounded-lg shadow-2xl z-50 overflow-hidden">
                            {filteredTickers.map((ticker) => (
                                <div
                                    key={ticker.value}
                                    className="px-3 py-1.5 text-sm text-zinc-300 hover:bg-white/5 cursor-pointer flex justify-between items-center"
                                    onClick={() => handleTickerSelect(ticker)}
                                >
                                    <span className="font-bold text-xs">{ticker.label}</span>
                                    <span className="text-[9px] text-zinc-600 bg-black/30 px-1 py-0.5 rounded">NSE</span>
                                </div>
                            ))}
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
