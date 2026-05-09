import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type LogicalRange,
  type UTCTimestamp,
} from "lightweight-charts";
import type { CandlesPayload, ChartMetric } from "../lib/api";
import { money, price } from "../lib/format";

type Props = {
  payload: CandlesPayload | null;
  metric: ChartMetric;
};

export function TradingChart({ payload, metric }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | ISeriesApi<"Line"> | null>(null);
  const metricRef = useRef<ChartMetric | null>(null);
  const fittedRef = useRef(false);
  const candles = (payload?.candles || [])
    .filter((candle) => Number.isFinite(Number(candle.time)) && Number.isFinite(Number(candle.close)) && Number(candle.close) > 0)
    .slice(-180);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || candles.length < 2) return;

    if (!chartRef.current) {
      chartRef.current = createChart(container, {
        autoSize: true,
        handleScroll: {
          mouseWheel: true,
          pressedMouseMove: true,
          horzTouchDrag: true,
          vertTouchDrag: true,
        },
        handleScale: {
          axisPressedMouseMove: true,
          mouseWheel: true,
          pinch: true,
        },
        layout: {
          background: { type: ColorType.Solid, color: "#0b0f16" },
          textColor: "#8b93a4",
          fontSize: 11,
          attributionLogo: false,
        },
        grid: {
          vertLines: { color: "#1d2430" },
          horzLines: { color: "#1d2430" },
        },
        rightPriceScale: {
          borderColor: "#222936",
          scaleMargins: { top: 0.12, bottom: 0.16 },
          autoScale: true,
        },
        timeScale: {
          borderColor: "#222936",
          timeVisible: true,
          secondsVisible: true,
          barSpacing: 8,
          minBarSpacing: 2,
          rightOffset: 8,
          lockVisibleTimeRangeOnResize: true,
          rightBarStaysOnScroll: false,
        },
        crosshair: {
          mode: 1,
        },
      });
    }

    const chart = chartRef.current;
    const metricChanged = metricRef.current !== metric;
    const visibleLogicalRange = !metricChanged && fittedRef.current ? chart.timeScale().getVisibleLogicalRange() : null;
    const visiblePriceRange = !metricChanged && fittedRef.current ? chart.priceScale("right").getVisibleRange() : null;
    if (metricChanged && seriesRef.current) {
      chart.removeSeries(seriesRef.current);
      seriesRef.current = null;
      fittedRef.current = false;
    }
    metricRef.current = metric;

    if (metric === "price") {
      if (!seriesRef.current) {
        seriesRef.current = chart.addSeries(CandlestickSeries, {
          upColor: "#5ee0a5",
          downColor: "#ff5f70",
          borderUpColor: "#5ee0a5",
          borderDownColor: "#ff5f70",
          wickUpColor: "#5ee0a5",
          wickDownColor: "#ff5f70",
        });
      }
      (seriesRef.current as ISeriesApi<"Candlestick">).setData(candles.map((candle) => ({
        time: Number(candle.time) as UTCTimestamp,
        open: Number(candle.open ?? candle.close),
        high: Number(candle.high ?? candle.close),
        low: Number(candle.low ?? candle.close),
        close: Number(candle.close),
      })));
    } else {
      if (!seriesRef.current) {
        seriesRef.current = chart.addSeries(LineSeries, {
          color: "#5f7cff",
          lineWidth: 2,
          priceFormat: { type: "volume" },
        });
      }
      (seriesRef.current as ISeriesApi<"Line">).setData(candles.map((candle) => ({
        time: Number(candle.time) as UTCTimestamp,
        value: Number(candle.close),
      })));
    }

    if (!fittedRef.current) {
      chart.timeScale().fitContent();
      chart.priceScale("right").setAutoScale(true);
      fittedRef.current = true;
    } else {
      restoreViewport(chart, visibleLogicalRange, visiblePriceRange);
    }
  }, [candles, metric]);

  useEffect(() => () => {
    chartRef.current?.remove();
    chartRef.current = null;
    seriesRef.current = null;
    metricRef.current = null;
    fittedRef.current = false;
  }, []);

  if (candles.length < 2) {
    return <div className="chart-empty">Need at least two local snapshots to draw chart.</div>;
  }

  const latest = candles[candles.length - 1]?.close;
  const first = candles[0]?.close;
  const change = first ? ((Number(latest) - Number(first)) / Number(first)) * 100 : null;
  const formatValue = metric === "liquidity" ? money : price;
  const fitLatest = () => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.timeScale().fitContent();
    chart.priceScale("right").setAutoScale(true);
    fittedRef.current = true;
  };

  return (
    <div className="chart-wrap">
      <div className="chart-head">
        <span>{metric === "liquidity" ? "Liquidity" : "Price"} chart</span>
        <strong>{formatValue(latest)}</strong>
        <small className={Number(change) >= 0 ? "good" : "bad"}>{Number.isFinite(Number(change)) ? `${Number(change).toFixed(2)}%` : "-"}</small>
        <small>{payload?.interval_seconds || 1}s candles</small>
        <button type="button" onClick={fitLatest}>Fit Latest</button>
      </div>
      <div className="chart" ref={containerRef} />
      <div className="chart-credit">Charting: TradingView lightweight-charts</div>
    </div>
  );
}

function restoreViewport(
  chart: IChartApi,
  logicalRange: LogicalRange | null,
  priceRange: { from: number; to: number } | null,
) {
  if (logicalRange && Number.isFinite(logicalRange.from) && Number.isFinite(logicalRange.to)) {
    chart.timeScale().setVisibleLogicalRange(logicalRange);
  }
  if (priceRange && Number.isFinite(priceRange.from) && Number.isFinite(priceRange.to)) {
    chart.priceScale("right").setVisibleRange(priceRange);
  }
}
