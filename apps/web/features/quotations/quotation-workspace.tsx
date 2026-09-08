"use client";
import { CursorPageControls } from "../../components/cursor-page-controls";
import { WorkTextReview } from "../finance/work-review";
import { InquirySource } from "./inquiry-source";
import { CommercialTimeline } from "../finance/commercial-timeline";

import { ApiClientError } from "@trade-workbench/api-client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useRef, useState, useSyncExternalStore } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { revisionSchema } from "./revision-schema";
import { useMemberContext } from "../overview/api";
import { useSessionScope } from "../overview/session";

import { sessionKeys } from "../leads/api";
import { CustomerReview } from "./customer-review";
import { CreateQuotePanel } from "./create-quote-panel";

import {
  useCreateInquiry,
  useCreateProduct,
  useQuotation,
  useQuotationCommand,
  useQuotations,
  useReviseQuotation,
  type Quotation,
  type QuotationCommand,
  type QuotationListItem,
  type QuotationStatus,
  type QuotationVersion,
  type InquiryCreate,
} from "./api";

const sessionEvent = "trade-workbench-session-change";
const connectionSchema = z.object({
  organizationId: z.uuid("请输入有效的组织 ID"),
  accessToken: z.string().trim().min(1, "请填写隔离测试访问凭证"),
});

const statusLabels: Record<QuotationStatus, string> = {
  DRAFT: "草稿",
  INTERNAL_REVIEW: "内部审核",
  SENT: "已发送",
  CUSTOMER_REVIEW: "客户审核",
  ACCEPTED: "已接受",
  REJECTED: "已拒绝",
  EXPIRED: "已过期",
  SUPERSEDED: "已替代",
};

const statusOptions = Object.entries(statusLabels) as [
  QuotationStatus,
  string,
][];

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

function formatMoney(value: string | null, currency: string) {
  if (value === null) return "未提供";
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(Number(value));
}

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
        aria-labelledby="quote-connection-title"
      >
        <p className="section-kicker">受控访问</p>
        <h1 id="quote-connection-title">连接你的业务空间</h1>
        <p>使用与线索舱单相同的组织和访问令牌。</p>
        <form onSubmit={connect} noValidate>
          <label htmlFor="quote-organization-id">组织 ID</label>
          <input
            id="quote-organization-id"
            {...form.register("organizationId")}
            aria-invalid={Boolean(form.formState.errors.organizationId)}
            aria-describedby="quote-organization-error"
          />
          {form.formState.errors.organizationId && (
            <p id="quote-organization-error" role="alert">
              {form.formState.errors.organizationId.message}
            </p>
          )}
          <label htmlFor="quote-access-token">访问令牌</label>
          <textarea
            id="quote-access-token"
            {...form.register("accessToken")}
            rows={4}
            aria-invalid={Boolean(form.formState.errors.accessToken)}
            aria-describedby="quote-token-error"
          />
          {form.formState.errors.accessToken && (
            <p id="quote-token-error" role="alert">
              {form.formState.errors.accessToken.message}
            </p>
          )}
          <button className="primary-button" type="submit">
            连接业务空间
          </button>
        </form>
      </section>
    </main>
  );
}

function QuoteRow({
  quote,
  selected,
}: {
  quote: QuotationListItem;
  selected: boolean;
}) {
  return (
    <Link
      className="quote-row"
      href={`/quotations/${quote.id}`}
      data-selected={selected}
      aria-current={selected ? "page" : undefined}
    >
      <span>
        <small>V{quote.version_number}</small>
        <strong>{quote.quotation_number}</strong>
        <time dateTime={quote.valid_until}>有效期至 {quote.valid_until}</time>
      </span>
      <span>
        <span className="status-chip" data-status={quote.status}>
          {statusLabels[quote.status]}
        </span>
        <b>{formatMoney(quote.total, quote.currency_code)}</b>
      </span>
    </Link>
  );
}

