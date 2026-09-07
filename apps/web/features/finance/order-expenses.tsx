"use client";
import { useState } from "react";
import { type SalesOrder } from "../orders/api";
import { useMemberContext } from "../overview/api";
import { useSessionScope } from "../overview/session";
import { type Expense, useExpenses, useExpenseSummary } from "./expense-api";
import { ExpenseForm, expenseCategories, expenseError } from "./expense-form";

function Panel({
  scope,
  order,
  permissions,
}: {
  scope: string;
  order: SalesOrder;
  permissions: string[];
}) {
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const query = useExpenses(scope, order.id, cursors.at(-1));
  const summary = useExpenseSummary(
    scope,
    order.id,
    permissions.includes("profit.read"),
  );
  const [editing, setEditing] = useState<{ original?: Expense }>();
  const [notice, setNotice] = useState("");
  return (
    <section className="finance-section" aria-label="订单费用">
      <p className="section-kicker">费用凭证 · 保留原始事实</p>
      <h2>订单费用</h2>
      <p>登记已发生的附加成本，不代表已付款。采购本金与应付结算另行管理。</p>
      {summary.data && (
        <div className="finance-payment">
          <h3>调整后预估毛利 · 非实际利润</h3>
          <strong>
            {summary.data.adjusted_forecast_gross_profit}{" "}
            {summary.data.order_currency_code}
          </strong>
          <p>
            报价毛利 {summary.data.quoted_gross_profit} − 额外费用净额{" "}
            {summary.data.net_additional_cost}
          </p>
          <p>
            报价已包含费用净额：{summary.data.net_included_cost}（不重复扣减）
          </p>
        </div>
      )}
      {summary.isError && <p role="alert">{expenseError(summary.error)}</p>}
      {notice && <p role="status">{notice}</p>}
      {query.isPending && <p role="status">正在读取费用…</p>}
      {query.isError && <p role="alert">{expenseError(query.error)}</p>}
      <button
        className="quiet-button"
        disabled={query.isFetching}
        onClick={() => {
          void query.refetch();
          if (permissions.includes("profit.read")) void summary.refetch();
        }}
      >
        刷新费用
      </button>
      {order.confirmed_at &&
        permissions.includes("expense.write") &&
        !editing && (
          <button
            className="secondary-button"
            onClick={() => {
              setNotice("");
              setEditing({});
            }}
          >
            登记订单费用
          </button>
        )}
      {editing && (
        <ExpenseForm
          scope={scope}
          orderId={order.id}
          currency={order.currency_code}
          original={editing.original}
          onDone={() => {
            setEditing(undefined);
            setCursors([undefined]);
            setNotice("费用操作已保存，原始凭证和操作记录均已保留。");
          }}
          onCancel={() => setEditing(undefined)}
        />
      )}
      {query.data?.items.length === 0 && (
        <p>尚无订单费用，请按已核对的凭证登记。</p>
      )}
      {query.data?.items.map((row) => (
        <article className="finance-payment" key={row.id}>
          <h3>
            {row.expense_number} ·{" "}
            {row.kind === "REVERSAL"
              ? "冲销记录"
              : row.reversed_by_expense_id
                ? "已冲销"
                : "费用登记"}
          </h3>
          <p>
            {expenseCategories[row.category]} ·{" "}
            {row.cost_treatment === "ADDITIONAL" ? "额外成本" : "报价已包含"} ·{" "}
            {row.incurred_on}
          </p>
          <strong>
            {row.amount} {row.currency_code} · 折合 {row.order_currency_amount}{" "}
            {row.order_currency_code}
          </strong>
          <p>
            汇率：{row.exchange_rate} · {row.description}
          </p>
          <p>凭证：{row.evidence_reference}</p>
          <p>原因：{row.reason}</p>
          {row.reversal_of_expense_id && (
            <p>原费用：{row.reversal_of_expense_id}</p>
          )}
          {row.kind === "EXPENSE" &&
            !row.reversed_by_expense_id &&
            permissions.includes("expense.write") &&
            !editing && (
              <button
                className="secondary-button"
                onClick={() => {
                  setNotice("");
                  setEditing({ original: row });
                }}
              >
                冲销费用 {row.expense_number}
              </button>
            )}
        </article>
      ))}
      <nav className="queue-pagination" aria-label="费用分页">
        <button
          className="secondary-button"
          disabled={
            cursors.length === 1 || query.isFetching || Boolean(editing)
          }
          onClick={() => setCursors((v) => v.slice(0, -1))}
        >
          上一页费用
        </button>
        <button
          className="secondary-button"
          disabled={
            !query.data?.has_more ||
            query.isFetching ||
            query.isError ||
            Boolean(editing)
          }
          onClick={() => {
            const next = query.data?.next_cursor;
            if (next) setCursors((v) => [...v, next]);
          }}
        >
          下一页费用
        </button>
      </nav>
    </section>
  );
}
export function OrderExpenses({ order }: { order: SalesOrder }) {
  const scope = useSessionScope();
  const member = useMemberContext(scope);
  if (!scope || member.isPending) return <p role="status">正在确认费用权限…</p>;
  if (member.isError) return <p role="alert">{expenseError(member.error)}</p>;
  if (!member.data.permissions.includes("expense.read")) return null;
  return (
    <Panel
      key={`${scope}:${order.id}`}
      scope={scope}
      order={order}
      permissions={member.data.permissions}
    />
  );
}
