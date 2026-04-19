import { useRef, useEffect, useCallback } from 'react';
import {
    createChart,
    ColorType,
    CrosshairMode,
    CandlestickSeries,
    HistogramSeries,
    LineSeries,
} from 'lightweight-charts';

/**
 * Custom hook for managing TradingView Lightweight Chart lifecycle (v5 API).
 * Chart instance lives in a ref — never destroyed/recreated on toggle.
 */
export default function useStockChart(containerRef) {
    const chartRef = useRef(null);
    const seriesMapRef = useRef({});
    const resizeObserverRef = useRef(null);

    // Initialize chart once
    useEffect(() => {
        if (!containerRef.current) return;

        const chart = createChart(containerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: 'transparent' },
                textColor: '#a1a1aa',
                fontSize: 11,
            },
            grid: {
                vertLines: { color: 'rgba(255,255,255,0.04)' },
                horzLines: { color: 'rgba(255,255,255,0.04)' },
            },
            crosshair: {
                mode: CrosshairMode.Normal,
                vertLine: { color: 'rgba(255,255,255,0.15)', width: 1, style: 0, labelBackgroundColor: '#27272a' },
                horzLine: { color: 'rgba(255,255,255,0.15)', width: 1, style: 0, labelBackgroundColor: '#27272a' },
            },
            timeScale: {
                borderColor: 'rgba(255,255,255,0.08)',
                timeVisible: false,
                secondsVisible: false,
            },
            rightPriceScale: {
                borderColor: 'rgba(255,255,255,0.08)',
            },
            handleScroll: { vertTouchDrag: false },
            handleScale: { axisPressedMouseMove: true },
        });

        chartRef.current = chart;

        // Resize observer for responsive behavior
        const ro = new ResizeObserver((entries) => {
            if (entries.length === 0 || !containerRef.current) return;
            const { width, height } = entries[0].contentRect;
            chart.applyOptions({ width, height });
        });
        ro.observe(containerRef.current);
        resizeObserverRef.current = ro;

        return () => {
            ro.disconnect();
            chart.remove();
            chartRef.current = null;
            seriesMapRef.current = {};
        };
    }, []); // Intentionally empty — mount once

    // Add candlestick series (v5: chart.addSeries(CandlestickSeries, options))
    const setCandlestickData = useCallback((data) => {
        if (!chartRef.current) return;
        let series = seriesMapRef.current['candle'];
        if (!series) {
            series = chartRef.current.addSeries(CandlestickSeries, {
                upColor: '#10b981',
                downColor: '#ef4444',
                borderDownColor: '#ef4444',
                borderUpColor: '#10b981',
                wickDownColor: '#ef4444',
                wickUpColor: '#10b981',
            });
            seriesMapRef.current['candle'] = series;
        }
        series.setData(data);
    }, []);

    // Add volume histogram (v5: chart.addSeries(HistogramSeries))
    const setVolumeData = useCallback((data) => {
        if (!chartRef.current) return;
        let series = seriesMapRef.current['volume'];
        if (!series) {
            series = chartRef.current.addSeries(HistogramSeries, {
                priceFormat: { type: 'volume' },
                priceScaleId: 'volume',
            });
            series.priceScale().applyOptions({
                scaleMargins: { top: 0.85, bottom: 0 },
            });
            seriesMapRef.current['volume'] = series;
        }
        series.setData(data);
    }, []);

    // Add line overlay — SMA, relative, drawdown (v5: chart.addSeries(LineSeries))
    const setLineData = useCallback((key, data, options = {}) => {
        if (!chartRef.current) return;
        let series = seriesMapRef.current[key];
        if (!series) {
            series = chartRef.current.addSeries(LineSeries, {
                lineWidth: 1.5,
                crosshairMarkerVisible: false,
                priceLineVisible: false,
                lastValueVisible: false,
                ...options,
            });
            seriesMapRef.current[key] = series;
        }
        series.setData(data);
    }, []);

    // Toggle series visibility — no chart recreation
    const toggleSeries = useCallback((key, visible) => {
        const series = seriesMapRef.current[key];
        if (series) {
            series.applyOptions({ visible });
        }
    }, []);

    // Set visible time range
    const setTimeRange = useCallback((from, to) => {
        if (!chartRef.current) return;
        chartRef.current.timeScale().setVisibleRange({ from, to });
    }, []);

    // Fit content
    const fitContent = useCallback(() => {
        if (!chartRef.current) return;
        chartRef.current.timeScale().fitContent();
    }, []);

    // Subscribe to crosshair move
    const subscribeCrosshairMove = useCallback((handler) => {
        if (!chartRef.current) return;
        chartRef.current.subscribeCrosshairMove(handler);
    }, []);

    return {
        chartRef,
        seriesMapRef,
        setCandlestickData,
        setVolumeData,
        setLineData,
        toggleSeries,
        setTimeRange,
        fitContent,
        subscribeCrosshairMove,
    };
}
