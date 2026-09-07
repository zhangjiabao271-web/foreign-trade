"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ApiClientError } from "@trade-workbench/api-client";
import { useMemberContext } from "../overview/api";
import { useSessionScope } from "../overview/session";
import { type PurchaseOrder, usePurchaseChangeCommand } from "./api";

const quantity = z
  .string()
  .trim()
  .regex(/^\d{1,14}(\.\d{1,4})?$/, "请输入非负数，最多四位小数");
const schema = z
  .object({
    mode: z.enum(["cancel", "amend"]),
    reason: z.string().trim().min(1, "请填写取消或变更原因").max(1000),
    reference: z.string().trim().max(200),
    confirmed: z
      .boolean()
      .refine(Boolean, "请确认保留已收货事实且已核对供应商处理依据"),
    supplier: z.string().trim(),
    currency: z.string().trim(),
    rate: z.string().trim(),
    lines: z.array(z.object({ quantity, unit_cost: quantity })),
  })
  .superRefine((data, context) => {
    if (data.mode !== "amend") return;
    if (!z.uuid().safeParse(data.supplier).success)
      context.addIssue({
        code: "custom",
        path: ["supplier"],
        message: "请输入有效的供应商公司 ID",
      });
    if (!/^[A-Z]{3}$/.test(data.currency))
      context.addIssue({
        code: "custom",
        path: ["currency"],
        message: "请输入三位大写币种代码",
      });
    if (!/^\d{1,10}(\.\d{1,8})?$/.test(data.rate) || Number(data.rate) <= 0)
      context.addIssue({
        code: "custom",
        path: ["rate"],
        message: "请输入正汇率，最多八位小数",
      });
    if (!data.lines.some((line) => Number(line.quantity) > 0))
      context.addIssue({
        code: "custom",
        path: ["lines"],
        message: "至少填写一项正数替代数量",
      });
  });