function ProfitRuler({ version }: { version: QuotationVersion }) {
  if (
    version.total_cost === null ||
    version.gross_profit === null ||
    version.gross_margin === null
  )
    return (
      <p className="empty-copy">成本和毛利快照未提供，暂无法展示利润分析。</p>
    );
  const total = Number(version.total);
  const cost = Number(version.total_cost);
  const costWidth =
    total > 0 ? Math.min(100, Math.max(0, (cost / total) * 100)) : 0;
  return (
    <section className="profit-ruler" aria-label="收入、成本与毛利">
      <div className="profit-ruler-head">
        <div>
          <span>报价收入</span>
          <strong>{formatMoney(version.total, version.currency_code)}</strong>
        </div>
        <div>
          <span>预计成本</span>
          <strong>
            {formatMoney(version.total_cost, version.currency_code)}
          </strong>
        </div>
        <div>
          <span>报价毛利</span>
          <strong>
            {formatMoney(version.gross_profit, version.currency_code)}
          </strong>
        </div>
      </div>
      <div className="profit-track" aria-hidden="true">
        <span style={{ width: `${costWidth}%` }} />
      </div>
      <p>
        毛利率 <b>{(Number(version.gross_margin) * 100).toFixed(2)}%</b>
        <small>基于 V{version.version_number} 冻结快照</small>
      </p>
    </section>
  );
}

const commandPermissions = {
  submit: "quotation.submit",
  approve: "quotation.approve",
  send: "quotation.send",
  accept: "quotation.accept",
  reject: "quotation.accept",
  expire: "quotation.write",
} as const satisfies Record<QuotationCommand, string>;

function commandOptions(version: QuotationVersion) {
  const options: {
    command: QuotationCommand;
    label: string;
    primary?: boolean;
  }[] = [];
  if (version.status === "DRAFT")
    options.push({ command: "submit", label: "提交审核", primary: true });
  if (version.status === "INTERNAL_REVIEW" && !version.approved_at) {
    options.push({ command: "approve", label: "经理批准", primary: true });
  }
  if (version.status === "INTERNAL_REVIEW" && version.approved_at) {
    options.push({ command: "send", label: "发送给客户", primary: true });
  }
  if (version.status === "SENT" || version.status === "CUSTOMER_REVIEW") {
    options.push(
      { command: "accept", label: "记录客户接受", primary: true },
      { command: "reject", label: "记录客户拒绝" },
    );
  }
  if (
    !["ACCEPTED", "REJECTED", "EXPIRED", "SUPERSEDED"].includes(version.status)
  ) {
    options.push({ command: "expire", label: "标记过期" });
  }
  return options;
}

