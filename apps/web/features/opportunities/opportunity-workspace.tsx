"use client";

import { WorkTextReview } from "../finance/work-review";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ApiClientError } from "@trade-workbench/api-client";
import { useMemberContext } from "../overview/api";
import { useSessionScope } from "../overview/session";
import {
  useOpportunities,
  useOpportunity,
  useOpportunityHistory,
  useOpportunityCommand,
  type Opportunity,
  type OpportunityStatus,
  type Command,
} from "./api";

const labels: Record<OpportunityStatus, string> = {
  OPEN: "待询盘",
  INQUIRY: "已询盘",
  QUOTING: "报价中",
  NEGOTIATION: "洽谈中",
  WON: "已赢单",
  LOST: "已丢单",
};
const schema = z.object({
  reason: z
    .string()
    .trim()
    .min(1, "请填写处理原因")
    .max(1000, "原因最多 1000 字"),
  confirmed: z.boolean().refine(Boolean, "请确认已核对处理影响"),
});
function errorText(error: unknown) {
  if (error instanceof ApiClientError) {
    if (error.problem.status === 409)
      return "商机状态或版本已变化，请刷新后核对。";
    if (error.problem.status === 403) return "当前成员没有此操作权限。";
    if (error.problem.status === 404) return "商机不存在或不在当前组织中。";
  }
  return "未能确认结果，请重试或刷新核对。";
}
export function OpportunityAction({
  scope,
  row,
  command,
  onClose,
  onSuccess = onClose,
}: {
  scope: string;
  row: Opportunity;
  command: Command;
  onClose: () => void;
  onSuccess?: () => void;
}) {
  const mutation = useOpportunityCommand(scope, row.id);
  const [submission, setSubmission] = useState<{
    payload: string;
    key: string;
  } | null>(null);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { reason: "", confirmed: false },
  });
  const label = command === "mark-lost" ? "确认丢单" : "开始洽谈";
  return (
    <form
      className="purchase-change-form"
      onSubmit={form.handleSubmit(({ reason }) => {
        const body = { reason, expected_version: row.version };
        const payload = JSON.stringify({ command, body });
        const key =
          submission?.payload === payload
            ? submission.key
            : crypto.randomUUID();
        setSubmission({ payload, key });
        mutation.mutate({ command, body, key }, { onSuccess });
      })}
    >
      <h2>{label}</h2>
      {command === "mark-lost" && (
        <p>
          丢单后不能继续接受报价或重开商机。已有报价证据保留，本操作不会撤回报价或向客户发送消息。
        </p>
      )}
      <fieldset disabled={mutation.isPending}>
        <label>
          处理原因
          <textarea
            rows={3}
            {...form.register("reason")}
            aria-invalid={Boolean(form.formState.errors.reason)}
          />
        </label>
        {form.formState.errors.reason && (
          <p role="alert">{form.formState.errors.reason.message}</p>
        )}
        <label className="outbox-confirm">
          <input type="checkbox" {...form.register("confirmed")} />
          已核对当前商机与处理影响
        </label>
        {form.formState.errors.confirmed && (
          <p role="alert">{form.formState.errors.confirmed.message}</p>
        )}
        {mutation.isError && <p role="alert">{errorText(mutation.error)}</p>}
        <div className="purchase-actions">
          <button className="primary-button" type="submit">
            {mutation.isPending ? "正在记录…" : label}
          </button>
          <button className="secondary-button" type="button" onClick={onClose}>
            返回，不做变更
          </button>
        </div>
      </fieldset>
    </form>
  );
}
function OpportunityList({ scope }: { scope: string }) {
  const [status, setStatus] = useState<OpportunityStatus | undefined>();
  const [cursors, setCursors] = useState<Array<string | undefined>>([
    undefined,
  ]);
  const query = useOpportunities(scope, status, cursors.at(-1));
  return (
    <section className="action-queue opportunity-panel">
      <header>
        <h1>商机跟进</h1>
        <button
          className="secondary-button"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          刷新
        </button>
      </header>
      <label>
        阶段筛选
        <select
          value={status ?? ""}
          onChange={(e) => {
            setStatus(
              (e.target.value || undefined) as OpportunityStatus | undefined,
            );
            setCursors([undefined]);
          }}
        >
          <option value="">全部阶段</option>
          {Object.entries(labels).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {query.isPending && <p role="status">正在读取商机…</p>}
      {query.isError && <p role="alert">{errorText(query.error)}</p>}
      {query.data?.items.length === 0 && (
        <p>当前没有符合条件的商机。可从线索转换建立商机。</p>
      )}
      <ul>
        {query.data?.items.map((row) => (
          <li key={row.id}>
            <Link href={`/opportunities/${row.id}`}>
              <strong>{row.name}</strong>
              <span>{labels[row.status]}</span>
            </Link>
          </li>
        ))}
      </ul>
      <nav className="queue-pagination" aria-label="商机分页">
        <button
          className="secondary-button"
          disabled={cursors.length === 1 || query.isFetching}
          onClick={() => setCursors(cursors.slice(0, -1))}
        >
          上一页
        </button>
        <button
          className="secondary-button"
          disabled={!query.data?.has_more || query.isFetching || query.isError}
          onClick={() =>
            setCursors([...cursors, query.data?.next_cursor ?? undefined])
          }
        >
          下一页
        </button>
      </nav>
    </section>
  );
}
function OpportunityDetail({
  scope,
  id,
  writable,
}: {
  scope: string;
  id: string;
  writable: boolean;
}) {
  const query = useOpportunity(scope, id);
  const [offset, setOffset] = useState(0);
  const history = useOpportunityHistory(scope, id, offset);
  const [command, setCommand] = useState<Command | null>(null);
  const [notice, setNotice] = useState("");
  if (query.isPending) return <p role="status">正在读取商机…</p>;
  if (query.isError)
    return (
      <section role="alert">
        <p>{errorText(query.error)}</p>
        <button
          className="secondary-button"
          onClick={() => void query.refetch()}
        >
          重试
        </button>
      </section>
    );
  const row = query.data;
  const terminal = row.status === "WON" || row.status === "LOST";
  return (
    <section className="action-queue opportunity-panel">
      <header>
        <h1>{row.name}</h1>
        <button
          className="secondary-button"
          disabled={query.isFetching}
          onClick={() => {
            setCommand(null);
            void query.refetch();
            void history.refetch();
          }}
        >
          刷新
        </button>
      </header>
      <p className="section-kicker">当前阶段 · {labels[row.status]}</p>
      <p>询盘和报价自动推进阶段，客户接受报价后赢单。</p>
      {row.status === "LOST" && (
        <section aria-label="丢单原因审核">
          <p className="work-content-preview">
            丢单原因：
            {row.content_visible
              ? row.lost_reason || "未记录"
              : "保密，待审核后开放"}
          </p>
          <WorkTextReview
            crmKind="opportunity"
            recordId={row.id}
            onChanged={async () => {
              await query.refetch();
              await history.refetch();
            }}
          />
        </section>
      )}
      {row.lost_at && (
        <p>记录时间：{new Date(row.lost_at).toLocaleString("zh-CN")}</p>
      )}
      <Link href="/quotations">前往询盘与报价</Link>
      {notice && <p role="status">{notice}</p>}
      {writable && !terminal && !command && (
        <div className="purchase-actions">
          {row.status === "QUOTING" && (
            <button
              className="secondary-button"
              onClick={() => setCommand("start-negotiation")}
            >
              开始洽谈
            </button>
          )}
          <button
            className="secondary-button"
            onClick={() => setCommand("mark-lost")}
          >
            标记丢单
          </button>
        </div>
      )}
      {writable && !terminal && command && (
        <OpportunityAction
          key={`${row.id}-${row.version}-${command}`}
          scope={scope}
          row={row}
          command={command}
          onClose={() => {
            setCommand(null);
            setNotice("");
          }}
          onSuccess={() => {
            setCommand(null);
            setNotice("商机阶段已更新，处理原因已记入时间线。");
          }}
        />
      )}
      <h2>商机时间线</h2>
      {history.isPending && <p role="status">正在读取记录…</p>}
      {history.isError && <p role="alert">{errorText(history.error)}</p>}
      {history.data?.items.length === 0 && <p>暂无阶段记录。</p>}
      <ul>
        {history.data?.items.map((item) => (
          <li key={item.id}>
            <p>{item.summary ?? "保密活动：待审核后开放"}</p>
            <WorkTextReview
              subjectType="opportunity"
              subjectId={row.id}
              recordId={item.id}
              onChanged={() => history.refetch()}
            />
            <time dateTime={item.occurred_at}>
              {new Date(item.occurred_at).toLocaleString("zh-CN")}
            </time>
          </li>
        ))}
      </ul>
      <nav className="queue-pagination" aria-label="时间线分页">
        <button
          className="secondary-button"
          disabled={offset === 0 || history.isFetching}
          onClick={() => setOffset(Math.max(0, offset - 10))}
        >
          较新记录
        </button>
        <button
          className="secondary-button"
          disabled={
            !history.data?.has_more || history.isFetching || history.isError
          }
          onClick={() => setOffset(offset + 10)}
        >
          更早记录
        </button>
      </nav>
    </section>
  );
}
function Connected({ scope, id }: { scope: string; id?: string }) {
  const member = useMemberContext(scope);
  if (member.isPending) return <p role="status">正在确认权限…</p>;
  if (member.isError) return <p role="alert">{errorText(member.error)}</p>;
  if (!member.data.permissions.includes("opportunity.read"))
    return <p role="alert">当前成员无商机查看权限。</p>;
  return id ? (
    <OpportunityDetail
      key={id}
      scope={scope}
      id={id}
      writable={member.data.permissions.includes("opportunity.write")}
    />
  ) : (
    <OpportunityList scope={scope} />
  );
}
export function OpportunityWorkspace({ id }: { id?: string }) {
  const scope = useSessionScope();
  return (
    <main id="main-content" className="overview-shell">
      <header className="topbar">
        <Link className="brand" href="/">
          外贸工作台
        </Link>
        <nav className="overview-nav" aria-label="商机导航">
          <Link href="/opportunities">全部商机</Link>
          <Link href="/leads">线索</Link>
          <Link href="/quotations">报价</Link>
        </nav>
      </header>
      {scope ? (
        <Connected key={scope} scope={scope} id={id} />
      ) : (
        <p>请先登录并选择业务组织。</p>
      )}
    </main>
  );
}