function errorText(error: unknown) {
  if (error instanceof ApiClientError) {
    if (error.problem.code === "SUPPLIER_CANCELLATION_REFERENCE_REQUIRED")
      return "已发送的采购必须填写供应商取消依据。";
    if (error.problem.status === 403) return "当前成员无采购审批权限。";
    if (error.problem.status === 409)
      return "采购状态、数量或提交版本不符合要求。请返回并刷新采购单后核对，原单不会被部分修改。";
  }
  return "未能确认处理结果。请保留表单重试或返回刷新核对，重复请求会被校验。";
}
function ChangeForm({
  order,
  mode,
  onClose,
}: {
  order: PurchaseOrder;
  mode: "cancel" | "amend";
  onClose: () => void;
}) {
  const mutation = usePurchaseChangeCommand(order.id);
  const items = order.items ?? [];
  const [submission, setSubmission] = useState<{
    payload: string;
    key: string;
  } | null>(null);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: {
      mode,
      reason: "",
      reference: "",
      confirmed: false,
      supplier: order.supplier_company_id,
      currency: order.currency_code ?? "",
      rate: order.exchange_rate ?? "",
      lines: items.map((item) => ({
        quantity: "0",
        unit_cost: item.unit_cost ?? "",
      })),
    },
  });
  let submitLabel = "确认取消未收货部分";
  if (mode === "amend") submitLabel = "确认变更并生成新草稿";
  if (mutation.isPending) submitLabel = "正在处理…";
  return (
    <form
      className="purchase-change-form"
      onSubmit={form.handleSubmit((data) => {
        const base = {
          expected_version: order.version,
          reason: data.reason,
          supplier_reference: data.reference || null,
        };
        const body =
          mode === "amend"
            ? {
                ...base,
                replacement: {
                  sales_order_id: order.sales_order_id,
                  supplier_company_id: data.supplier,
                  currency_code: data.currency,
                  exchange_rate: data.rate,
                  items: data.lines.flatMap((line, index) =>
                    Number(line.quantity) > 0
                      ? [
                          {
                            sales_order_item_id:
                              items[index].sales_order_item_id,
                            quantity: line.quantity,
                            unit_cost: line.unit_cost,
                          },
                        ]
                      : [],
                  ),
                },
              }
            : base;
        const payload = JSON.stringify(body);
        const key =
          submission?.payload === payload
            ? submission.key
            : crypto.randomUUID();
        setSubmission({ payload, key });
        if ("replacement" in body)
          mutation.mutate(
            { command: "amend", body, key },
            { onSuccess: onClose },
          );
        else
          mutation.mutate(
            { command: "cancel", body, key },
            { onSuccess: onClose },
          );
      })}
    >
      <h4>{mode === "amend" ? "变更未收货采购" : "取消未收货承诺"}</h4>
      <p>
        原单、价格和已收货数量会保留。本操作不退货、不撤销应付款，也不会向供应商发送消息。
      </p>
      {mode === "amend" && (
        <p>
          旧单剩余承诺取消后，生成关联的新草稿；新单需要重新批准、发送和供应商确认。
        </p>
      )}
      <fieldset disabled={mutation.isPending}>
        <label>
          取消或变更原因
          <textarea {...form.register("reason")} rows={3} />
        </label>
        {form.formState.errors.reason && (
          <p role="alert">{form.formState.errors.reason.message}</p>
        )}
        <label>
          供应商取消依据
          <input {...form.register("reference")} />
        </label>
        <p>已发送或已确认的采购需填写对方确认号或证据引用。</p>
        {mode === "amend" && (
          <>
            <label>
              新供应商公司 ID
              <input {...form.register("supplier")} />
            </label>
            {form.formState.errors.supplier && (
              <p role="alert">{form.formState.errors.supplier.message}</p>
            )}
            <label>
              新采购币种
              <input {...form.register("currency")} />
            </label>
            {form.formState.errors.currency && (
              <p role="alert">{form.formState.errors.currency.message}</p>
            )}
            <label>
              新采购到订单币种汇率
              <input inputMode="decimal" {...form.register("rate")} />
            </label>
            {form.formState.errors.rate && (
              <p role="alert">{form.formState.errors.rate.message}</p>
            )}
            {items.map((item, index) => (
              <div key={item.id}>
                <p>
                  {item.sku_snapshot} · 原订货 {item.quantity} · 已收{" "}
                  {item.received_quantity} {item.unit_snapshot}
                </p>
                <label>
                  {item.sku_snapshot} 替代数量
                  <input
                    inputMode="decimal"
                    {...form.register(`lines.${index}.quantity`)}
                  />
                </label>
                <label>
                  {item.sku_snapshot} 新采购单价
                  <input
                    inputMode="decimal"
                    {...form.register(`lines.${index}.unit_cost`)}
                  />
                </label>
                {form.formState.errors.lines?.[index] && (
                  <p role="alert">
                    请检查该行数量与单价（非负数，最多四位小数）。
                  </p>
                )}
              </div>
            ))}
            {form.formState.errors.lines?.root && (
              <p role="alert">{form.formState.errors.lines.root.message}</p>
            )}
          </>
        )}
        <label className="outbox-confirm">
          <input type="checkbox" {...form.register("confirmed")} />
          已核对供应商依据，确认保留已收货事实
        </label>
        {form.formState.errors.confirmed && (
          <p role="alert">{form.formState.errors.confirmed.message}</p>
        )}
        {mutation.isError && <p role="alert">{errorText(mutation.error)}</p>}
        <div className="purchase-actions">
          <button type="submit" className="primary-button">
            {submitLabel}
          </button>
          <button type="button" className="secondary-button" onClick={onClose}>
            返回，不做变更
          </button>
        </div>
      </fieldset>
    </form>
  );
}
export function PurchaseChanges({ order }: { order: PurchaseOrder }) {
  const scope = useSessionScope();
  const member = useMemberContext(scope);
  const [mode, setMode] = useState<"cancel" | "amend" | null>(null);
  if (["CANCELLED", "CLOSED", "RECEIVED"].includes(order.status)) return null;
  if (!member.data?.permissions.includes("procurement.approve")) return null;
  if (!member.data.permissions.includes("profit.read")) return null;
  if (mode)
    return (
      <ChangeForm order={order} mode={mode} onClose={() => setMode(null)} />
    );
  return (
    <div className="purchase-actions">
      <button className="secondary-button" onClick={() => setMode("amend")}>
        变更采购
      </button>
      <button className="secondary-button" onClick={() => setMode("cancel")}>
        取消未收货部分
      </button>
    </div>
  );
}
