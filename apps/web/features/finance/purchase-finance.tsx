"use client";
import { useState } from "react";
import type { PurchaseOrder } from "../orders/api";
import { useMemberContext } from "../overview/api";
import { useSessionScope } from "../overview/session";
import { expenseError } from "./expense-form";
import {
  usePayables,
  useSupplierPayments,
  type SupplierPayment,
} from "./supplier-api";
import { SupplierForm, type SupplierEdit } from "./supplier-form";

const states = {
  PENDING: "未到期",
  DUE: "今日到期",
  OVERDUE: "已逾期",
  PARTIALLY_PAID: "部分核销",
  PAID: "已结清",
  VOIDED: "已作废",
};
function paymentLabel(payment: SupplierPayment) {
  if (payment.kind === "REVERSAL") return "冲销凭证";
  return payment.reversed_by_payment_id ? "已冲销" : "付款登记";
}
function Pages({
  label,
  previous,
  next,
  busy,
  onPrevious,
  onNext,
}: {
  label: string;
  previous: boolean;
  next: boolean;
  busy: boolean;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    <nav className="queue-pagination" aria-label={`${label}分页`}>
      <button
        className="secondary-button"
        disabled={!previous || busy}
        onClick={onPrevious}
      >
        上一页{label}
      </button>
      <button
        className="secondary-button"
        disabled={!next || busy}
        onClick={onNext}
      >
        下一页{label}
      </button>
    </nav>
  );
}
function Panel({
  scope,
  purchase,
  permissions,
}: {
  scope: string;
  purchase: PurchaseOrder;
  permissions: string[];
}) {
  const [payableCursors, setPayableCursors] = useState<(string | undefined)[]>([
    undefined,
  ]);
  const [paymentCursors, setPaymentCursors] = useState<(string | undefined)[]>([
    undefined,
  ]);
  const payables = usePayables(scope, purchase.id, payableCursors.at(-1));
  const payments = useSupplierPayments(
    scope,
    purchase.supplier_company_id,
    purchase.currency_code ?? "",
    paymentCursors.at(-1),
  );
  const [edit, setEdit] = useState<SupplierEdit>();
  const [notice, setNotice] = useState("");
  const choices =
    payables.data?.items.filter(
      (p) => p.status !== "VOIDED" && /[1-9]/.test(p.balance),
    ) ?? [];
  const start = (value: SupplierEdit) => {
    setNotice("");
    setEdit(value);
  };
  return (
    <section
      className="finance-section"
      aria-label={`供应商结算 ${purchase.purchase_order_number}`}
    >
      <h3>供应商应付与付款</h3>
      <p>
        此采购单应付与同供应商 {purchase.currency_code}{" "}
        付款凭证。付款可用于同供应商的其他采购，不等于此单已付。
      </p>
      {notice && <p role="status">{notice}</p>}
      {!edit && (
        <div className="queue-pagination">
          {purchase.confirmed_at && permissions.includes("payable.write") && (
            <button
              className="secondary-button"
              onClick={() => start({ mode: "payable", choices: [] })}
            >
              登记供应商应付
            </button>
          )}
          {permissions.includes("supplier_payment.record") && (
            <button
              className="secondary-button"
              onClick={() => start({ mode: "payment", choices: [] })}
            >
              登记供应商付款
            </button>
          )}
        </div>
      )}
      {edit && (
        <SupplierForm
          scope={scope}
          purchase={purchase}
          edit={edit}
          onDone={() => {
            setEdit(undefined);
            setPayableCursors([undefined]);
            setPaymentCursors([undefined]);
            setNotice("供应商结算操作已保存，未发起银行转账。");
          }}
          onCancel={() => setEdit(undefined)}
        />
      )}
      <h4>此采购单应付</h4>
      <button
        className="quiet-button"
        onClick={() => payables.refetch()}
        disabled={payables.isFetching}
      >
        刷新供应商应付
      </button>
      {payables.isPending && <p role="status">正在读取供应商应付…</p>}
      {payables.isError && <p role="alert">{expenseError(payables.error)}</p>}
      {payables.data?.items.length === 0 && (
        <p>尚无应付记录；请按核对后的采购本金凭证登记。</p>
      )}
      {payables.data?.items.map((p) => (
        <article key={p.id} className="finance-payment">
          <h4>
            {p.payable_number} · {states[p.status]}
          </h4>
          <strong>
            待付 {p.balance} {p.currency_code}
          </strong>
          <p>
            原金额 {p.amount} · 已核销 {p.paid_amount} · 到期 {p.due_date}
          </p>
          <p>
            凭证：{p.reference} · {p.description}
          </p>
          {p.void_reason && <p>作废原因：{p.void_reason}</p>}
          {p.status !== "VOIDED" &&
            !/[1-9]/.test(p.paid_amount) &&
            permissions.includes("payable.write") &&
            !edit && (
              <button
                className="quiet-button"
                onClick={() => start({ mode: "void", payable: p, choices: [] })}
              >
                作废应付 {p.payable_number}
              </button>
            )}
        </article>
      ))}
      <Pages
        label="供应商应付"
        previous={payableCursors.length > 1}
        next={Boolean(payables.data?.has_more) && !payables.isError}
        busy={payables.isFetching || Boolean(edit)}
        onPrevious={() => setPayableCursors((v) => v.slice(0, -1))}
        onNext={() => {
          const next = payables.data?.next_cursor;
          if (next) setPayableCursors((v) => [...v, next]);
        }}
      />
      <h4>同供应商付款凭证</h4>
      <button
        className="quiet-button"
        onClick={() => payments.refetch()}
        disabled={payments.isFetching}
      >
        刷新供应商付款
      </button>
      {payments.isPending && <p role="status">正在读取供应商付款…</p>}
      {payments.isError && <p role="alert">{expenseError(payments.error)}</p>}
      {payments.data?.items.length === 0 && <p>尚无同币种供应商付款凭证。</p>}
      {payments.data?.items.map((p) => (
        <article key={p.id} className="finance-payment">
          <h4>
            {p.payment_number} · {paymentLabel(p)}
          </h4>
          <strong>
            {p.amount} {p.currency_code} · 可用 {p.available_amount}
          </strong>
          <p>
            {p.paid_on} · 凭证：{p.reference}
          </p>
          <p>原因：{p.reason}</p>
          <details>
            <summary>查看供应商核销记录</summary>
            {p.allocations.length === 0 ? (
              <p>此凭证尚无核销记录。</p>
            ) : (
              p.allocations.map((a) => (
                <p key={a.id}>
                  {a.kind === "REVERSAL" ? "反向核销" : "核销"} {a.amount}{" "}
                  {p.currency_code} · 应付 {a.payable_id}
                </p>
              ))
            )}
          </details>
          {p.kind === "PAYMENT" && !p.reversed_by_payment_id && !edit && (
            <div className="queue-pagination">
              {permissions.includes("supplier_payment.allocate") &&
                choices.length > 0 &&
                /[1-9]/.test(p.available_amount) && (
                  <button
                    className="secondary-button"
                    onClick={() =>
                      start({ mode: "allocate", payment: p, choices })
                    }
                  >
                    核销付款 {p.payment_number}
                  </button>
                )}
              {permissions.includes("supplier_payment.reverse") && (
                <button
                  className="quiet-button"
                  onClick={() =>
                    start({ mode: "reverse", payment: p, choices: [] })
                  }
                >
                  冲销付款 {p.payment_number}
                </button>
              )}
            </div>
          )}
        </article>
      ))}
      <Pages
        label="供应商付款"
        previous={paymentCursors.length > 1}
        next={Boolean(payments.data?.has_more) && !payments.isError}
        busy={payments.isFetching || Boolean(edit)}
        onPrevious={() => setPaymentCursors((v) => v.slice(0, -1))}
        onNext={() => {
          const next = payments.data?.next_cursor;
          if (next) setPaymentCursors((v) => [...v, next]);
        }}
      />
    </section>
  );
}
export function PurchaseFinance({ purchase }: { purchase: PurchaseOrder }) {
  const scope = useSessionScope();
  const member = useMemberContext(scope);
  const [open, setOpen] = useState(false);
  if (!scope || member.isPending)
    return <p role="status">正在确认供应商结算权限…</p>;
  if (member.isError) return <p role="alert">{expenseError(member.error)}</p>;
  if (
    !member.data.permissions.includes("payable.read") ||
    !member.data.permissions.includes("supplier_payment.read") ||
    !member.data.permissions.includes("profit.read")
  )
    return null;
  if (purchase.currency_code === null)
    return <p role="alert">采购币种不可用，请刷新后再查看供应商结算。</p>;
  return (
    <>
      <button
        className="secondary-button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "收起供应商结算" : "查看供应商结算"}
      </button>
      {open && (
        <Panel
          key={`${scope}:${purchase.id}`}
          scope={scope}
          purchase={purchase}
          permissions={member.data.permissions}
        />
      )}
    </>
  );
}