function RevisionPanel({
  quote,
  onClose,
}: {
  quote: Quotation;
  onClose: () => void;
}) {
  const mutation = useReviseQuotation(quote.id);
  const submission = useRef<{ payload: string; key: string } | null>(null);
  const inFlight = useRef(false);
  const current = quote.current_version;
  const currentItems = current.items ?? [];
  const form = useForm<z.infer<typeof revisionSchema>>({
    resolver: zodResolver(revisionSchema),
    mode: "onBlur",
    defaultValues: {
      exchangeRate: current.exchange_rate,
      validUntil: current.valid_until,
      prices: currentItems.map((item) => ({ value: item.unit_price })),
    },
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    void form.handleSubmit(async (data) => {
      if (inFlight.current) return;
      const body = {
        expected_version_id: current.id,
        exchange_rate: data.exchangeRate,
        valid_until: data.validUntil,
        items: currentItems.map((item, index) => ({
          source_item_id: item.id,
          product_id: item.product_id,
          quantity: item.quantity,
          unit_price: data.prices[index].value,
          tax_amount: item.tax_amount,
          freight_amount: item.freight_amount,
        })),
      };
      const payload = JSON.stringify(body);
      if (submission.current?.payload !== payload)
        submission.current = { payload, key: crypto.randomUUID() };
      inFlight.current = true;
      try {
        await mutation.mutateAsync({ body, key: submission.current.key });
        onClose();
      } catch {
        // Preserve the opening version and retry identity after an uncertain response.
      } finally {
        inFlight.current = false;
      }
    })(event);
  };
  return (
    <section className="quote-form-panel" aria-labelledby="revision-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">不可变版本</p>
          <h2 id="revision-title">生成 V{current.version_number + 1}</h2>
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
          报价币种
          <input value={current.currency_code} readOnly />
        </label>
        <label>
          基准汇率 *
          <input
            {...form.register("exchangeRate")}
            inputMode="decimal"
            disabled={mutation.isPending}
            aria-invalid={Boolean(form.formState.errors.exchangeRate)}
            aria-describedby="revision-rate-error"
          />
        </label>
        {form.formState.errors.exchangeRate && (
          <p id="revision-rate-error" className="form-error" role="alert">
            {form.formState.errors.exchangeRate.message}
          </p>
        )}
        <label>
          新有效期 *
          <input
            {...form.register("validUntil")}
            type="date"
            disabled={mutation.isPending}
            aria-invalid={Boolean(form.formState.errors.validUntil)}
            aria-describedby="revision-date-error"
          />
        </label>
        {form.formState.errors.validUntil && (
          <p id="revision-date-error" className="form-error" role="alert">
            {form.formState.errors.validUntil.message}
          </p>
        )}
        <fieldset
          className="quote-lines field-span-full"
          disabled={mutation.isPending}
        >
          <legend>逐行调整售价</legend>
          {currentItems.map((item, index) => (
            <label key={item.id}>
              {item.sku_snapshot} · {item.description_snapshot}
              <input
                aria-label={`${item.sku_snapshot} 新单价`}
                inputMode="decimal"
                {...form.register(`prices.${index}.value`)}
                aria-invalid={Boolean(
                  form.formState.errors.prices?.[index]?.value,
                )}
                aria-describedby={`revision-price-${index}-error`}
              />
              {form.formState.errors.prices?.[index]?.value && (
                <span
                  id={`revision-price-${index}-error`}
                  className="form-error"
                  role="alert"
                >
                  {form.formState.errors.prices[index]?.value?.message}
                </span>
              )}
            </label>
          ))}
        </fieldset>
        {form.formState.errors.prices?.message && (
          <p className="form-error" role="alert">
            {form.formState.errors.prices.message}
          </p>
        )}
        <p className="field-span-full">
          保持表单打开并原样重试不会重复生成版本。关闭后重开会生成新的请求，请先核对版本账本；旧版本提交会被拒绝。
        </p>
        {mutation.isError && (
          <p className="form-error field-span-full" role="alert">
            {describeError(mutation.error)}
          </p>
        )}
        <button className="primary-button" disabled={mutation.isPending}>
          {mutation.isPending
            ? "正在冻结新版本…"
            : `生成 V${current.version_number + 1}`}
        </button>
      </form>
    </section>
  );
}

function QuoteDetail({ id, connected }: { id?: string; connected: boolean }) {
  const member = useMemberContext(useSessionScope());
  const permissions = member.data?.permissions ?? [];
  const canReadCosts = permissions.includes("profit.read");
  const query = useQuotation(id, connected);
  const command = useQuotationCommand(id ?? "");
  const [revisionSource, setRevisionSource] = useState<Quotation | null>(null);
  if (!id)
    return (
      <section className="quote-detail empty-detail">
        <p>选择一份报价，查看冻结快照、利润尺与审核轨迹。</p>
      </section>
    );
  if (query.isLoading)
    return (
      <section className="quote-detail" aria-busy="true">
        <div className="detail-skeleton" />
        <div className="detail-skeleton short" />
      </section>
    );
  if (query.isError || !query.data) {
    return (
      <section className="quote-detail error-state" role="alert">
        <h2>无法读取报价</h2>
        <p>{describeError(query.error)}</p>
        <button className="secondary-button" onClick={() => query.refetch()}>
          重试
        </button>
      </section>
    );
  }
  const quote = query.data;
  const current = quote.current_version;
  const currentItems = current.items ?? [];
  if (
    revisionSource &&
    permissions.includes("quotation.write") &&
    current.status !== "ACCEPTED"
  )
    return (
      <RevisionPanel
        key={revisionSource.current_version.id}
        quote={revisionSource}
        onClose={() => setRevisionSource(null)}
      />
    );
  return (
    <section className="quote-detail" aria-labelledby="quote-detail-title">
      <div className="detail-heading">
        <div>
          <p className="manifest-code">QUOTE / V{current.version_number}</p>
          <h2 id="quote-detail-title">{quote.quotation_number}</h2>
          <p>
            {current.currency_code} · 有效期至 {current.valid_until}
          </p>
        </div>
        <span className="status-chip large" data-status={current.status}>
          {statusLabels[current.status]}
        </span>
      </div>
      {canReadCosts ? (
        <ProfitRuler version={current} />
      ) : (
        <p className="empty-copy">报价成本和毛利仅管理员、经理、财务可见。</p>
      )}
      <InquirySource id={quote.inquiry_id} />
      <section aria-label="报价文本审核">
        <p>
          {current.content_visible
            ? `付款：${current.payment_terms ?? "未填写"}；交付：${current.delivery_terms ?? "未填写"}`
            : "报价说明和条款待审核，当前不可见"}
        </p>
        <WorkTextReview
          commercialKind="quotation_version"
          recordId={current.id}
          onChanged={() => query.refetch()}
        />
        <details>
          <summary>历史版本文本审核</summary>
          {quote.versions
            .filter((version) => version.id !== current.id)
            .map((version) => (
              <section key={version.id}>
                <h4>V{version.version_number}</h4>
                <p>
                  {version.content_visible
                    ? `付款：${version.payment_terms ?? "未填写"}；交付：${version.delivery_terms ?? "未填写"}`
                    : "本版说明和条款待审核"}
                </p>
                {version.items?.map((item) => (
                  <p key={item.id}>
                    {item.sku_snapshot} ·{" "}
                    {item.description_snapshot ?? "说明待审核"}
                  </p>
                ))}
                <WorkTextReview
                  commercialKind="quotation_version"
                  recordId={version.id}
                  onChanged={() => query.refetch()}
                />
              </section>
            ))}
        </details>
      </section>
      {current.status === "SENT" && (
        <CustomerReview id={quote.id} versionId={current.id} />
      )}
      <div className="quote-actions" aria-label="报价命令">
        <div>
          {commandOptions(current)
            .filter((option) =>
              permissions.includes(commandPermissions[option.command]),
            )
            .map((option) => (
              <button
                key={option.command}
                className={
                  option.primary ? "primary-button" : "secondary-button"
                }
                disabled={command.isPending}
                onClick={() =>
                  command.mutate({
                    command: option.command,
                    body: {
                      expected_version_id: current.id,
                      expected_version: current.version,
                    },
                  })
                }
              >
                {option.label}
              </button>
            ))}
          {current.status !== "ACCEPTED" &&
            permissions.includes("quotation.write") && (
              <button
                className="quiet-button"
                disabled={command.isPending}
                onClick={() => setRevisionSource(quote)}
              >
                生成修订版
              </button>
            )}
        </div>
        {command.isError && (
          <div>
            <p className="form-error" role="alert">
              {describeError(command.error)}
            </p>
            <p>
              原样重试保留原操作和版本，不会改为操作后来出现的新版本。版本冲突时请刷新核对。
            </p>
            {command.variables &&
              permissions.includes(
                commandPermissions[command.variables.command],
              ) && (
                <button
                  className="secondary-button"
                  onClick={() => command.mutate(command.variables!)}
                >
                  原样重试上次报价操作
                </button>
              )}
          </div>
        )}
      </div>
      <div className="quote-table-wrap">
        <table className="quote-table">
          <caption>V{current.version_number} 商业快照</caption>
          <thead>
            <tr>
              <th>商品</th>
              <th>数量</th>
              <th>售价</th>
              <th>销售额</th>
              {canReadCosts && <th>成本</th>}
              {canReadCosts && <th>毛利</th>}
            </tr>
          </thead>
          <tbody>
            {currentItems.map((item) => (
              <tr key={item.id}>
                <th scope="row">
                  <strong>{item.sku_snapshot}</strong>
                  <small>{item.description_snapshot ?? "说明待审核"}</small>
                </th>
                <td>
                  {item.quantity} {item.unit_snapshot}
                </td>
                <td>{formatMoney(item.unit_price, current.currency_code)}</td>
                <td>{formatMoney(item.line_total, current.currency_code)}</td>
                {canReadCosts && (
                  <td>
                    <span>
                      {formatMoney(item.line_cost, current.currency_code)}
                    </span>
                    <small>
                      {item.unit_cost} {item.cost_currency} ×{" "}
                      {item.cost_exchange_rate}
                    </small>
                  </td>
                )}
                {canReadCosts && (
                  <td>
                    {formatMoney(item.line_gross_profit, current.currency_code)}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <dl className="quote-terms">
        <div>
          <dt>付款条件</dt>
          <dd>{current.payment_terms || "—"}</dd>
        </div>
        <div>
          <dt>交付条款</dt>
          <dd>{current.delivery_terms || "—"}</dd>
        </div>
        <div>
          <dt>基准汇率</dt>
          <dd>
            1 {current.currency_code} = {current.exchange_rate}{" "}
            {current.base_currency_code}
          </dd>
        </div>
        <div>
          <dt>经理批准</dt>
          <dd>
            {current.approved_at
              ? `已批准 · ${new Date(current.approved_at).toLocaleString("zh-CN")}`
              : "待批准"}
          </dd>
        </div>
      </dl>
      <section
        className="version-ledger"
        aria-labelledby="version-ledger-title"
      >
        <div className="timeline-heading">
          <p className="section-kicker" id="version-ledger-title">
            版本账本
          </p>
          <span>{quote.versions.length} 个快照</span>
        </div>
        <ol>
          {quote.versions.map((version) => (
            <li key={version.id}>
              <strong>V{version.version_number}</strong>
              <span className="status-chip" data-status={version.status}>
                {statusLabels[version.status]}
              </span>
              <span>{formatMoney(version.total, version.currency_code)}</span>
            </li>
          ))}
        </ol>
      </section>
      <CommercialTimeline
        subject="quotation"
        id={quote.id}
        revision={`${current.id}:${current.version}`}
      />
    </section>
  );
}

const productSchema = z.object({
  sku: z.string().trim().min(1, "请填写 SKU").max(80),
  name: z.string().trim().min(1, "请填写产品名称").max(240),
  description: z.string().max(2000, "说明最多 2000 字"),
  unit: z.string().trim().min(1, "请填写单位").max(32),
  cost: z
    .string()
    .regex(/^\d{1,14}(\.\d{1,4})?$/, "请输入非负成本，最多四位小数"),
  currency: z
    .string()
    .trim()
    .regex(/^[A-Za-z]{3}$/, "请输入三位币种代码"),
});
const inquirySchema = z.object({
  opportunityId: z.uuid("请输入有效的商机 ID"),
  companyId: z.uuid("请输入有效的客户公司 ID"),
  reference: z.string().max(120, "参考号最多 120 字"),
  description: z.string().trim().min(1, "请填写询盘内容"),
});
function PreparationPanel({
  onClose,
  canProduct,
  canInquiry,
}: {
  onClose: () => void;
  canProduct: boolean;
  canInquiry: boolean;
}) {
  const product = useCreateProduct();
  const inquiry = useCreateInquiry();
  const inquiryRetry = useRef<{
    payload: string;
    key: string;
    body: InquiryCreate;
  } | null>(null);
  const inquirySubmitting = useRef(false);
  const productForm = useForm<z.infer<typeof productSchema>>({
    resolver: zodResolver(productSchema),
    mode: "onBlur",
    defaultValues: {
      sku: "",
      name: "",
      description: "",
      unit: "set",
      cost: "",
      currency: "CNY",
    },
  });
  const inquiryForm = useForm<z.infer<typeof inquirySchema>>({
    resolver: zodResolver(inquirySchema),
    mode: "onBlur",
    defaultValues: {
      opportunityId: "",
      companyId: "",
      reference: "",
      description: "",
    },
  });
  const [receipt, setReceipt] = useState<string>();
  return (
    <section className="prep-panel" aria-labelledby="prep-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">开价准备</p>
          <h2 id="prep-title">产品与询盘</h2>
        </div>
        <button
          className="quiet-button"
          onClick={onClose}
          disabled={product.isPending || inquiry.isPending}
        >
          关闭
        </button>
      </div>
      <div className="prep-grid">
        {canProduct && (
          <form
            noValidate
            aria-busy={product.isPending}
            onSubmit={productForm.handleSubmit((data) => {
              if (product.isPending) return;
              product.mutate(
                {
                  sku: data.sku,
                  name: data.name,
                  description: data.description || null,
                  unit: data.unit,
                  standard_cost: data.cost,
                  cost_currency: data.currency.toUpperCase(),
                },
                {
                  onSuccess: (result) => setReceipt(`产品已建立：${result.id}`),
                },
              );
            })}
          >
            <h3>建立产品</h3>
            {(
              [
                { key: "sku", label: "SKU *" },
                { key: "name", label: "产品名称 *" },
                { key: "unit", label: "单位 *" },
                { key: "cost", label: "标准成本 *" },
                { key: "currency", label: "成本币种 *" },
              ] as const
            ).map(({ key, label }) => (
              <label key={key}>
                {label}
                <input
                  {...productForm.register(key)}
                  aria-label={label}
                  disabled={product.isPending}
                  inputMode={key === "cost" ? "decimal" : undefined}
                  aria-invalid={Boolean(productForm.formState.errors[key])}
                  aria-describedby={`product-${key}-error`}
                />
                {productForm.formState.errors[key] && (
                  <span
                    id={`product-${key}-error`}
                    role="alert"
                    className="form-error"
                  >
                    {productForm.formState.errors[key]?.message}
                  </span>
                )}
              </label>
            ))}
            <label>
              产品说明（默认保密）
              <textarea
                {...productForm.register("description")}
                disabled={product.isPending}
              />
            </label>
            {productForm.formState.errors.description && (
              <p role="alert">
                {productForm.formState.errors.description.message}
              </p>
            )}
            <p>名称、SKU 和单位用于识别，请勿填写内部成本或利润。</p>
            <button className="secondary-button" disabled={product.isPending}>
              {product.isPending ? "正在保存…" : "保存产品"}
            </button>
            {product.isError && (
              <p role="alert">{describeError(product.error)}</p>
            )}
          </form>
        )}
        {canInquiry && (
          <form
            noValidate
            aria-busy={inquiry.isPending}
            onSubmit={(event) => {
              void inquiryForm.handleSubmit(async (data) => {
                if (inquirySubmitting.current) return;
                inquirySubmitting.current = true;
                const input = {
                  opportunity_id: data.opportunityId,
                  company_id: data.companyId,
                  customer_reference: data.reference || null,
                  description: data.description,
                };
                const payload = JSON.stringify(input);
                if (inquiryRetry.current?.payload !== payload) {
                  inquiryRetry.current = {
                    payload,
                    key: crypto.randomUUID(),
                    body: { ...input, received_at: new Date().toISOString() },
                  };
                }
                try {
                  const result = await inquiry.mutateAsync(
                    inquiryRetry.current,
                  );
                  setReceipt(`询盘已建立：${result.id}`);
                } catch {
                  // Preserve both the command key and first-submission timestamp for retry.
                } finally {
                  inquirySubmitting.current = false;
                }
              })(event);
            }}
          >
            <h3>登记询盘</h3>
            {(
              [
                { key: "opportunityId", label: "商机 ID *" },
                { key: "companyId", label: "客户公司 ID *" },
                { key: "reference", label: "客户参考号" },
              ] as const
            ).map(({ key, label }) => (
              <label key={key}>
                {label}
                <input
                  {...inquiryForm.register(key)}
                  aria-label={label}
                  disabled={inquiry.isPending}
                  aria-invalid={Boolean(inquiryForm.formState.errors[key])}
                  aria-describedby={`inquiry-${key}-error`}
                />
                {inquiryForm.formState.errors[key] && (
                  <span
                    id={`inquiry-${key}-error`}
                    role="alert"
                    className="form-error"
                  >
                    {inquiryForm.formState.errors[key]?.message}
                  </span>
                )}
              </label>
            ))}
            <label>
              询盘内容 *
              <textarea
                {...inquiryForm.register("description")}
                aria-label="询盘内容 *"
                rows={3}
                disabled={inquiry.isPending}
                aria-invalid={Boolean(inquiryForm.formState.errors.description)}
                aria-describedby="inquiry-description-error"
              />
            </label>
            {inquiryForm.formState.errors.description && (
              <p
                id="inquiry-description-error"
                role="alert"
                className="form-error"
              >
                {inquiryForm.formState.errors.description.message}
              </p>
            )}
            <button className="secondary-button" disabled={inquiry.isPending}>
              {inquiry.isPending ? "正在保存…" : "保存询盘"}
            </button>
            {inquiry.isError && (
              <p role="alert">{describeError(inquiry.error)}</p>
            )}
            <p>
              结果未确认时保持输入不变重试，可找回原询盘。修改输入视为新登记；关闭或刷新后请先核对已有询盘。
            </p>
          </form>
        )}
      </div>
      {receipt && (
        <p className="prep-receipt" aria-live="polite">
          {receipt}
        </p>
      )}
    </section>
  );
}

export function QuotationWorkspace({
  initialQuotationId,
}: {
  initialQuotationId?: string;
}) {
  const router = useRouter();
  const scope = useSessionScope();
  const member = useMemberContext(scope);
  const permissions = member.data?.permissions ?? [];
  const canCreate = permissions.includes("quotation.write");
  const canProduct =
    permissions.includes("product.write") &&
    permissions.includes("profit.read");
  const canInquiry = permissions.includes("inquiry.write");
  const [status, setStatus] = useState<"" | QuotationStatus>("");
  const [panel, setPanel] = useState<"quote" | "prep" | null>(null);
  const sessionSnapshot = useSyncExternalStore(
    subscribeToSession,
    loadSessionSnapshot,
    () => "",
  );
  const connected = Boolean(sessionSnapshot);
  const quotations = useQuotations(status, connected);
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
          <Link className="active" href="/quotations">
            报价
          </Link>
          <Link href="/orders">订单</Link>
          <Link href="/shipments">出运</Link>
        </nav>
        <button className="quiet-button" onClick={disconnect}>
          切换空间
        </button>
      </header>
      <section className="workspace-intro quote-intro">
        <div>
          <p className="section-kicker">Phase 3 · Margin control</p>
          <h1>报价驾驶台</h1>
          <p>每次改价都形成独立快照；成本、汇率与毛利沿审核航线留下凭证。</p>
        </div>
        <div className="intro-actions">
          {(canProduct || canInquiry) && (
            <button
              className="secondary-button"
              onClick={() => setPanel("prep")}
            >
              准备产品与询盘
            </button>
          )}
          {canCreate && (
            <button
              className="primary-button"
              onClick={() => setPanel("quote")}
            >
              创建报价 V1
            </button>
          )}
        </div>
      </section>
      {panel === "prep" && (canProduct || canInquiry) && (
        <PreparationPanel
          key={scope}
          canProduct={canProduct}
          canInquiry={canInquiry}
          onClose={() => setPanel(null)}
        />
      )}
      {panel === "quote" && canCreate && (
        <CreateQuotePanel
          canReadCosts={permissions.includes("profit.read")}
          key={scope}
          onClose={() => setPanel(null)}
          onCreated={(id) => {
            setPanel(null);
            router.push(`/quotations/${id}`);
          }}
        />
      )}
      <div className="quote-console">
        <section className="quote-manifest" aria-labelledby="quote-list-title">
          <div className="list-heading">
            <div>
              <p className="section-kicker">审核航线</p>
              <h2 id="quote-list-title">报价队列</h2>
            </div>
            <span>已加载 {quotations.data?.count ?? 0} 份</span>
          </div>
          <div className="quote-filter">
            <label htmlFor="quote-status">筛选报价状态</label>
            <select
              id="quote-status"
              value={status}
              onChange={(event) =>
                setStatus(event.target.value as "" | QuotationStatus)
              }
            >
              <option value="">全部状态</option>
              {statusOptions.map(([value, label]) => (
                <option value={value} key={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          {quotations.isLoading && (
            <div className="lead-list-skeleton" aria-label="正在加载报价">
              <span />
              <span />
              <span />
            </div>
          )}
          {quotations.isError && !quotations.data && (
            <div className="list-message error-state" role="alert">
              <strong>报价队列未能抵达</strong>
              <p>{describeError(quotations.error)}</p>
              <button
                className="secondary-button"
                onClick={() => quotations.refetch()}
              >
                重试
              </button>
            </div>
          )}
          {quotations.data?.items.length === 0 && (
            <div className="list-message">
              <strong>暂无报价</strong>
              <p>先准备产品与询盘，再创建第一份可复算报价。</p>
              {canCreate && (
                <button
                  className="secondary-button"
                  onClick={() => setPanel("quote")}
                >
                  创建报价 V1
                </button>
              )}
            </div>
          )}
          {quotations.data?.items.map((quote) => (
            <QuoteRow
              quote={quote}
              selected={quote.id === initialQuotationId}
              key={quote.id}
            />
          ))}
          <CursorPageControls query={quotations} label="报价" />
        </section>
        <QuoteDetail
          key={`${scope}:${initialQuotationId}`}
          id={initialQuotationId}
          connected={connected}
        />
      </div>
    </main>
  );
}
