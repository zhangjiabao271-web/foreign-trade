"use client";

import { WorkTextReview } from "../finance/work-review";
import { useMemberContext } from "../overview/api";
import { useSessionScope } from "../overview/session";

import { zodResolver } from "@hookform/resolvers/zod";
import { ApiClientError } from "@trade-workbench/api-client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, useSyncExternalStore } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  sessionKeys,
  useConvertLead,
  useCreateLead,
  useLead,
  useLeadCommand,
  useLeads,
  type Lead,
  type LeadCommand,
  type LeadStatus,
} from "./api";

const sessionSchema = z.object({
  organizationId: z.uuid("请输入有效的组织 ID"),
  accessToken: z.string().min(16, "访问令牌不完整"),
});

const leadSchema = z.object({
  company_name: z.string().trim().min(1, "请输入公司名称").max(240),
  contact_name: z.string().trim().max(200).optional(),
  email: z.union([z.literal(""), z.email("请输入有效邮箱")]),
  phone: z.string().trim().max(80).optional(),
  country_code: z
    .union([z.literal(""), z.string().trim().length(2, "请输入两位国家代码")])
    .transform((value) => value.toUpperCase()),
  source: z.string().trim().max(120).optional(),
  notes: z.string().trim().optional(),
});

type SessionValues = z.infer<typeof sessionSchema>;
type LeadFormValues = z.input<typeof leadSchema>;

const statuses: { value: "" | LeadStatus; label: string }[] = [
  { value: "", label: "全部状态" },
  { value: "NEW", label: "待判定" },
  { value: "QUALIFIED", label: "已确认" },
  { value: "CONTACTED", label: "已联系" },
  { value: "RESPONDED", label: "已回复" },
  { value: "NO_RESPONSE", label: "未回复" },
  { value: "CONVERTED", label: "已转换" },
  { value: "DISQUALIFIED", label: "已排除" },
];

const statusLabels = Object.fromEntries(
  statuses
    .filter((status) => status.value)
    .map((status) => [status.value, status.label]),
) as Record<LeadStatus, string>;

const commandMap: Partial<
  Record<LeadStatus, { command: LeadCommand; label: string }[]>
> = {
  NEW: [
    { command: "qualify", label: "确认有效" },
    { command: "disqualify", label: "排除线索" },
  ],
  QUALIFIED: [{ command: "contact", label: "记录已联系" }],
  CONTACTED: [
    { command: "respond", label: "记录客户回复" },
    { command: "no-response", label: "标记未回复" },
  ],
  NO_RESPONSE: [{ command: "contact", label: "再次联系" }],
};

const sessionEvent = "trade-workbench-session-change";

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
    if (error.problem.status === 403) {
      return "当前成员没有执行此操作的权限。请切换角色或联系组织管理员。";
    }
    if (error.problem.status === 401) {
      return "访问凭证已失效，请重新连接业务空间。";
    }
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

function LeadRow({ lead, selected }: { lead: Lead; selected: boolean }) {
  return (
    <Link
      className="lead-row"
      data-selected={selected}
      href={`/leads/${lead.id}`}
      aria-current={selected ? "page" : undefined}
    >
      <span className="lead-row-main">
        <strong>{lead.company_name}</strong>
        <small>{lead.contact_name || "联系人待补充"}</small>
      </span>
      <span className="lead-row-meta">
        <span className="status-chip" data-status={lead.status}>
          {statusLabels[lead.status]}
        </span>
        <time dateTime={lead.created_at}>
          {new Intl.DateTimeFormat("zh-CN", {
            month: "2-digit",
            day: "2-digit",
          }).format(new Date(lead.created_at))}
        </time>
      </span>
    </Link>
  );
}

function ConnectionPanel({
  onConnected,
}: {
  onConnected: (session: SessionValues) => void;
}) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<SessionValues>({ resolver: zodResolver(sessionSchema) });
  return (
    <section className="connection-panel" aria-labelledby="connection-title">
      <p className="section-kicker">受控访问</p>
      <h1 id="connection-title">连接你的业务空间</h1>
      <p>当前施工环境尚未绑定正式登录服务。连接信息仅保存在本浏览器中。</p>
      <form onSubmit={handleSubmit(onConnected)} noValidate>
        <label htmlFor="organization-id">组织 ID</label>
        <input
          id="organization-id"
          autoComplete="off"
          {...register("organizationId")}
        />
        {errors.organizationId && (
          <span role="alert">{errors.organizationId.message}</span>
        )}
        <label htmlFor="access-token">访问令牌</label>
        <textarea id="access-token" rows={4} {...register("accessToken")} />
        {errors.accessToken && (
          <span role="alert">{errors.accessToken.message}</span>
        )}
        <button className="primary-button" type="submit">
          连接业务空间
        </button>
      </form>
    </section>
  );
}

