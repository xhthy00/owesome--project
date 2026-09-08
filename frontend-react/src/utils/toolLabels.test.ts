import { describe, expect, it } from "vitest";
import { pickCustomerAnswer, stripRedundantQueryResultSection } from "./toolLabels";

describe("stripRedundantQueryResultSection", () => {
  it("结论里已有表时去掉文末查询结果附表", () => {
    const text = `均分 565.22。

| 排名口径 | 全市排名 |
| --- | --- |
| 按选考方向 | 第 43 名 |

### 查询结果

| 口径 | 全市排名 |
| --- | --- |
| 按选考方向 | 43 |
`;
    const out = stripRedundantQueryResultSection(text);
    expect(out).toContain("第 43 名");
    expect(out).not.toContain("查询结果");
  });

  it("只有查询结果表时保留", () => {
    const text = `### 查询结果

| 口径 | 全市排名 |
| --- | --- |
| 按选考方向 | 43 |
`;
    expect(stripRedundantQueryResultSection(text)).toContain("查询结果");
  });
});

describe("pickCustomerAnswer", () => {
  it("从 summary 去掉重复查询结果表", () => {
    const summary = `<think>ok</think>

扬州中学高三(10)班均分 565.22。

| 排名口径 | 全市排名 |
| --- | --- |
| 按选考方向 | 第 43 名 |

### 查询结果

| 口径 | 全市排名 |
| --- | --- |
| 按选考方向 | 43 |
`;
    const out = pickCustomerAnswer(summary, "");
    expect(out).toContain("第 43 名");
    expect(out).not.toContain("查询结果");
  });
});
