"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ApiClientError } from "@trade-workbench/api-client";
import { type Expense, useExpenseWrite } from "./expense-api";

export const expenseCategories = {
  FREIGHT: "运费",
  INSPECTION: "验货费",
  BANK_FEE: "银行手续费",
  CUSTOMS: "报关费用",
  OTHER: "其他费用",
};
export function expenseError(error: unknown) {
  if (error instanceof ApiClientError) return error.problem.detail;
  return error instanceof Error ? error.message : "费用操作失败，请重试。";
}
const decimal = (places: number) =>
  z
    .string()
    .regex(
      new RegExp(`^\\d+(\\.\\d{1,${places}})?$`),
      `请填写最多 ${places} 位小数的正数`,
    )
    .refine((v) => /[1-9]/.test(v), "金额和汇率必须大于零");
export const expenseSchema = z.object({
  category: z.enum(["FREIGHT", "INSPECTION", "BANK_FEE", "CUSTOMS", "OTHER"]),
  cost_treatment: z.enum(["ADDITIONAL", "INCLUDED_IN_QUOTATION"]),
  amount: decimal(4),
  currency_code: z.string().regex(/^[A-Z]{3}$/, "请填写三位大写币种"),
  exchange_rate: decimal(8),
  incurred_on: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "请选择费用发生日期"),
  description: z.string().trim().min(3, "费用说明至少三个字符").max(500),
  evidence_reference: z.string().trim().min(3, "凭证引用至少三个字符").max(240),
  reason: z.string().trim().min(3, "操作原因至少三个字符").max(500),
  confirmed: z.boolean().refine(Boolean, "请确认费用归类及操作含义"),
});
export function ExpenseForm({
  scope,
  orderId,
  currency,
  original,
  onDone,
  onCancel,
}: {
  scope: string;
  orderId: string;
  currency: string;
  original?: Expense;
  onDone: () => void;
  onCancel: () => void;
}) {
  const command = useExpenseWrite(scope, orderId);
  const [retry, setRetry] = useState<{ payload: string; key: string }>();
  const form = useForm<z.infer<typeof expenseSchema>>({
    resolver: zodResolver(expenseSchema),
    defaultValues: {
      category: original?.category ?? "FREIGHT",
      cost_treatment: original?.cost_treatment,
      amount: original?.amount ?? "",
      currency_code: original?.currency_code ?? currency,
      exchange_rate: original?.exchange_rate ?? "1",
      incurred_on: original?.incurred_on ?? "",
      description: original?.description ?? "",
      evidence_reference: original?.evidence_reference ?? "",
      reason: "",
      confirmed: false,
    },
  });
  const labels = {
    amount: "费用金额",
    currency_code: "费用币种",
    exchange_rate: "折算汇率（费用币种 → 订单币种）",
    incurred_on: "费用发生日期",
    description: "费用说明",
    evidence_reference: "凭证引用",
    reason: "费用操作原因",
  } as const;
  return (
    <form
      className="finance-form"
      onSubmit={form.handleSubmit((values) => {
        const body = expenseSchema.omit({ confirmed: true }).parse(values);
        const payload = JSON.stringify({
          body,
          original: original?.id,
          version: original?.version,
        });
        const key =
          retry?.payload === payload ? retry.key : crypto.randomUUID();
        setRetry({ payload, key });
        command.mutate(
          original
            ? {
                action: "reverse",
                id: original.id,
                body: {
                  expected_version: original.version,
                  reason: body.reason,
                },
                key,
              }
            : { action: "record", body, key },
          { onSuccess: onDone },
        );
      })}
    >
      <h3>{original ? `冲销 ${original.expense_number}` : "登记订单费用"}</h3>
      <fieldset disabled={command.isPending}>
        {!original && (
          <>
            <label>
              费用类别
              <select {...form.register("category")}>
                {Object.entries(expenseCategories).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
            <label>
              费用成本归类
              <select {...form.register("cost_treatment")}>
                <option value="">请人工核对后选择</option>
                <option value="ADDITIONAL">额外成本：扣减预估毛利</option>
                <option value="INCLUDED_IN_QUOTATION">
                  报价已包含：不重复扣减
                </option>
              </select>
            </label>
            {form.formState.errors.cost_treatment && (
              <p role="alert">请选择费用成本归类</p>
            )}
          </>
        )}
        {(Object.keys(labels) as (keyof typeof labels)[])
          .filter((key) => !original || key === "reason")
          .map((key) => (
            <div key={key}>
              <label>
                {labels[key]}
                <input
                  type={key === "incurred_on" ? "date" : "text"}
                  inputMode={
                    key === "amount" || key === "exchange_rate"
                      ? "decimal"
                      : undefined
                  }
                  {...form.register(key)}
                />
              </label>
              {form.formState.errors[key] && (
                <p role="alert" className="form-error">
                  {form.formState.errors[key]?.message}
                </p>
              )}
            </div>
          ))}
        <p>
          {original
            ? "全额冲销会新增反向记录，原费用保留。需要更正金额时，冲销后重新登记。"
            : `1 单位费用币种折合多少 ${currency}；同币种汇率必须为 1。费用不是付款证明。`}
        </p>
        <label className="contract-confirm">
          <input type="checkbox" {...form.register("confirmed")} />
          {original
            ? "我确认全额冲销此费用"
            : "我已核对凭证及归类，避免重复扣减报价成本"}
        </label>
        {form.formState.errors.confirmed && (
          <p role="alert">{form.formState.errors.confirmed.message}</p>
        )}
        {command.isError && <p role="alert">{expenseError(command.error)}</p>}
        <div className="queue-pagination">
          <button className="primary-button">
            {command.isPending
              ? "正在保存…"
              : original
                ? "确认冲销费用"
                : "保存订单费用"}
          </button>
          <button type="button" className="secondary-button" onClick={onCancel}>
            取消费用操作
          </button>
        </div>
      </fieldset>
    </form>
  );
}
