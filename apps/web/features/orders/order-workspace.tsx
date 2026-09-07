"use client";

import { OrderPageControls } from "./page-controls";
import { CursorPageControls } from "../../components/cursor-page-controls";
import { WorkTextReview } from "../finance/work-review";

import { ApiClientError } from "@trade-workbench/api-client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useRef, useState, useSyncExternalStore } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  orderCreateSchema,
  purchaseCreateSchema,
  purchaseConfirmSchema,
} from "./form-schemas";

import { sessionKeys } from "../leads/api";
import { OrderFinance } from "../finance/order-finance";
import { OrderContracts } from "../contracts/order-contracts";
import { OrderExpenses } from "../finance/order-expenses";
import { PurchaseReceiving } from "./purchase-receiving";
import { PurchaseChanges } from "./purchase-changes";
import { PurchaseFinance } from "../finance/purchase-finance";
import { sumCommitments } from "./amounts";
import { useMemberContext } from "../overview/api";
import { useSessionScope } from "../overview/session";

import {
  useConfirmSalesOrder,
  useCreatePurchaseOrder,
  useCreateSalesOrder,
  usePurchaseOrderCommand,
  usePurchaseOrders,
  useRefreshOrders,
  useSalesOrder,
  useSalesOrders,
  type PurchaseOrder,
  type SalesOrder,
} from "./api";

const sessionEvent = "trade-workbench-session-change";

const orderStatusLabels: Record<SalesOrder["status"], string> = {
  DRAFT: "草稿",
  CONFIRMED: "已确认",
  DEPOSIT_PENDING: "待收定金",
  EXECUTING: "执行中",
  READY_TO_SHIP: "待出货",
  SHIPPED: "已出运",
  COMPLETED: "已完成",
  CANCELLED: "已取消",
};

const purchaseStatusLabels: Record<PurchaseOrder["status"], string> = {
  DRAFT: "草稿",
  APPROVED: "已批准",
  SENT: "已发送",
  CONFIRMED: "供应商已确认",
  PARTIALLY_RECEIVED: "部分收货",
  RECEIVED: "已收货",
  CLOSED: "已关闭",
  CANCELLED: "已取消",
};

function loadSessionSnapshot() {
  if (typeof window === "undefined") return "";
  const organizationId = window.localStorage.getItem(
    sessionKeys.organizationId,
  );
  const accessToken = window.localStorage.getItem(sessionKeys.accessToken);
  return organizationId &&
    (accessToken || window.localStorage.getItem(sessionKeys.marker))
    ? JSON.stringify({ organizationId, accessToken })
    : "";
}

function subscribeToSession(onStoreChange: () => void) {
  window.addEventListener("storage", onStoreChange);
  window.addEventListener(sessionEvent, onStoreChange);
  return () => {
    window.removeEventListener("storage", onStoreChange);
    window.removeEventListener(sessionEvent, onStoreChange);
  };
}

function describeError(error: unknown) {
  if (error instanceof ApiClientError) {
    if (error.problem.status === 403) return "当前成员没有执行此命令的权限。";
    if (error.problem.status === 401)
      return "访问凭证已失效，请重新连接业务空间。";
    return `${error.problem.detail}（${error.problem.code}）`;
  }
  return "服务暂时不可用，请检查连接后重试。";
}

function CompassMark() {
  return (
    <svg viewBox="0 0 40 40" aria-hidden="true">
      <path d="M7 29 20 7l13 22-13 5Z" />
      <circle cx="20" cy="22" r="3" />
    </svg>
  );
}

function formatMoney(
  value: string | null | undefined,
  currency: string | null,
) {
  if (value == null || currency === null) return "未提供";
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(Number(value));
}

const connectionSchema = z.object({
  organizationId: z.uuid("请输入有效的组织 ID"),
  accessToken: z.string().min(1, "请填写隔离测试访问凭证"),
});

