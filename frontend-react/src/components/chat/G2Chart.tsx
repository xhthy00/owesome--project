import { useEffect, useMemo, useRef } from "react";
import { Chart } from "@antv/g2";

export type G2ChartType = "column" | "bar" | "line" | "pie";

type Props = {
  type: G2ChartType;
  columns: string[];
  rows: unknown[][];
  showLabel?: boolean;
};

const toNumber = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
};

const isNumericColumn = (col: string, data: Record<string, unknown>[]): boolean => {
  if (!data.length) return false;
  for (const row of data) {
    const v = row[col];
    if (v === null || v === undefined || v === "") continue;
    const n = Number(String(v).replace("%", ""));
    if (Number.isNaN(n)) return false;
  }
  return true;
};

export default function G2Chart({ type, columns, rows, showLabel = false }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<Chart | null>(null);

  const data = useMemo(() => {
    if (!columns.length || !rows.length) return [];
    return rows.map((row) =>
      Object.fromEntries(columns.map((col, idx) => [col, row[idx]]))
    ) as Record<string, unknown>[];
  }, [columns, rows]);
  const inferred = useMemo(() => {
    if (!columns.length || !data.length) {
      return { xField: "", yField: "", chartData: [] as Record<string, unknown>[] };
    }
    const numericCols = columns.filter((col) => isNumericColumn(col, data));
    const categoricalCols = columns.filter((col) => !isNumericColumn(col, data));
    const hasOnlyNumericCols = categoricalCols.length === 0 && numericCols.length > 0;
    if (hasOnlyNumericCols && data.length === 1) {
      const metricCol = "指标";
      const valueCol = "数值";
      const chartData: Record<string, unknown>[] = numericCols.map((col) => ({
        [metricCol]: col,
        [valueCol]: data[0][col]
      }));
      return { xField: metricCol, yField: valueCol, chartData };
    }
    const xField = categoricalCols[0] ?? columns[0];
    const yCandidates = (numericCols.length ? numericCols : columns).filter((col) => col !== xField);
    const yField = yCandidates[0] ?? columns[1] ?? columns[0];
    return { xField, yField, chartData: data };
  }, [columns, data]);

  useEffect(() => {
    if (!containerRef.current) return;
    if (!inferred.chartData.length) return;
    const { xField, yField, chartData } = inferred;

    const chart = new Chart({
      container: containerRef.current,
      autoFit: true,
      height: 320
    });
    chartRef.current = chart;
    chart.theme({
      type: "classic",
      axis: { labelFill: "#9ca3af", titleFill: "#9ca3af" }
    });

    if (type === "pie") {
      const pieData = chartData
        .map((item) => ({
          category: String(item[xField] ?? ""),
          value: toNumber(item[yField]) ?? 0
        }))
        .filter((item) => item.category);
      chart.coordinate({ type: "theta" });
      chart
        .interval()
        .data(pieData)
        .transform({ type: "stackY" })
        .encode("y", "value")
        .encode("color", "category")
        .label({ text: "value", style: { fill: "#111827", fontSize: 11 } });
    } else {
      const mark =
        type === "line" ? chart.line() : chart.interval();
      mark
        .data(chartData)
        .encode("x", xField)
        .encode("y", yField)
        .encode("color", xField);
      if (showLabel) {
        mark.label({ text: yField, style: { fill: "#111827", fontSize: 11 } });
      }
    }

    chart.render();

    return () => {
      chart.destroy();
      chartRef.current = null;
    };
  }, [inferred, type, showLabel]);

  useEffect(() => {
    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, []);

  return <div ref={containerRef} className="h-[320px] w-full" />;
}
