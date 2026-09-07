"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ApiClientError } from "@trade-workbench/api-client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import type { SalesOrder } from "../orders/api";
import { useMemberContext } from "../overview/api";
import { useSessionScope } from "../overview/session";
import { WorkTextReview } from "./work-review";
import {
  useFinanceCommand,
  useOrderFinance,
  useCustomerPayments,
  type Payment,
  type Receivable,
  type Task,
} from "./api";

const money = z
  .string()
  .regex(/^(?:0|[1-9]\d{0,13})(?:\.\d{1,4})?$/, "金额最多保留四位小数")
  .refine((value) => /[1-9]/.test(value), "金额必须大于零");
const dateValue = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "请选择日期");
const generateSchema = z.object({ deposit: dateValue, balance: dateValue });
const receiptSchema = z.object({
  amount: money,
  received: dateValue,
  reference: z.string().max(160),
  notes: z.string().max(2000, "备注最多 2000 个字符"),
});
const allocationSchema = z.object({
  paymentId: z.string().uuid("请选择收款"),
  receivableId: z.string().uuid("请选择应收"),
  amount: money,
});
const reasonSchema = z.object({
  reason: z.string().trim().min(3, "请至少填写三个字符").max(500),
});
const completeSchema = z.object({
  waiver: z
    .string()
    .trim()
    .max(500)
    .refine((value) => !value || value.length >= 8, "豁免原因至少八个字符"),
});
const searchSchema = z.object({
  query: z.string().trim().max(160, "搜索最多 160 个字符"),
});

function ErrorMessage({ error }: { error: unknown }) {
  if (!error) return null;
  const text =
    error instanceof ApiClientError
      ? error.problem.status === 403
        ? "当前成员没有此操作权限，请交由财务或经理处理。"
        : error.problem.detail
      : "连接失败，请检查服务后重试。";
  return (
    <p className="form-error" role="alert">
      {text}
    </p>
  );
}
function Validation({ message }: { message?: string }) {
  return message ? (
    <p className="form-error" role="alert">
      {message}
    </p>
  ) : null;
}

function Generate({ order }: { order: SalesOrder }) {
  const command = useFinanceCommand(order.id);
  const form = useForm<z.infer<typeof generateSchema>>({
    resolver: zodResolver(generateSchema),
    defaultValues: { deposit: order.deposit_due_date ?? "", balance: "" },
  });
  return (
    <form
      className="finance-form"
      onSubmit={form.handleSubmit((values) =>
        command.mutate({
          kind: "generate",
          body: {
            deposit_due_date: values.deposit,
            balance_due_date: values.balance,
          },
        }),
      )}
    >
      <h3>生成应收计划</h3>
      <p>定金与尾款由订单快照计算，生成后不能通过重复提交改写日期。</p>
      <label>
        定金到期日
        <input type="date" {...form.register("deposit")} />
      </label>
      <Validation message={form.formState.errors.deposit?.message} />
      <label>
        尾款到期日
        <input type="date" {...form.register("balance")} />
      </label>
      <Validation message={form.formState.errors.balance?.message} />
      <ErrorMessage error={command.error} />
      <button className="primary-button" disabled={command.isPending}>
        生成定金和尾款应收
      </button>
    </form>
  );
}

function RecordReceipt({ order }: { order: SalesOrder }) {
  const command = useFinanceCommand(order.id);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [saved, setSaved] = useState(false);
  const form = useForm<z.infer<typeof receiptSchema>>({
    resolver: zodResolver(receiptSchema),
    defaultValues: { amount: "", received: "", reference: "", notes: "" },
  });
  return (
    <form
      className="finance-form"
      onSubmit={form.handleSubmit((values) => {
        setSaved(false);
        command.mutate(
          {
            kind: "record",
            key,
            body: {
              company_id: order.company_id,
              currency_code: order.currency_code,
              amount: values.amount,
              method: "BANK_TRANSFER",
              received_at: new Date(
                values.received + "T12:00:00",
              ).toISOString(),
              reference: values.reference || null,
              notes: values.notes || null,
            },
          },
          {
            onSuccess: () => {
              setKey(crypto.randomUUID());
              form.reset();
              setSaved(true);
            },
          },
        );
      })}
    >
      <h3>记录银行收款</h3>
      <p>
        只记录已发生的收款事实，不会发起转账；币种为 {order.currency_code}。
      </p>
      <label>
        实收金额
        <input inputMode="decimal" {...form.register("amount")} />
      </label>
      <Validation message={form.formState.errors.amount?.message} />
      <label>
        收款日期
        <input type="date" {...form.register("received")} />
      </label>
      <Validation message={form.formState.errors.received?.message} />
      <label>
        银行流水号
        <input {...form.register("reference")} />
      </label>
      <Validation message={form.formState.errors.reference?.message} />
      <p>流水号仅用于识别收款，请勿填写成本或利润。</p>
      <label>
        收款备注（默认保密）
        <textarea {...form.register("notes")} />
      </label>
      <Validation message={form.formState.errors.notes?.message} />
      <ErrorMessage error={command.error} />
      {saved && <p role="status">收款已记录，请在右侧核销到对应应收。</p>}
      <button className="primary-button" disabled={command.isPending}>
        记录收款
      </button>
    </form>
  );
}

