import { describe, expect, it } from "vitest";
import {
  inferChartFields,
  isRankAxisColumn,
  preferQueryTableOverChart
} from "./G2Chart";

describe("preferQueryTableOverChart", () => {
  it("班级全市双口径排名：默认 Y 是名次，改走数据表", () => {
    const columns = ["口径", "全市排名", "班级总数", "六门均分", "班级参考人数"];
    const rows = [
      ["按选考方向(物理类)", 43, 307, 565.22, 46],
      ["不区分选考", 49, 389, 565.22, 46]
    ];
    const { yField } = inferChartFields(columns, rows);
    expect(yField).toBe("全市排名");
    expect(preferQueryTableOverChart(yField)).toBe(true);
  });

  it("达线率图仍走图表", () => {
    const columns = ["口径", "达线率", "达线人数", "参考人数"];
    const rows = [
      ["物理类", 82.5, 38, 46],
      ["历史类", 71.2, 21, 30]
    ];
    const { yField } = inferChartFields(columns, rows);
    expect(yField).toBe("达线率");
    expect(preferQueryTableOverChart(yField)).toBe(false);
  });

  it("学校均分对比即使带排名列也不改走表", () => {
    const columns = ["学校", "六门均分", "全市排名"];
    const rows = [
      ["扬州中学", 612.3, 2],
      ["新华中学", 598.1, 8]
    ];
    const { yField } = inferChartFields(columns, rows);
    expect(yField).toBe("六门均分");
    expect(preferQueryTableOverChart(yField)).toBe(false);
  });

  it("调用方指定非名次 Y 轴时仍出图", () => {
    expect(preferQueryTableOverChart("六门均分")).toBe(false);
    expect(isRankAxisColumn("六门均分")).toBe(false);
    expect(isRankAxisColumn("全市排名")).toBe(true);
    expect(isRankAxisColumn("city_rank")).toBe(true);
    expect(isRankAxisColumn("达线率")).toBe(false);
  });
});