function ConnectionPanel() {
  const form = useForm<z.infer<typeof connectionSchema>>({
    resolver: zodResolver(connectionSchema),
    defaultValues: { organizationId: "", accessToken: "" },
  });
  const connect = form.handleSubmit((data) => {
    window.localStorage.setItem(
      sessionKeys.organizationId,
      data.organizationId,
    );
    window.localStorage.setItem(sessionKeys.accessToken, data.accessToken);
    window.dispatchEvent(new Event(sessionEvent));
  });
  return (
    <main id="main-content" className="connection-shell">
      <section
        className="connection-panel"
        aria-labelledby="order-connect-title"
      >
        <p className="section-kicker">受控访问</p>
        <h1 id="order-connect-title">连接你的业务空间</h1>
        <p>订单、采购和利润数据只在当前组织范围内读取。</p>
        <form onSubmit={connect} noValidate>
          <label htmlFor="order-organization-id">组织 ID</label>
          <input
            id="order-organization-id"
            {...form.register("organizationId")}
            required
            aria-invalid={Boolean(form.formState.errors.organizationId)}
          />
          {form.formState.errors.organizationId && (
            <p role="alert">{form.formState.errors.organizationId.message}</p>
          )}
          <label htmlFor="order-access-token">访问令牌</label>
          <textarea
            id="order-access-token"
            {...form.register("accessToken")}
            aria-invalid={Boolean(form.formState.errors.accessToken)}
            rows={4}
            required
          />
          {form.formState.errors.accessToken && (
            <p role="alert">{form.formState.errors.accessToken.message}</p>
          )}
          <button className="primary-button" type="submit">
            连接业务空间
          </button>
        </form>
      </section>
    </main>
  );
}