function Allocate({
  order,
  payments,
  receivables,
}: {
  order: SalesOrder;
  payments: Payment[];
  receivables: Receivable[];
}) {
  const command = useFinanceCommand(order.id);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const form = useForm<z.infer<typeof allocationSchema>>({
    resolver: zodResolver(allocationSchema),
    defaultValues: { paymentId: "", receivableId: "", amount: "" },
  });
  return (
    <form
      className="finance-form"
      onSubmit={form.handleSubmit((values) =>
        command.mutate(
          {
            kind: "allocate",
            key,
            paymentId: values.paymentId,
            body: {
              allocations: [
                { receivable_id: values.receivableId, amount: values.amount },
              ],
            },
          },
          {
            onSuccess: () => {
              setKey(crypto.randomUUID());
              form.reset();
            },
          },
        ),
      )}
    >
      <h3>将收款核销到应收</h3>
      <p>支持分次核销；最终可用额和应收余额由后台核验。</p>
      <label>
        选择收款
        <select {...form.register("paymentId")}>
          <option value="">请选择</option>
          {payments
            .filter((row) => row.kind === "RECEIPT" && row.status === "ACTIVE")
            .map((row) => (
              <option key={row.id} value={row.id}>
                {row.payment_number} · 可用 {row.available_amount}{" "}
                {row.currency_code}
              </option>
            ))}
        </select>
      </label>
      <Validation message={form.formState.errors.paymentId?.message} />
      <label>
        选择应收
        <select {...form.register("receivableId")}>
          <option value="">请选择</option>
          {receivables.map((row) => (
            <option key={row.id} value={row.id}>
              {row.installment_type === "DEPOSIT" ? "定金" : "尾款"} · 未结{" "}
              {row.balance} {row.currency_code}
            </option>
          ))}
        </select>
      </label>
      <Validation message={form.formState.errors.receivableId?.message} />
      <label>
        核销金额
        <input inputMode="decimal" {...form.register("amount")} />
      </label>
      <Validation message={form.formState.errors.amount?.message} />
      <ErrorMessage error={command.error} />
      <button className="primary-button" disabled={command.isPending}>
        确认核销
      </button>
    </form>
  );
}

function ReverseReceipt({
  orderId,
  payment,
}: {
  orderId: string;
  payment: Payment;
}) {
  const [open, setOpen] = useState(false);
  const command = useFinanceCommand(orderId);
  const form = useForm<z.infer<typeof reasonSchema>>({
    resolver: zodResolver(reasonSchema),
  });
  if (!open)
    return (
      <button className="quiet-button" onClick={() => setOpen(true)}>
        冲销 {payment.payment_number}
      </button>
    );
  return (
    <form
      className="finance-form"
      onSubmit={form.handleSubmit((values) =>
        command.mutate(
          {
            kind: "reverse",
            paymentId: payment.id,
            body: { reason: values.reason },
          },
          { onSuccess: () => setOpen(false) },
        ),
      )}
    >
      <p>冲销将新增反向记录并恢复相应欠款，原流水仍保留。</p>
      <label>
        冲销原因
        <textarea {...form.register("reason")} />
      </label>
      <Validation message={form.formState.errors.reason?.message} />
      <ErrorMessage error={command.error} />
      <button className="secondary-button" disabled={command.isPending}>
        确认冲销收款
      </button>
      <button
        className="quiet-button"
        type="button"
        onClick={() => setOpen(false)}
      >
        取消
      </button>
    </form>
  );
}

