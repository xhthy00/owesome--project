import { CloseOutlined } from "@ant-design/icons";
import { Button, Checkbox, Input, Radio } from "antd";
import { useEffect, useMemo, useState } from "react";
import type { Question } from "@/api/adapter/chatAdapter";

type AnswerState = {
  selected: string[];
  custom: string;
};

type QuestionDockProps = {
  question: Question;
  submitting?: boolean;
  error?: string | null;
  onConfirm: (answers: string[][]) => void | Promise<void>;
  onCancel: () => void | Promise<void>;
};

const emptyAnswers = (count: number): AnswerState[] =>
  Array.from({ length: count }, () => ({ selected: [], custom: "" }));

export default function QuestionDock({
  question,
  submitting = false,
  error,
  onConfirm,
  onCancel
}: QuestionDockProps) {
  const [answers, setAnswers] = useState<AnswerState[]>(() =>
    emptyAnswers(question.questions.length)
  );

  useEffect(() => {
    setAnswers(emptyAnswers(question.questions.length));
  }, [question.request_id, question.questions.length]);

  const resolvedAnswers = useMemo(
    () =>
      answers.map((answer) => {
        const custom = answer.custom.trim();
        return custom ? [custom] : answer.selected;
      }),
    [answers]
  );
  const complete =
    resolvedAnswers.length === question.questions.length &&
    resolvedAnswers.every((answer) => answer.length > 0);

  const updateAnswer = (index: number, next: AnswerState) => {
    setAnswers((current) =>
      current.map((answer, answerIndex) => (answerIndex === index ? next : answer))
    );
  };

  return (
    <section className="mb-2 rounded-2xl border border-[#dbe7f7] bg-white p-4 shadow-[0_4px_16px_rgba(15,23,42,0.08)] dark:border-[#344054] dark:bg-[#1b2130]">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm font-semibold text-[#1f2937] dark:text-[#f3f4f6]">
          需要您的确认
        </div>
        <Button
          type="text"
          size="small"
          aria-label="关闭确认问题"
          disabled={submitting}
          icon={<CloseOutlined />}
          onClick={() => void onCancel()}
        />
      </div>

      <div className="max-h-[320px] space-y-4 overflow-y-auto pr-1">
        {question.questions.map((item, index) => {
          const answer = answers[index] ?? { selected: [], custom: "" };
          return (
            <fieldset key={`${question.request_id}-${index}`} className="m-0 border-0 p-0">
              <legend className="mb-2 text-sm font-medium text-[#344054] dark:text-[#e5e7eb]">
                {item.header ? `${item.header}：` : ""}
                {item.question}
              </legend>
              <div className="space-y-2">
                {(item.options ?? []).map((option) => {
                  const checked = answer.selected.includes(option.label);
                  const content = (
                    <span>
                      <span className="block text-sm text-[#344054] dark:text-[#e5e7eb]">
                        {option.label}
                      </span>
                      {option.description ? (
                        <span className="block text-xs text-[#7b8494]">
                          {option.description}
                        </span>
                      ) : null}
                    </span>
                  );
                  const control = item.multiple ? (
                    <Checkbox
                      className="flex w-full !items-start rounded-lg border border-[#eef1f5] px-3 py-2 hover:border-[#91caff] dark:border-[#303849]"
                      checked={checked}
                      onChange={(event) => {
                        const selected = event.target.checked
                          ? [...answer.selected, option.label]
                          : answer.selected.filter((label) => label !== option.label);
                        updateAnswer(index, { selected, custom: "" });
                      }}
                    >
                      {content}
                    </Checkbox>
                  ) : (
                    <Radio
                      className="flex w-full !items-start rounded-lg border border-[#eef1f5] px-3 py-2 hover:border-[#91caff] dark:border-[#303849]"
                      checked={checked}
                      onChange={() =>
                        updateAnswer(index, { selected: [option.label], custom: "" })
                      }
                    >
                      {content}
                    </Radio>
                  );
                  return <div key={option.label}>{control}</div>;
                })}
                {item.custom !== false ? (
                  <Input
                    aria-label={`${item.header || item.question}自定义答案`}
                    placeholder="其他，请输入您的答案"
                    value={answer.custom}
                    onChange={(event) =>
                      updateAnswer(index, { selected: [], custom: event.target.value })
                    }
                  />
                ) : null}
              </div>
            </fieldset>
          );
        })}
      </div>

      {error ? <div className="mt-2 text-xs text-[#ff4d4f]">{error}</div> : null}
      <div className="mt-4 flex justify-end gap-2">
        <Button disabled={submitting} onClick={() => void onCancel()}>
          Cancel
        </Button>
        <Button
          type="primary"
          loading={submitting}
          disabled={!complete}
          onClick={() => void onConfirm(resolvedAnswers)}
        >
          Confirm
        </Button>
      </div>
    </section>
  );
}