function CreateOrderPanel({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const mutation = useCreateSalesOrder();
  const submission = useRef<{ payload: string; key: string } | null>(null);
  const submitting = useRef(false);
  const form = useForm<z.infer<typeof orderCreateSchema>>({
    resolver: zodResolver(orderCreateSchema),
    defaultValues: {
      quotationId: "",
      depositRate: "0.3000",
      depositDueDate: "",
    },
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    void form.handleSubmit((data) => {
      if (submitting.current || mutation.isPending) return;
      const body = {
        quotation_id: data.quotationId,
        deposit_rate: data.depositRate,
        deposit_due_date: data.depositDueDate || null,
      };
      const payload = JSON.stringify(body);
      if (submission.current?.payload !== payload)
        submission.current = { payload, key: crypto.randomUUID() };
      submitting.current = true;
      mutation.mutate(
        { body, key: submission.current.key },
        {
          onSuccess: (order) => onCreated(order.id),
          onSettled: () => {
            submitting.current = false;
          },
        },
      );
    })(event);
  }
  return (
    <section className="order-form-panel" aria-labelledby="create-order-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">接受报价 → 销售订单</p>
          <h2 id="create-order-title">冻结客户承诺</h2>
        </div>
        <button
          className="quiet-button"
          type="button"
          onClick={onClose}
          disabled={mutation.isPending}
        >
          取消
        </button>
      </div>
      <form onSubmit={submit} noValidate aria-busy={mutation.isPending}>
        <p className="field-span-full">
          未收到成功响应时，订单可能已生成。保持输入不变可原样重试；修改、关闭或刷新前请先核对订单列表。
          同一报价只能生成一张订单，重复建单不会修改已存定金条件。
        </p>
        <label>
          已接受报价 ID *
          <input
            {...form.register("quotationId")}
            disabled={mutation.isPending}
            aria-invalid={Boolean(form.formState.errors.quotationId)}
            required
          />
          {form.formState.errors.quotationId && (
            <span role="alert">
              {form.formState.errors.quotationId.message}
            </span>
          )}
        </label>
        <label>
          定金比例 *
          <input
            {...form.register("depositRate")}
            disabled={mutation.isPending}
            aria-invalid={Boolean(form.formState.errors.depositRate)}
            inputMode="decimal"
            required
          />
          {form.formState.errors.depositRate && (
            <span role="alert">
              {form.formState.errors.depositRate.message}
            </span>
          )}
        </label>
        <label>
          定金到期日
          <input
            {...form.register("depositDueDate")}
            type="date"
            disabled={mutation.isPending}
            aria-invalid={Boolean(form.formState.errors.depositDueDate)}
          />
          {form.formState.errors.depositDueDate && (
            <span role="alert">
              {form.formState.errors.depositDueDate.message}
            </span>
          )}
        </label>
        {mutation.isError && (
          <p className="form-error field-span-full" role="alert">
            {describeError(mutation.error)}
          </p>
        )}
        <button className="primary-button" disabled={mutation.isPending}>
          {mutation.isPending ? "正在冻结订单…" : "从报价生成订单"}
        </button>
      </form>
    </section>
  );
}

function CreatePurchasePanel({
  order,
  onClose,
}: {
  order: SalesOrder;
  onClose: () => void;
}) {
  const mutation = useCreatePurchaseOrder();
  const submission = useRef<{
    payload: string;
    key: string;
  } | null>(null);
  const form = useForm<z.infer<typeof purchaseCreateSchema>>({
    resolver: zodResolver(purchaseCreateSchema),
    defaultValues: {
      supplierCompanyId: "",
      currencyCode: "CNY",
      exchangeRate: "1.00000000",
      lines: (order.items ?? []).map((item) => ({
        quantity: item.quantity,
        unitCost: item.unit_cost ?? "",
      })),
    },
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    void form.handleSubmit((data) => {
      if (mutation.isPending) return;
      const body = {
        sales_order_id: order.id,
        supplier_company_id: data.supplierCompanyId,
        currency_code: data.currencyCode,
        exchange_rate: data.exchangeRate,
        items: (order.items ?? []).map((item, index) => ({
          sales_order_item_id: item.id,
          quantity: data.lines[index].quantity,
          unit_cost: data.lines[index].unitCost,
        })),
      };
      const payload = JSON.stringify(body);
      const key =
        submission.current?.payload === payload
          ? submission.current.key
          : crypto.randomUUID();
      submission.current = { payload, key };
      mutation.mutate({ body, key }, { onSuccess: onClose });
    })(event);
  };
  return (
    <section className="order-form-panel" aria-labelledby="create-po-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">采购承诺</p>
          <h2 id="create-po-title">为 {order.order_number} 建采购单</h2>
        </div>
        <button
          className="quiet-button"
          type="button"
          onClick={onClose}
          disabled={mutation.isPending}
        >
          取消
        </button>
      </div>
      <form onSubmit={submit} noValidate aria-busy={mutation.isPending}>
        <label>
          供应商公司 ID *
          <input
            {...form.register("supplierCompanyId")}
            disabled={mutation.isPending}
            aria-invalid={Boolean(form.formState.errors.supplierCompanyId)}
            required
          />
          {form.formState.errors.supplierCompanyId && (
            <span role="alert">
              {form.formState.errors.supplierCompanyId.message}
            </span>
          )}
        </label>
        <label>
          采购币种 *
          <input
            {...form.register("currencyCode")}
            disabled={mutation.isPending}
            aria-invalid={Boolean(form.formState.errors.currencyCode)}
            maxLength={3}
            required
          />
          {form.formState.errors.currencyCode && (
            <span role="alert">
              {form.formState.errors.currencyCode.message}
            </span>
          )}
        </label>
        <label>
          换算到订单币种汇率 *
          <input
            {...form.register("exchangeRate")}
            disabled={mutation.isPending}
            aria-invalid={Boolean(form.formState.errors.exchangeRate)}
            inputMode="decimal"
            required
          />
          {form.formState.errors.exchangeRate && (
            <span role="alert">
              {form.formState.errors.exchangeRate.message}
            </span>
          )}
        </label>
        <fieldset
          className="purchase-lines field-span-full"
          disabled={mutation.isPending}
        >
          <legend>采购行</legend>
          {(order.items ?? []).map((item, index) => (
            <div className="purchase-line" key={item.id}>
              <strong>
                {item.sku_snapshot} · {item.description_snapshot}
              </strong>
              <label>
                采购数量（订单 {item.quantity} {item.unit_snapshot}）
                <input
                  aria-label={`${item.sku_snapshot} 采购数量`}
                  inputMode="decimal"
                  {...form.register(`lines.${index}.quantity`)}
                  aria-invalid={Boolean(
                    form.formState.errors.lines?.[index]?.quantity,
                  )}
                  required
                />
                {form.formState.errors.lines?.[index]?.quantity && (
                  <span role="alert">
                    {form.formState.errors.lines[index]?.quantity?.message}
                  </span>
                )}
              </label>
              <label>
                采购单价
                <input
                  aria-label={`${item.sku_snapshot} 采购单价`}
                  inputMode="decimal"
                  {...form.register(`lines.${index}.unitCost`)}
                  aria-invalid={Boolean(
                    form.formState.errors.lines?.[index]?.unitCost,
                  )}
                  required
                />
                {form.formState.errors.lines?.[index]?.unitCost && (
                  <span role="alert">
                    {form.formState.errors.lines[index]?.unitCost?.message}
                  </span>
                )}
              </label>
            </div>
          ))}
        </fieldset>
        {form.formState.errors.lines?.root?.message && (
          <p role="alert">{form.formState.errors.lines.root.message}</p>
        )}
        {mutation.isError && (
          <p className="form-error field-span-full" role="alert">
            {describeError(mutation.error)}
          </p>
        )}
        <button className="primary-button" disabled={mutation.isPending}>
          {mutation.isPending ? "正在建立采购承诺…" : "创建采购草稿"}
        </button>
        <p className="field-span-full">
          剩余可采购数量由服务端核验。连接中断时可保留原表单重试；修改内容或关闭表单前，请先核对采购清单。
        </p>
      </form>
    </section>
  );
}

function CommitmentStrip({
  order,
  purchaseCommitted,
  canReadCosts,
}: {
  order: SalesOrder;
  purchaseCommitted: string | null;
  canReadCosts: boolean;
}) {
  return (
    <section className="commitment-strip" aria-label="客户承诺、定金与采购承诺">
      <div>
        <span>客户订单额</span>
        <strong>{formatMoney(order.total, order.currency_code)}</strong>
      </div>
      <div>
        <span>约定定金</span>
        <strong>
          {formatMoney(order.deposit_amount, order.currency_code)}
        </strong>
        <small>{(Number(order.deposit_rate) * 100).toFixed(0)}% 收款条件</small>
      </div>
      {canReadCosts && (
        <div>
          <span>采购承诺</span>
          <strong>{formatMoney(purchaseCommitted, order.currency_code)}</strong>
          <small>已建采购单折算</small>
        </div>
      )}
    </section>
  );
}

function PurchaseCard({
  order,
  finalized,
}: {
  order: PurchaseOrder;
  finalized: boolean;
}) {
  const refresh = useRefreshOrders();
  const scope = useSessionScope();
  const member = useMemberContext(scope);
  const canWrite = member.data?.permissions.includes("procurement.write");
  const canReadCosts = member.data?.permissions.includes("profit.read");
  const canApprove =
    canReadCosts && member.data?.permissions.includes("procurement.approve");
  const command = usePurchaseOrderCommand(order.id);
  const [confirmationVersion, setConfirmationVersion] = useState<number | null>(
    null,
  );
  const form = useForm<z.infer<typeof purchaseConfirmSchema>>({
    resolver: zodResolver(purchaseConfirmSchema),
    defaultValues: { supplierReference: "", expectedDeliveryDate: "" },
  });
  const confirm = form.handleSubmit((data) => {
    if (
      !canWrite ||
      finalized ||
      command.isPending ||
      confirmationVersion === null
    )
      return;
    command.mutate(
      {
        command: "confirm",
        body: {
          expected_version: confirmationVersion,
          supplier_reference: data.supplierReference || null,
          expected_delivery_date: data.expectedDeliveryDate,
        },
      },
      { onSuccess: () => setConfirmationVersion(null) },
    );
  });
  return (
    <article className="purchase-card">
      <header>
        <div>
          <p className="manifest-code">
            PURCHASE
            {canReadCosts && order.currency_code
              ? ` / ${order.currency_code}`
              : ""}
          </p>
          <h3>{order.purchase_order_number}</h3>
        </div>
        <span className="status-chip" data-status={order.status}>
          {purchaseStatusLabels[order.status]}
        </span>
      </header>
      <dl>
        {canReadCosts && (
          <div>
            <dt>原采购额</dt>
            <dd>{formatMoney(order.total, order.currency_code)}</dd>
          </div>
        )}
        {canReadCosts && (
          <div>
            <dt>订单币种折算</dt>
            <dd>{order.total_order_currency ?? "未提供"}</dd>
          </div>
        )}
        <div>
          <dt>预计交付</dt>
          <dd>{order.expected_delivery_date || "待供应商确认"}</dd>
        </div>
      </dl>
      {!canReadCosts && (
        <p>采购金额仅管理员、经理、财务可见；可继续查看数量和交付进度。</p>
      )}
      <section aria-label="采购文本审核">
        <p>供应商确认号：{order.supplier_reference || "未填写"}</p>
        {!order.content_visible ? (
          <p>采购说明和取消正文待审核，当前不可见</p>
        ) : (
          <div>
            {(order.items ?? []).map((item) => (
              <p key={item.id}>
                {item.sku_snapshot} ·{" "}
                {item.description_snapshot || "未填写说明"}
              </p>
            ))}
            {order.status === "CANCELLED" && (
              <p>
                取消原因：{order.cancellation_reason || "未填写"}；凭据说明：
                {order.cancellation_reference || "未填写"}
              </p>
            )}
          </div>
        )}
        <WorkTextReview
          sourceKind="purchase"
          recordId={order.id}
          onChanged={refresh}
        />
      </section>
      {canReadCosts && order.status === "CANCELLED" && (
        <p>
          取消后保留金额：
          {formatMoney(order.retained_total, order.currency_code)}
        </p>
      )}
      {order.replaces_purchase_order_id && (
        <p>替代原采购单：{order.replaces_purchase_order_id}</p>
      )}
      <div className="purchase-actions">
        {canApprove && !finalized && order.status === "DRAFT" && (
          <button
            className="primary-button"
            disabled={command.isPending}
            onClick={() =>
              command.mutate({
                command: "approve",
                body: { expected_version: order.version },
              })
            }
          >
            批准采购单
          </button>
        )}
        {canWrite && !finalized && order.status === "APPROVED" && (
          <button
            className="primary-button"
            disabled={command.isPending}
            onClick={() =>
              command.mutate({
                command: "send",
                body: { expected_version: order.version },
              })
            }
          >
            记录已发送
          </button>
        )}
        {canWrite &&
          !finalized &&
          order.status === "SENT" &&
          confirmationVersion === null && (
            <button
              className="primary-button"
              onClick={() => setConfirmationVersion(order.version)}
            >
              记录供应商确认
            </button>
          )}
      </div>
      {canWrite &&
        !finalized &&
        confirmationVersion !== null &&
        order.status === "SENT" && (
          <form
            className="supplier-confirm"
            onSubmit={confirm}
            noValidate
            aria-busy={command.isPending}
          >
            <p>
              本次确认绑定打开表单时的采购版本。版本已变化时，请关闭后核对并重新打开；
              未收到响应可原样重试，不能用重复确认修改已存供应商承诺。
            </p>
            <label>
              供应商确认号
              <input
                {...form.register("supplierReference")}
                disabled={command.isPending}
                aria-invalid={Boolean(form.formState.errors.supplierReference)}
              />
              {form.formState.errors.supplierReference && (
                <span role="alert">
                  {form.formState.errors.supplierReference.message}
                </span>
              )}
            </label>
            <label>
              预计交付日 *
              <input
                {...form.register("expectedDeliveryDate")}
                type="date"
                required
                disabled={command.isPending}
                aria-invalid={Boolean(
                  form.formState.errors.expectedDeliveryDate,
                )}
              />
              {form.formState.errors.expectedDeliveryDate && (
                <span role="alert">
                  {form.formState.errors.expectedDeliveryDate.message}
                </span>
              )}
            </label>
            <button className="primary-button" disabled={command.isPending}>
              保存确认
            </button>
            <button
              type="button"
              className="quiet-button"
              disabled={command.isPending}
              onClick={() => setConfirmationVersion(null)}
            >
              取消确认
            </button>
          </form>
        )}
      {command.isError && (
        <div>
          <p className="form-error" role="alert">
            {describeError(command.error)}
          </p>
          <p>
            响应丢失可能已成功。原样重试保留上次操作、版本和输入；新的决定请先刷新核对。
          </p>
          {command.variables &&
            (command.variables.command === "approve"
              ? canApprove
              : canWrite) && (
              <button
                type="button"
                className="quiet-button"
                disabled={command.isPending}
                onClick={() =>
                  command.mutate(command.variables!, {
                    onSuccess: () => setConfirmationVersion(null),
                  })
                }
              >
                原样重试采购操作
              </button>
            )}
        </div>
      )}
      <PurchaseReceiving order={order} />
      <PurchaseChanges order={order} />
      <PurchaseFinance purchase={order} />
    </article>
  );
}

function OrderDetail({ id, connected }: { id?: string; connected: boolean }) {
  const scope = useSessionScope();
  const member = useMemberContext(scope);
  const query = useSalesOrder(id, connected);
  const purchaseOrders = usePurchaseOrders(connected && Boolean(id), id);
  const confirmOrder = useConfirmSalesOrder(id ?? "");
  const [creatingPurchase, setCreatingPurchase] = useState(false);
  if (!id)
    return (
      <section className="order-detail empty-detail">
        <p>选择一份订单，查看客户承诺、待收定金和采购占用。</p>
      </section>
    );
  if (query.isLoading)
    return (
      <section className="order-detail" aria-busy="true">
        <div className="detail-skeleton" />
        <div className="detail-skeleton short" />
      </section>
    );
  if (query.isError || !query.data)
    return (
      <section className="order-detail error-state" role="alert">
        <h2>无法读取订单</h2>
        <p>{describeError(query.error)}</p>
        <button className="secondary-button" onClick={() => query.refetch()}>
          重试
        </button>
      </section>
    );
  const order = query.data;
  const relatedPurchases =
    purchaseOrders.data?.items.filter(
      (purchase) => purchase.sales_order_id === order.id,
    ) ?? [];
  const canReadCosts = Boolean(
    member.data?.permissions.includes("profit.read"),
  );
  const purchaseCommitted =
    canReadCosts && purchaseOrders.isSuccess && !purchaseOrders.hasNextPage
      ? sumCommitments(
          relatedPurchases.map(
            (purchase) => purchase.retained_total_order_currency,
          ),
        )
      : null;
  const canCreatePurchase =
    canReadCosts &&
    member.data?.permissions.includes("procurement.write") &&
    ["CONFIRMED", "DEPOSIT_PENDING", "EXECUTING"].includes(order.status);
  if (creatingPurchase && canCreatePurchase)
    return (
      <CreatePurchasePanel
        key={order.id}
        order={order}
        onClose={() => setCreatingPurchase(false)}
      />
    );
  return (
    <section className="order-detail" aria-labelledby="order-detail-title">
      <div className="detail-heading">
        <div>
          <p className="manifest-code">ORDER / {order.currency_code}</p>
          <h2 id="order-detail-title">{order.order_number}</h2>
          <p>源自已接受报价 · {order.quotation_id}</p>
        </div>
        <span className="status-chip large" data-status={order.status}>
          {orderStatusLabels[order.status]}
        </span>
      </div>
      <CommitmentStrip
        order={order}
        purchaseCommitted={purchaseCommitted}
        canReadCosts={canReadCosts}
      />
      <OrderFinance order={order} />
      <OrderExpenses order={order} />
      <OrderContracts order={order} />
      <section aria-label="订单文本审核">
        <p>
          {order.content_visible
            ? `付款：${order.payment_terms ?? "未填写"}；交付：${order.delivery_terms ?? "未填写"}`
            : "订单说明和条款待审核，当前不可见"}
        </p>
        <WorkTextReview
          commercialKind="sales_order"
          recordId={order.id}
          onChanged={() => query.refetch()}
        />
      </section>
      <div className="order-actions" aria-label="订单与采购命令">
        {member.data?.permissions.includes("order.confirm") &&
          order.status === "DRAFT" && (
            <button
              className="primary-button"
              disabled={confirmOrder.isPending}
              onClick={() =>
                confirmOrder.mutate({ expected_version: order.version })
              }
            >
              {confirmOrder.isPending ? "正在确认…" : "经理确认订单"}
            </button>
          )}
        {canCreatePurchase && (
          <button
            className="secondary-button"
            onClick={() => setCreatingPurchase(true)}
          >
            创建采购单
          </button>
        )}
        {confirmOrder.isError && (
          <div>
            <p className="form-error" role="alert">
              {describeError(confirmOrder.error)}
            </p>
            {member.data?.permissions.includes("order.confirm") &&
              confirmOrder.variables && (
                <button
                  className="secondary-button"
                  disabled={confirmOrder.isPending}
                  onClick={() =>
                    confirmOrder.variables &&
                    confirmOrder.mutate(confirmOrder.variables)
                  }
                >
                  原样重试订单确认
                </button>
              )}
            <p>
              重试保留上次所见版本；版本冲突时请刷新核对后重新确认。关闭或刷新后先检查订单现状。
            </p>
          </div>
        )}
      </div>
      <div className="quote-table-wrap">
        {!canReadCosts && (
          <p className="empty-copy">订单成本和毛利仅管理员、经理、财务可见。</p>
        )}
        <table className="quote-table">
          <caption>接受版本冻结的销售订单行</caption>
          <thead>
            <tr>
              <th>商品</th>
              <th>数量</th>
              <th>售价</th>
              <th>销售额</th>
              {canReadCosts && <th>预计成本</th>}
              {canReadCosts && <th>毛利</th>}
            </tr>
          </thead>
          <tbody>
            {(order.items ?? []).map((item) => (
              <tr key={item.id}>
                <th scope="row">
                  <strong>{item.sku_snapshot}</strong>
                  <small>{item.description_snapshot ?? "说明待审核"}</small>
                </th>
                <td>
                  {item.quantity} {item.unit_snapshot}
                </td>
                <td>{formatMoney(item.unit_price, order.currency_code)}</td>
                <td>{formatMoney(item.line_total, order.currency_code)}</td>
                {canReadCosts && (
                  <>
                    <td>{formatMoney(item.line_cost, order.currency_code)}</td>
                    <td>
                      {formatMoney(item.line_gross_profit, order.currency_code)}
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <section
        className="purchase-ledger"
        aria-labelledby="purchase-ledger-title"
      >
        <div className="panel-heading">
          <div>
            <p className="section-kicker">供应航线</p>
            <h2 id="purchase-ledger-title">采购承诺</h2>
          </div>
          <span>已加载 {relatedPurchases.length} 份</span>
        </div>
        {purchaseOrders.isLoading && <p role="status">正在读取采购清单…</p>}
        {relatedPurchases.length ? (
          <div className="purchase-grid">
            {relatedPurchases.map((purchase) => (
              <PurchaseCard
                order={purchase}
                key={purchase.id}
                finalized={
                  order.status === "COMPLETED" || order.status === "CANCELLED"
                }
              />
            ))}
          </div>
        ) : purchaseOrders.isSuccess ? (
          <p className="empty-copy">订单确认后可建立采购单并记录供应商承诺。</p>
        ) : null}
        {purchaseOrders.hasNextPage && canReadCosts && (
          <p>采购清单尚未加载完整，暂不显示完整采购承诺合计。</p>
        )}
        <CursorPageControls query={purchaseOrders} label="采购单" />
      </section>
    </section>
  );
}

export function OrderWorkspace({
  initialOrderId,
}: {
  initialOrderId?: string;
}) {
  const router = useRouter();
  const scope = useSessionScope();
  const member = useMemberContext(scope);
  const canCreateOrder = member.data?.permissions.includes("order.write");
  const [creatingOrder, setCreatingOrder] = useState(false);
  const sessionSnapshot = useSyncExternalStore(
    subscribeToSession,
    loadSessionSnapshot,
    () => "",
  );
  const connected = Boolean(sessionSnapshot);
  const orders = useSalesOrders(connected);
  const disconnect = () => {
    window.localStorage.removeItem(sessionKeys.organizationId);
    window.localStorage.removeItem(sessionKeys.accessToken);
    window.dispatchEvent(new Event(sessionEvent));
  };
  if (!connected) return <ConnectionPanel />;
  return (
    <main id="main-content" className="workspace-shell">
      <header className="workspace-topbar">
        <Link className="brand" href="/">
          <CompassMark />
          <span>
            外贸工作台<small>Trade workbench</small>
          </span>
        </Link>
        <nav aria-label="主导航">
          <Link href="/leads">线索</Link>
          <Link href="/quotations">报价</Link>
          <Link className="active" href="/orders">
            订单
          </Link>
          <Link href="/shipments">出运</Link>
        </nav>
        <button className="quiet-button" onClick={disconnect}>
          切换空间
        </button>
      </header>
      <section className="workspace-intro order-intro">
        <div>
          <p className="section-kicker">Phase 4 · Commitment control</p>
          <h1>订单承诺舱</h1>
          <p>
            把客户承诺、定金要求与供应商采购放在同一张航图上，先看清再承诺。
          </p>
        </div>
        {canCreateOrder && (
          <button
            className="primary-button"
            onClick={() => setCreatingOrder(true)}
          >
            从已接受报价建单
          </button>
        )}
      </section>
      {member.isPending && <p role="status">正在确认订单操作权限…</p>}
      {member.isError && <p role="alert">无法确认订单操作权限，请刷新页面。</p>}
      {creatingOrder && canCreateOrder && (
        <CreateOrderPanel
          key={scope}
          onClose={() => setCreatingOrder(false)}
          onCreated={(id) => {
            setCreatingOrder(false);
            router.push(`/orders/${id}`);
          }}
        />
      )}
      <div className="order-console">
        <section className="order-manifest" aria-labelledby="order-list-title">
          <div className="list-heading">
            <div>
              <p className="section-kicker">承诺清单</p>
              <h2 id="order-list-title">销售订单</h2>
            </div>
            <span>已加载 {orders.data?.count ?? 0} 份</span>
          </div>
          {orders.isLoading && (
            <div className="lead-list-skeleton" aria-label="正在加载订单">
              <span />
              <span />
              <span />
            </div>
          )}
          {orders.isError && !orders.data && (
            <div className="list-message error-state" role="alert">
              <strong>订单清单暂时不可用</strong>
              <p>{describeError(orders.error)}</p>
            </div>
          )}
          {orders.data?.items.map((order) => (
            <Link
              className="order-row"
              href={`/orders/${order.id}`}
              data-selected={order.id === initialOrderId}
              aria-current={order.id === initialOrderId ? "page" : undefined}
              key={order.id}
            >
              <span>
                <small>{order.currency_code}</small>
                <strong>{order.order_number}</strong>
                <time dateTime={order.deposit_due_date ?? undefined}>
                  {order.deposit_due_date
                    ? `定金到期 ${order.deposit_due_date}`
                    : "未设定金到期日"}
                </time>
              </span>
              <span>
                <span className="status-chip" data-status={order.status}>
                  {orderStatusLabels[order.status]}
                </span>
                <b>{formatMoney(order.total, order.currency_code)}</b>
              </span>
            </Link>
          ))}
          {orders.data?.count === 0 && (
            <p className="list-message">
              接受报价后，在这里冻结第一份销售订单。
            </p>
          )}
          <OrderPageControls query={orders} />
        </section>
        <OrderDetail
          key={`${scope}:${initialOrderId ?? ""}`}
          id={initialOrderId}
          connected={connected}
        />
      </div>
    </main>
  );
}