function ResolveTask({ orderId, task }: { orderId: string; task: Task }) {
  const command = useFinanceCommand(orderId);
  const form = useForm<z.infer<typeof reasonSchema>>({
    resolver: zodResolver(reasonSchema),
  });
  return (
    <form
      className="finance-form"
      onSubmit={form.handleSubmit((values) =>
        command.mutate({
          kind: "task",
          taskId: task.id,
          body: { expected_version: task.version, resolution: values.reason },
        }),
      )}
    >
      <strong>{task.title ?? "待审核任务"}</strong>
      {!task.content_visible && (
        <p>
          标题及备注保密，请联系管理员、经理或财务审核；完成任务前请先核实实际处理结果。
        </p>
      )}
      <label>
        处理结果
        <textarea {...form.register("reason")} />
      </label>
      <Validation message={form.formState.errors.reason?.message} />
      <ErrorMessage error={command.error} />
      <button className="secondary-button" disabled={command.isPending}>
        完成此待办
      </button>
    </form>
  );
}

function CompleteOrder({ order }: { order: SalesOrder }) {
  const command = useFinanceCommand(order.id);
  const form = useForm<z.infer<typeof completeSchema>>({
    resolver: zodResolver(completeSchema),
    defaultValues: { waiver: "" },
  });
  if (order.status === "COMPLETED")
    return <p role="status">订单已完成归档，交易与核销记录保留可追溯。</p>;
  return (
    <form
      className="finance-form"
      onSubmit={form.handleSubmit((values) =>
        command.mutate({
          kind: "complete",
          body: {
            expected_version: order.version,
            financial_waiver_reason: values.waiver || null,
          },
        }),
      )}
    >
      <h3>经理结案检查</h3>
      <p>
        后台将检查完整交付、必需文件、应收结清和未完成待办。财务豁免不会抹除欠款。
      </p>
      <label>
        财务豁免原因（无欠款请留空）
        <textarea {...form.register("waiver")} />
      </label>
      <Validation message={form.formState.errors.waiver?.message} />
      <ErrorMessage error={command.error} />
      <button className="primary-button" disabled={command.isPending}>
        检查并完成订单
      </button>
    </form>
  );
}

const statusLabels: Record<Receivable["status"], string> = {
  PENDING: "未到期",
  DUE: "今日到期",
  PARTIALLY_PAID: "部分收款",
  PAID: "已结清",
  OVERDUE: "逾期",
};

