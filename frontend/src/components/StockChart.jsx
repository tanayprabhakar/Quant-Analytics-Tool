import React, { useRef, useEffect, useState, useMemo, useCallback, memo } from 'react';
import useStockChart from '../hooks/useStockChart';

const TIMEFRAMES = [
    { label: '1M', days: 30 },
    { label: '3M', days: 90 },
    { label: '6M', days: 180 },
    { label: '1Y', days: 365 },
    { label: 'MAX', days: null },
];

const OVERLAYS = [
    { key: 'sma50', label: '50 DMA', defaultOn: true },
    { key: 'sma200', label: '200 DMA', defaultOn: true },
    { key: 'volume', label: 'Volume', defaultOn: true },
    { key: 'relative', label: 'Rel vs NIFTY', defaultOn: false },
    { key: 'drawdown', label: 'Drawdown', defaultOn: false },
];

function StockChart({ performanceData, symbol }) {
    const containerRef = useRef(null);
    const {
        setCandlestickData,
        setVolumeData,
        setLineData,
        toggleSeries,
        setTimeRange,
        fitContent,
        subscribeCrosshairMove,
        seriesMapRef,
    } = useStockChart(containerRef);

    const [activeTimeframe, setActiveTimeframe] = useState('1Y');
    const [overlays, setOverlays] = useState(() => {
        const m = {};
        OVERLAYS.forEach(o => m[o.key] = o.defaultOn);
        return m;
    });
    const [tooltip, setTooltip] = useState(null);

    // Prepare chart data — memoized
    const chartDatasets = useMemo(() => {
        const raw = performanceData?.data || [];
        if (!raw.length) return null;

        const candles = [];
        const volumes = [];
        const sma50 = [];
        const sma200 = [];
        const relPerf = [];
        const drawdownData = [];

        let rollingMax = -Infinity;

        for (let i = 0; i < raw.length; i++) {
            const d = raw[i];
            const time = d.date; // YYYY-MM-DD string

            candles.push({
                time,
                open: d.open,
                high: d.high,
                low: d.low,
                close: d.close,
            });

            // Volume bars colored by direction
            const isUp = d.close >= d.open;
            volumes.push({
                time,
                value: d.volume || 0,
                color: isUp ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)',
            });

            if (d.sma_50 != null) sma50.push({ time, value: d.sma_50 });
            if (d.sma_200 != null) sma200.push({ time, value: d.sma_200 });

            // Relative performance (normalize to %)
            if (d.relative_perf != null) {
                relPerf.push({ time, value: (d.relative_perf - 1) * 100 });
            }

            // Drawdown
            if (d.close != null) {
                if (d.close > rollingMax) rollingMax = d.close;
                drawdownData.push({ time, value: rollingMax > 0 ? ((d.close / rollingMax) - 1) * 100 : 0 });
            }
        }

        return { candles, volumes, sma50, sma200, relPerf, drawdownData };
    }, [performanceData]);

    // Push data to chart once computed
    useEffect(() => {
        if (!chartDatasets) return;

        setCandlestickData(chartDatasets.candles);
        setVolumeData(chartDatasets.volumes);
        setLineData('sma50', chartDatasets.sma50, { color: '#3b82f6', lineWidth: 1.5 });
        setLineData('sma200', chartDatasets.sma200, { color: '#f59e0b', lineWidth: 1.5 });
        setLineData('relative', chartDatasets.relPerf, {
            color: '#8b5cf6',
            lineWidth: 2,
            visible: overlays.relative,
            priceScaleId: 'relative',
        });
        setLineData('drawdown', chartDatasets.drawdownData, {
            color: '#ef4444',
            lineWidth: 1.5,
            visible: overlays.drawdown,
            priceScaleId: 'drawdown',
        });

        // Apply initial visibility
        Object.entries(overlays).forEach(([key, vis]) => toggleSeries(key, vis));

        // Fit initially then apply default timeframe
        fitContent();
    }, [chartDatasets]); // Only when data changes

    // Crosshair tooltip handler
    useEffect(() => {
        subscribeCrosshairMove((param) => {
            if (!param.time || !param.seriesData) {
                setTooltip(null);
                return;
            }
            const candleSeries = seriesMapRef.current['candle'];
            if (!candleSeries) return;
            const data = param.seriesData.get(candleSeries);
            if (!data) { setTooltip(null); return; }

            const volSeries = seriesMapRef.current['volume'];
            const volData = volSeries ? param.seriesData.get(volSeries) : null;

            const pctChange = data.open > 0 ? ((data.close - data.open) / data.open * 100).toFixed(2) : '0.00';

            setTooltip({
                time: param.time,
                open: data.open?.toFixed(2),
                high: data.high?.toFixed(2),
                low: data.low?.toFixed(2),
                close: data.close?.toFixed(2),
                change: pctChange,
                volume: volData?.value ? (volData.value / 1e6).toFixed(1) + 'M' : '—',
            });
        });
    }, [subscribeCrosshairMove]);

    // Handle timeframe change
    const handleTimeframe = useCallback((tf) => {
        setActiveTimeframe(tf.label);
        if (!chartDatasets?.candles?.length) return;

        if (tf.days === null) {
            fitContent();
            return;
        }

        const allCandles = chartDatasets.candles;
        const last = allCandles[allCandles.length - 1];
        const cutoffDate = new Date(last.time);
        cutoffDate.setDate(cutoffDate.getDate() - tf.days);
        const cutoffStr = cutoffDate.toISOString().split('T')[0];

        setTimeRange(cutoffStr, last.time);
    }, [chartDatasets, fitContent, setTimeRange]);

    // Handle overlay toggle — no re-fetch, no chart recreation
    const handleOverlayToggle = useCallback((key) => {
        setOverlays(prev => {
            const next = { ...prev, [key]: !prev[key] };
            toggleSeries(key, next[key]);
            return next;
        });
    }, [toggleSeries]);

    return (
        <div className="bg-zinc-900/40 backdrop-blur-xl border border-white/5 rounded-lg overflow-hidden flex flex-col h-full">
            {/* Controls Row */}
            <div className="flex items-center justify-between px-3 py-1.5 border-b border-white/5">
                {/* Timeframe buttons */}
                <div className="flex gap-0.5">
                    {TIMEFRAMES.map(tf => (
                        <button
                            key={tf.label}
                            onClick={() => handleTimeframe(tf)}
                            className={`px-2.5 py-0.5 text-[10px] font-bold tracking-wider rounded transition-colors ${activeTimeframe === tf.label
                                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                                : 'text-zinc-500 hover:text-zinc-300 border border-transparent'
                                }`}
                        >
                            {tf.label}
                        </button>
                    ))}
                </div>

                {/* Overlay toggles */}
                <div className="flex gap-1">
                    {OVERLAYS.map(o => (
                        <button
                            key={o.key}
                            onClick={() => handleOverlayToggle(o.key)}
                            className={`px-2 py-0.5 text-[10px] font-medium rounded transition-all ${overlays[o.key]
                                ? 'bg-white/10 text-white border border-white/10'
                                : 'text-zinc-600 hover:text-zinc-400 border border-transparent'
                                }`}
                        >
                            {overlays[o.key] ? '✓ ' : ''}{o.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* Chart container */}
            <div className="relative flex-1 min-h-0">
                <div ref={containerRef} style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }} />

                {/* Floating tooltip */}
                {tooltip && (
                    <div className="absolute top-2 left-2 bg-black/80 backdrop-blur border border-white/10 rounded px-2.5 py-1.5 pointer-events-none z-10">
                        <div className="flex items-center gap-3 text-[11px]">
                            <span className="text-zinc-400 font-mono">{tooltip.time}</span>
                            <span className="text-white font-bold">₹{tooltip.close}</span>
                            <span className={parseFloat(tooltip.change) >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                                {parseFloat(tooltip.change) >= 0 ? '+' : ''}{tooltip.change}%
                            </span>
                            <span className="text-zinc-500">Vol: {tooltip.volume}</span>
                        </div>
                        <div className="flex gap-3 text-[10px] text-zinc-500 mt-0.5">
                            <span>O: {tooltip.open}</span>
                            <span>H: {tooltip.high}</span>
                            <span>L: {tooltip.low}</span>
                            <span>C: {tooltip.close}</span>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export default memo(StockChart);
