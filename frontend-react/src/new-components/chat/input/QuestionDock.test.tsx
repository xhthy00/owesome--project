import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import QuestionDock from "./QuestionDock";

const question = {
  request_id: "que_1",
  conv_id: "12",
  questions: [
    {
      header: "范围",
      question: "选择分析范围",
      options: [{ label: "班级" }],
      multiple: true,
      custom: true
    },
    {
      header: "口径",
      question: "选择比较口径",
      options: [{ label: "年级" }, { label: "全市" }],
      multiple: false,
      custom: false
    }
  ]
};

describe("QuestionDock", () => {
  it("全部问题回答后才允许确认，并让自定义答案与选项互斥", () => {
    const onConfirm = vi.fn();
    render(
      <QuestionDock question={question} onConfirm={onConfirm} onCancel={vi.fn()} />
    );

    const confirm = screen.getByRole("button", { name: "Confirm" });
    expect(confirm).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.change(screen.getByLabelText("范围自定义答案"), {
      target: { value: "自定义范围" }
    });
    expect(screen.getByRole("checkbox")).not.toBeChecked();

    fireEvent.click(screen.getByRole("radio", { name: /年级/ }));
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);

    expect(onConfirm).toHaveBeenCalledWith([["自定义范围"], ["年级"]]);
  });

  it("Cancel 和关闭按钮都拒绝问题", () => {
    const onCancel = vi.fn();
    render(
      <QuestionDock question={question} onConfirm={vi.fn()} onCancel={onCancel} />
    );

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "关闭确认问题" }));
    expect(onCancel).toHaveBeenCalledTimes(2);
  });
});