export function OrderFinance({ order }: { order: SalesOrder }) {
  const scope = useSessionScope();
  const member = useMemberContext(scope);
  const permissions = member.data?.permissions ?? [];
  const query = useOrderFinance(order.id);
  const [search, setSearch] = useState("");
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const cursor = cursors[cursors.length - 1];
  const receipts = useCustomerPayments(
    order.company_id,
    order.currency_code,
    search,
    cursor,
  );
  const searchForm = useForm<z.infer<typeof searchSchema>>({
    resolver: zodResolver(searchSchema),
    defaultValues: { query: "" },
  });
  if (query.isPending)
    return (
      <section aria-busy="true" className="finance-section">
        正在核对应收与收款…
      </section>
    );
  if (query.isError)
    return (
      <section className="finance-section">
        <ErrorMessage error={query.error} />
        <button className="secondary-button" onClick={() => query.refetch()}>
          重试财务数据
        </button>
      </section>
    );
  const data = query.data;
  const payments = receipts.data?.items ?? [];
  return (
    <section className="finance-section" aria-labelledby="finance-title">
      <p className="section-kicker">资金航线 · {order.currency_code}</p>
      <h2 id="finance-title">应收、回款与结案</h2>
      <div className="finance-installments">
        {data.receivables.map((row) => (
          <article key={row.id}>
            <p>
              {row.installment_type === "DEPOSIT" ? "定金" : "尾款"} ·{" "}
              {statusLabels[row.status]}
            </p>
            <strong>
              {row.amount} {row.currency_code}
            </strong>
            <p>
              已核销 {row.paid_amount} · 未结 {row.balance}
            </p>
            <small>
              到期 {row.due_date} · {row.receivable_number}
            </small>
          </article>
        ))}
      </div>
      {!data.receivables.length && permissions.includes("receivable.write") && (
        <Generate order={order} />
      )}
      <form
        className="finance-form"
        role="search"
        onSubmit={searchForm.handleSubmit((values) => {
          setSearch(values.query);
          setCursors([undefined]);
        })}
      >
        <label>
          查找当前客户收款
          <input
            {...searchForm.register("query")}
            placeholder="收款编号或银行流水号"
          />
        </label>
        <Validation message={searchForm.formState.errors.query?.message} />
        <button className="secondary-button">查找收款</button>
        <p>
          仅显示当前客户的 {order.currency_code} 收款，每页 20
          笔；可翻页查找历史收款后核销。
        </p>
      </form>
      <div className="finance-columns">
        {permissions.includes("payment.record") && (
          <RecordReceipt order={order} />
        )}
        {permissions.includes("payment.allocate") && (
          <Allocate
            key={`${search}:${cursor ?? "first"}`}
            order={order}
            payments={payments}
            receivables={data.receivables}
          />
        )}
      </div>
      <h3>当前客户收款流水</h3>
      {receipts.isPending && <p role="status">正在查找收款…</p>}
      <ErrorMessage error={receipts.error} />
      {receipts.isError && (
        <button className="secondary-button" onClick={() => receipts.refetch()}>
          重试收款查询
        </button>
      )}
      {receipts.isSuccess && payments.length === 0 && (
        <p>未找到收款。可清空搜索重新查找；收到款项后再记录银行流水。</p>
      )}
      {payments.map((row) => (
        <article
          className="finance-payment"
          key={row.id}
          data-payment-id={row.id}
        >
          <strong>{row.payment_number}</strong>
          <p>
            {new Date(row.received_at).toLocaleDateString("zh-CN")} ·
            银行流水号：{row.reference ?? "未填写"}
          </p>
          <p>
            {row.kind === "REVERSAL"
              ? "反向记录"
              : row.status === "REVERSED"
                ? "已冲销"
                : "收款"}{" "}
            · {row.amount} {row.currency_code} · 可用 {row.available_amount}
          </p>
          {permissions.includes("payment.reverse") &&
            row.kind === "RECEIPT" &&
            row.status === "ACTIVE" && (
              <ReverseReceipt orderId={order.id} payment={row} />
            )}
          <section aria-label="收款备注审核">
            <p>
              {row.content_visible
                ? row.notes || "未填写备注"
                : "收款备注待审核，当前不可见"}
            </p>
            <WorkTextReview
              paymentText
              recordId={row.id}
              onChanged={async () => {
                await receipts.refetch();
                await query.refetch();
              }}
            />
          </section>
        </article>
      ))}
      <nav className="queue-pagination" aria-label="收款分页">
        <button
          className="secondary-button"
          disabled={cursors.length === 1 || receipts.isFetching}
          onClick={() => setCursors((values) => values.slice(0, -1))}
        >
          上一页收款
        </button>
        <span role="status">第 {cursors.length} 页</span>
        <button
          className="secondary-button"
          disabled={
            !receipts.data?.has_more || receipts.isFetching || receipts.isError
          }
          onClick={() => {
            const next = receipts.data?.next_cursor;
            if (next) setCursors((values) => [...values, next]);
          }}
        >
          下一页收款
        </button>
      </nav>
      <h3>结案待办</h3>
      {data.tasks.map((task) => (
        <article key={task.id} data-work-task-id={task.id}>
          {permissions.includes("task.write") &&
          (task.status === "OPEN" || task.status === "IN_PROGRESS") ? (
            <ResolveTask key={task.version} orderId={order.id} task={task} />
          ) : (
            <p>
              {task.title ?? "待审核任务"} ·{" "}
              {
                {
                  OPEN: "待处理",
                  IN_PROGRESS: "处理中",
                  DONE: "已完成",
                  CANCELLED: "已取消",
                }[task.status]
              }
            </p>
          )}
          {task.content_visible && Object.keys(task.details).length > 0 && (
            <details>
              <summary>任务补充信息</summary>
              <pre className="work-content-preview">
                {JSON.stringify(task.details, null, 2)}
              </pre>
            </details>
          )}
          <WorkTextReview
            orderId={order.id}
            kind="task"
            recordId={task.id}
            onChanged={() => query.refetch()}
          />
        </article>
      ))}
      {(order.status === "COMPLETED" ||
        permissions.includes("order.complete")) && (
        <CompleteOrder order={order} />
      )}
      <h3>订单时间线</h3>
      <ol className="finance-timeline">
        {data.activities.map((activity) => (
          <li key={activity.id}>
            <time>
              {new Date(activity.occurred_at).toLocaleString("zh-CN")}
            </time>
            <p>{activity.summary ?? "正文待审核，仅授权审核人可查看。"}</p>
            <small>{activity.activity_type}</small>
            {activity.content_visible &&
              Object.keys(activity.details).length > 0 && (
                <details>
                  <summary>活动补充信息</summary>
                  <pre className="work-content-preview">
                    {JSON.stringify(activity.details, null, 2)}
                  </pre>
                </details>
              )}
            <WorkTextReview
              orderId={order.id}
              kind="activity"
              recordId={activity.id}
              onChanged={() => query.refetch()}
            />
          </li>
        ))}
      </ol>
    </section>
  );
}
