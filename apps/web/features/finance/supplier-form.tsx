"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import type { PurchaseOrder } from "../orders/api";
import { expenseError } from "./expense-form";
import {
  type Payable,
  type SupplierPayment,
  type SupplierWrite,
  useSupplierWrite,
} from "./supplier-api";

export type SupplierEdit = {
  mode: "payable" | "payment" | "allocate" | "void" | "reverse";
  payable?: Payable;
  payment?: SupplierPayment;
  choices: Payable[];
};
const labels = {
  payable: "保存供应商应付",
  payment: "保存供应商付款",
  allocate: "确认供应商核销",
  void: "确认作废应付",
  reverse: "确认冲销供应商付款",
};
function operationExplanation(mode: SupplierEdit["mode"]) {
  if (mode === "reverse")
    return "冲销纠正错误登记，会反向恢复相关应付余额；不代表银行退款。";
  if (mode === "void") return "只可作废未核销的应付，原凭证和金额保留。";
  return "按真实凭证登记，不从系统发起银行转账。采购金额不自动等于应付金额。";
}
const schema = z.object({
  amount: z.string(),
  businessDate: z.string(),
  dueDate: z.string(),
  reference: z.string().trim().max(240),
  description: z.string().trim().max(500),
  reason: z.string().trim().min(3, "请填写至少三个字符的操作原因").max(500),
  payableId: z.string(),
  method: z.enum(["BANK_TRANSFER", "CARD", "CASH", "OTHER"]),
  confirmed: z.boolean().refine(Boolean, "请核对凭证并确认操作含义"),
});