function CreateLeadPanel({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const mutation = useCreateLead();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LeadFormValues>({
    resolver: zodResolver(leadSchema),
    defaultValues: { email: "", country_code: "" },
  });
  const submit = handleSubmit(async (values) => {
    const parsed = leadSchema.parse(values);
    const lead = await mutation.mutateAsync({
      ...parsed,
      contact_name: parsed.contact_name || undefined,
      email: parsed.email || undefined,
      phone: parsed.phone || undefined,
      country_code: parsed.country_code || undefined,
      source: parsed.source || undefined,
      notes: parsed.notes || undefined,
    });
    onCreated(lead.id);
  });
  return (
    <section className="lead-form-panel" aria-labelledby="new-lead-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">新舱单</p>
          <h2 id="new-lead-title">登记潜在客户</h2>
        </div>
        <button className="quiet-button" type="button" onClick={onClose}>
          取消
        </button>
      </div>
      <form onSubmit={submit} noValidate>
        <div className="field-span-two">
          <label htmlFor="company-name">公司名称 *</label>
          <input id="company-name" autoFocus {...register("company_name")} />
          {errors.company_name && (
            <span role="alert">{errors.company_name.message}</span>
          )}
        </div>
        <div>
          <label htmlFor="contact-name">联系人</label>
          <input
            id="contact-name"
            autoComplete="name"
            {...register("contact_name")}
          />
        </div>
        <div>
          <label htmlFor="lead-email">邮箱</label>
          <input
            id="lead-email"
            type="email"
            autoComplete="email"
            {...register("email")}
          />
          {errors.email && <span role="alert">{errors.email.message}</span>}
        </div>
        <div>
          <label htmlFor="lead-phone">电话</label>
          <input
            id="lead-phone"
            type="tel"
            autoComplete="tel"
            {...register("phone")}
          />
        </div>
        <div>
          <label htmlFor="country-code">国家代码</label>
          <input
            id="country-code"
            placeholder="CN"
            {...register("country_code")}
          />
          {errors.country_code && (
            <span role="alert">{errors.country_code.message}</span>
          )}
        </div>
        <div>
          <label htmlFor="lead-source">来源</label>
          <input
            id="lead-source"
            placeholder="展会、转介绍、官网…"
            {...register("source")}
          />
        </div>
        <div className="field-span-two">
          <label htmlFor="lead-notes">背景记录</label>
          <textarea id="lead-notes" rows={3} {...register("notes")} />
        </div>
        {mutation.isError && (
          <p className="form-error" role="alert">
            {describeError(mutation.error)}
          </p>
        )}
        <div className="form-actions field-span-two">
          <button
            className="primary-button"
            type="submit"
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "正在登记…" : "登记线索"}
          </button>
        </div>
      </form>
    </section>
  );
}

