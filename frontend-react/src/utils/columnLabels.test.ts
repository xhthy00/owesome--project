import { describe, expect, it } from "vitest";
import { labelColumn } from "./columnLabels";

describe("labelColumn", () => {
  it("把单科排名表头里的字段名译成中文", () => {
    expect(labelColumn("学校")).toBe("学校");
    expect(labelColumn("班级")).toBe("班级");
    expect(labelColumn("均分yy")).toBe("英语均分");
    expect(labelColumn("人数yy")).toBe("英语人数");
    expect(labelColumn("rk")).toBe("排名");
    expect(labelColumn("total_classes")).toBe("全市班级数");
  });

  it("英文列名与带科目后缀的均分仍可译", () => {
    expect(labelColumn("xx")).toBe("学校");
    expect(labelColumn("avg_yy")).toBe("英语均分");
    expect(labelColumn("n_sx")).toBe("数学人数");
    expect(labelColumn("city_rank")).toBe("全市排名");
  });
});
