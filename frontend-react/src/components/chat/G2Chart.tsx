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

export default function G2Chart({ type, columns, rows, showLabel = false }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<Chart | null>(null);

  const data = useMemo(() => {
    if (!columns.length || !rows.length) return [];
    return rows.map((row) =>
      Object.fromEntries(columns.map((col, idx) => [col, row[idx]]))
    ) as Record<string, unknown>[];
  }, [columns, rows]);

  useEffect(() => {
    if (!containerRef.current) return;
    if (!data.length) return;
    const xField = columns[0];
    const yCandidates = columns.slice(1).filter((col) =>
      data.some((item) => toNumber(item[col]) !== null)
    );
    const yField = yCandidates[0] ?? columns[1] ?? columns[0];

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
      const pieData = data
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
        .label({ text: "value", style: { fill: "#e5e7eb", fontSize: 11 } });
    } else {
      const mark =
        type === "line" ? chart.line() : chart.interval();
      mark
        .data(data)
        .encode("x", xField)
        .encode("y", yField)
        .encode("color", xField);
      if (showLabel) {
        mark.label({ text: yField, style: { fill: "#e5e7eb", fontSize: 11 } });
      }
    }

    chart.render();

    return () => {
      chart.destroy();
      chartRef.current = null;
    };
  }, [columns, data, type]);

  useEffect(() => {
    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, []);

  return <div ref={containerRef} className="h-[320px] w-full" />;
}