function DetailPanel({
  leadId,
  connected,
  writable,
  convertible,
}: {
  leadId?: string;
  connected: boolean;
  writable: boolean;
  convertible: boolean;
}) {
  const query = useLead(leadId, connected);
  const commandMutation = useLeadCommand(leadId ?? "");
  const convertMutation = useConvertLead(leadId ?? "");
  if (!leadId) {
    return (
      <section className="lead-detail empty-detail">
        <p>从左侧选择一条线索，查看航线与下一动作。</p>
      </section>
    );
  }
  if (query.isLoading) {
    return (
      <section className="lead-detail" aria-busy="true">
        <div className="detail-skeleton" />
        <div className="detail-skeleton short" />
      </section>
    );
  }
  if (query.isError || !query.data) {
    return (
      <section className="lead-detail error-state" role="alert">
        <h2>无法读取线索</h2>
        <p>{describeError(query.error)}</p>
        <button className="secondary-button" onClick={() => query.refetch()}>
          重试
        </button>
      </section>
    );
  }
  const lead = query.data;
  const actions = writable ? (commandMap[lead.status] ?? []) : [];
  const pending = commandMutation.isPending || convertMutation.isPending;
  const error = commandMutation.error ?? convertMutation.error;
  return (
    <section className="lead-detail" aria-labelledby="lead-detail-title">
      <div className="detail-heading">
        <div>
          <p className="manifest-code">
            LEAD / {lead.id.slice(0, 8).toUpperCase()}
          </p>
          <h2 id="lead-detail-title">{lead.company_name}</h2>
          <p>
            {lead.contact_name || "联系人待补充"} ·{" "}
            {lead.country_code || "地区待补充"}
          </p>
        </div>
        <span className="status-chip large" data-status={lead.status}>
          {statusLabels[lead.status]}
        </span>
      </div>
      <dl className="lead-facts">
        <div>
          <dt>邮箱</dt>
          <dd>{lead.email || "—"}</dd>
        </div>
        <div>
          <dt>电话</dt>
          <dd>{lead.phone || "—"}</dd>
        </div>
        <div>
          <dt>来源</dt>
          <dd>
            {lead.content_visible ? lead.source || "—" : "保密，待审核后开放"}
          </dd>
        </div>
        <div>
          <dt>当前版本</dt>
          <dd>v{lead.version}</dd>
        </div>
      </dl>
      <section className="finance-section" aria-label="线索备注审核">
        <h2>线索备注</h2>
        <p className="work-content-preview">
          {lead.content_visible
            ? lead.notes || "未填写备注"
            : "保密，待审核后开放"}
        </p>
        <WorkTextReview
          crmKind="lead"
          recordId={leadId}
          onChanged={() => query.refetch()}
        />
      </section>
      <div className="route-actions" aria-label="可执行动作">
        <p>下一动作</p>
        <div>
          {actions.map((action) => (
            <button
              key={action.command}
              className="secondary-button"
              disabled={pending}
              onClick={() => commandMutation.mutate(action.command)}
            >
              {action.label}
            </button>
          ))}
          {convertible && lead.status === "RESPONDED" && (
            <button
              className="primary-button"
              disabled={pending}
              onClick={() => convertMutation.mutate()}
            >
              {convertMutation.isPending ? "正在转换…" : "转换为客户与商机"}
            </button>
          )}
          {!writable && !convertible && <span>当前权限不允许修改线索。</span>}
          {writable && actions.length === 0 && lead.status !== "RESPONDED" && (
            <span>当前阶段没有待执行命令。</span>
          )}
        </div>
        {error && (
          <p className="form-error" role="alert">
            {describeError(error)}
          </p>
        )}
      </div>
      {lead.status === "CONVERTED" && (
        <div className="conversion-receipt">
          <strong>转换凭证已建立</strong>
          <span>Company {lead.converted_company_id?.slice(0, 8)}</span>
          <span>Opportunity {lead.converted_opportunity_id?.slice(0, 8)}</span>
        </div>
      )}
      <div className="timeline-heading">
        <p className="section-kicker">统一时间线</p>
        <span>{lead.activities.length} 条记录</span>
      </div>
      {lead.activities.length ? (
        <ol className="activity-timeline">
          {lead.activities.map((activity) => (
            <li key={activity.id}>
              <span aria-hidden="true" />
              <div>
                <strong>{activity.summary ?? "保密活动：待审核后开放"}</strong>
                <WorkTextReview
                  subjectType="lead"
                  subjectId={leadId}
                  recordId={activity.id}
                  onChanged={() => query.refetch()}
                />
                <time dateTime={activity.occurred_at}>
                  {new Intl.DateTimeFormat("zh-CN", {
                    dateStyle: "medium",
                    timeStyle: "short",
                  }).format(new Date(activity.occurred_at))}
                </time>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="empty-copy">这条线索还没有活动记录。</p>
      )}
    </section>
  );
}

export function LeadWorkspace({ initialLeadId }: { initialLeadId?: string }) {
  const router = useRouter();
  const scope = useSessionScope();
  const member = useMemberContext(scope);
  const writable =
    member.isSuccess && member.data.permissions.includes("lead.write");
  const convertible =
    member.isSuccess && member.data.permissions.includes("lead.convert");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"" | LeadStatus>("");
  const [creating, setCreating] = useState(false);
  const sessionSnapshot = useSyncExternalStore(
    subscribeToSession,
    loadSessionSnapshot,
    () => "",
  );
  const session = useMemo(
    () =>
      sessionSnapshot
        ? (JSON.parse(sessionSnapshot) as SessionValues)
        : undefined,
    [sessionSnapshot],
  );
  const filters = useMemo(
    () => ({ status: status || undefined, query: query.trim() || undefined }),
    [query, status],
  );
  const leads = useLeads(filters, Boolean(session));
  const connect = (values: SessionValues) => {
    window.localStorage.setItem(
      sessionKeys.organizationId,
      values.organizationId,
    );
    window.localStorage.setItem(sessionKeys.accessToken, values.accessToken);
    window.dispatchEvent(new Event(sessionEvent));
  };
  const disconnect = () => {
    window.localStorage.removeItem(sessionKeys.organizationId);
    window.localStorage.removeItem(sessionKeys.accessToken);
    window.dispatchEvent(new Event(sessionEvent));
  };
  if (!session)
    return (
      <main id="main-content" className="connection-shell">
        <ConnectionPanel onConnected={connect} />
      </main>
    );
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
          <Link className="active" href="/leads">
            线索
          </Link>
          <Link href="/quotations">报价</Link>
          <Link href="/orders">订单</Link>
          <Link href="/shipments">出运</Link>
        </nav>
        <button className="quiet-button" type="button" onClick={disconnect}>
          切换空间
        </button>
      </header>
      <section className="workspace-intro">
        <div>
          <p className="section-kicker">Phase 2 · Lead manifest</p>
          <h1>线索舱单</h1>
          <p>把每位潜在客户沿可审计航线推进到客户档案与商机。</p>
        </div>
        {writable && (
          <button
            className="primary-button"
            type="button"
            onClick={() => setCreating(true)}
          >
            登记新线索
          </button>
        )}
      </section>
      {member.isPending && <p role="status">正在确认线索操作权限…</p>}
      {member.isError && (
        <p role="alert">无法确认线索操作权限，请刷新后重试。</p>
      )}
      {creating && writable && (
        <CreateLeadPanel
          onClose={() => setCreating(false)}
          onCreated={(id) => {
            setCreating(false);
            router.push(`/leads/${id}`);
          }}
        />
      )}
      <div className="lead-console">
        <section className="lead-manifest" aria-labelledby="lead-list-title">
          <div className="list-heading">
            <div>
              <p className="section-kicker">到港队列</p>
              <h2 id="lead-list-title">潜在客户</h2>
            </div>
            <span>{leads.data?.count ?? 0} 条</span>
          </div>
          <div className="lead-filters">
            <label htmlFor="lead-search">搜索线索</label>
            <input
              id="lead-search"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="公司或联系人"
            />
            <label htmlFor="lead-status">筛选状态</label>
            <select
              id="lead-status"
              value={status}
              onChange={(event) =>
                setStatus(event.target.value as "" | LeadStatus)
              }
            >
              {statuses.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          {leads.isLoading && (
            <div className="lead-list-skeleton" aria-label="正在加载线索">
              <span />
              <span />
              <span />
            </div>
          )}
          {leads.isError && (
            <div className="list-message error-state" role="alert">
              <strong>线索未能抵达</strong>
              <p>{describeError(leads.error)}</p>
              <button
                className="secondary-button"
                onClick={() => leads.refetch()}
              >
                重试
              </button>
            </div>
          )}
          {leads.data?.items.length === 0 && (
            <div className="list-message">
              <strong>暂无匹配线索</strong>
              <p>
                {writable
                  ? "调整筛选，或登记第一位潜在客户。"
                  : "请调整筛选条件。"}
              </p>
              {writable && (
                <button
                  className="secondary-button"
                  onClick={() => setCreating(true)}
                >
                  登记新线索
                </button>
              )}
            </div>
          )}
          <div className="lead-list">
            {leads.data?.items.map((lead) => (
              <LeadRow
                key={lead.id}
                lead={lead}
                selected={lead.id === initialLeadId}
              />
            ))}
          </div>
        </section>
        <DetailPanel
          leadId={initialLeadId}
          connected={Boolean(session)}
          writable={writable}
          convertible={convertible}
        />
      </div>
    </main>
  );
}