export function SupplierForm({
  scope,
  purchase,
  edit,
  onDone,
  onCancel,
}: {
  scope: string;
  purchase: PurchaseOrder;
  edit: SupplierEdit;
  onDone: () => void;
  onCancel: () => void;
}) {
  const mutation = useSupplierWrite(scope);
  const [retry, setRetry] = useState<{ payload: string; key: string }>();
  const { mode, payable, payment, choices } = edit;
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(
      schema.superRefine((v, ctx) => {
        const issue = (path: keyof typeof v, message: string) =>
          ctx.addIssue({ code: "custom", path: [path], message });
        if (
          ["payable", "payment", "allocate"].includes(mode) &&
          (!/^\d+(\.\d{1,4})?$/.test(v.amount) || !/[1-9]/.test(v.amount))
        )
          issue("amount", "请输入大于零且最多四位小数的金额");
        if (mode === "payable" || mode === "payment") {
          if (!/^\d{4}-\d{2}-\d{2}$/.test(v.businessDate))
            issue("businessDate", "请选择已发生的业务日期");
          if (v.reference.length < 3)
            issue("reference", "请填写至少三个字符的凭证引用");
        }
        if (mode === "payable") {
          if (!/^\d{4}-\d{2}-\d{2}$/.test(v.dueDate))
            issue("dueDate", "请选择应付到期日");
          if (v.description.length < 3)
            issue("description", "请填写至少三个字符的应付说明");
        }
        if (mode === "allocate" && !choices.some((p) => p.id === v.payableId))
          issue("payableId", "请选择本页待核销应付");
      }),
    ),
    defaultValues: {
      amount: "",
      businessDate: "",
      dueDate: "",
      reference: "",
      description: "",
      reason: "",
      payableId: "",
      method: "BANK_TRANSFER",
      confirmed: false,
    },
  });
  const fields = [
    ...(["payable", "payment", "allocate"].includes(mode) ? ["amount"] : []),
    ...(mode === "payable" || mode === "payment"
      ? ["businessDate", "reference"]
      : []),
    ...(mode === "payable" ? ["dueDate", "description"] : []),
    "reason",
  ] as (
    | "amount"
    | "businessDate"
    | "reference"
    | "dueDate"
    | "description"
    | "reason"
  )[];
  const names = {
    amount: "供应商结算金额",
    businessDate: "供应商业务日期",
    reference: "供应商凭证引用",
    dueDate: "应付到期日",
    description: "应付说明",
    reason: "供应商结算操作原因",
  };
  return (
    <form
      className="finance-form"
      onSubmit={form.handleSubmit((v) => {
        if (purchase.currency_code === null) {
          form.setError("root", { message: "采购币种不可用，请刷新后重试。" });
          return;
        }
        const payload = JSON.stringify({
          v,
          mode,
          payableVersion: payable?.version,
          paymentVersion: payment?.version,
          choices: choices.map((p) => [p.id, p.version]),
        });
        const key =
          retry?.payload === payload ? retry.key : crypto.randomUUID();
        setRetry({ payload, key });
        let command: SupplierWrite;
        switch (mode) {
          case "payable":
            command = {
              action: mode,
              key,
              body: {
                purchase_order_id: purchase.id,
                amount: v.amount,
                incurred_on: v.businessDate,
                due_date: v.dueDate,
                reference: v.reference,
                description: v.description,
                reason: v.reason,
              },
            };
            break;
          case "payment":
            command = {
              action: mode,
              key,
              body: {
                supplier_company_id: purchase.supplier_company_id,
                currency_code: purchase.currency_code,
                amount: v.amount,
                paid_on: v.businessDate,
                method: v.method,
                reference: v.reference,
                reason: v.reason,
              },
            };
            break;
          case "allocate": {
            const selected = choices.find((p) => p.id === v.payableId);
            if (!selected || !payment) return;
            command = {
              action: mode,
              id: payment.id,
              key,
              body: {
                expected_version: payment.version,
                reason: v.reason,
                allocations: [
                  {
                    payable_id: selected.id,
                    expected_version: selected.version,
                    amount: v.amount,
                  },
                ],
              },
            };
            break;
          }
          case "void":
            if (!payable) return;
            command = {
              action: mode,
              id: payable.id,
              key,
              body: { expected_version: payable.version, reason: v.reason },
            };
            break;
          case "reverse":
            if (!payment) return;
            command = {
              action: mode,
              id: payment.id,
              key,
              body: { expected_version: payment.version, reason: v.reason },
            };
            break;
        }
        mutation.mutate(command, { onSuccess: onDone });
      })}
    >
      <h3>{labels[mode]}</h3>
      <p>
        采购单 {purchase.purchase_order_number} · {purchase.currency_code}
      </p>
      {payment && (
        <p>
          付款 {payment.payment_number} · 当前可用 {payment.available_amount}{" "}
          {payment.currency_code}
        </p>
      )}
      {payable && (
        <p>
          应付 {payable.payable_number} · 原金额 {payable.amount}{" "}
          {payable.currency_code}
        </p>
      )}
      <fieldset disabled={mutation.isPending}>
        {mode === "payment" && (
          <label>
            供应商付款方式
            <select {...form.register("method")}>
              <option value="BANK_TRANSFER">银行转账</option>
              <option value="CARD">银行卡</option>
              <option value="CASH">现金</option>
              <option value="OTHER">其他</option>
            </select>
          </label>
        )}
        {mode === "allocate" && (
          <>
            <label>
              待核销供应商应付
              <select {...form.register("payableId")}>
                <option value="">请选择已核对的应付</option>
                {choices.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.payable_number} · 待付 {p.balance} {p.currency_code}
                  </option>
                ))}
              </select>
            </label>
            {form.formState.errors.payableId && (
              <p role="alert">{form.formState.errors.payableId.message}</p>
            )}
          </>
        )}
        {fields.map((field) => (
          <div key={field}>
            <label>
              {names[field]}
              <input
                {...form.register(field)}
                type={
                  field === "businessDate" || field === "dueDate"
                    ? "date"
                    : "text"
                }
                inputMode={field === "amount" ? "decimal" : undefined}
              />
            </label>
            {form.formState.errors[field] && (
              <p role="alert">{form.formState.errors[field]?.message}</p>
            )}
          </div>
        ))}
        <p>{operationExplanation(mode)}</p>
        <label className="contract-confirm">
          <input type="checkbox" {...form.register("confirmed")} />
          我已核对供应商凭证并确认本次操作
        </label>
        {form.formState.errors.root && (
          <p role="alert">{form.formState.errors.root.message}</p>
        )}
        {form.formState.errors.confirmed && (
          <p role="alert">{form.formState.errors.confirmed.message}</p>
        )}
        {mutation.isError && <p role="alert">{expenseError(mutation.error)}</p>}
        <div className="queue-pagination">
          <button className="primary-button">
            {mutation.isPending ? "正在保存…" : labels[mode]}
          </button>
          <button type="button" className="secondary-button" onClick={onCancel}>
            取消供应商结算操作
          </button>
        </div>
      </fieldset>
    </form>
  );
}
