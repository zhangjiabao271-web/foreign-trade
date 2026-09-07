"use client";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ApiClientError, type components } from "@trade-workbench/api-client";
import { useActionQueue, useMemberContext, type QueueKind } from "./api";
import { connectSession, disconnectSession, useSessionScope } from "./session";
const queues: Array<{
  kind: QueueKind;
  title: string;
  permission: components["schemas"]["Permission"];
}> = [
  {
    kind: "receivables",
    title: "今日到期与逾期应收",
    permission: "receivable.read",
  },
  { kind: "deposits", title: "待收定金", permission: "order.read" },
  { kind: "leads", title: "待跟进线索", permission: "lead.read" },
  {
    kind: "quotations",
    title: "等待客户回复的报价",
    permission: "quotation.read",
  },
  { kind: "preparation", title: "采购与备货", permission: "order.read" },
  { kind: "shipments", title: "准备出货与文件", permission: "shipment.read" },
  { kind: "customs", title: "人工报关跟进", permission: "export.read" },
  { kind: "refunds", title: "人工退税跟进", permission: "export.read" },
];
const documentNames: Record<string, string> = {
  COMMERCIAL_INVOICE: "商业发票",
  SALES_CONTRACT: "销售合同",
  PACKING_LIST: "装箱单",
  BILL_OF_LADING: "提单",
  CERTIFICATE_OF_ORIGIN: "原产地证",
  BOOKING_CONFIRMATION: "订舱确认",
  OTHER: "其他文件",
};
function errorText(error: unknown) {
  if (error instanceof ApiClientError) {
    if (error.problem.status === 401) return "连接凭证已失效，请重新连接。";
    if (error.problem.status === 403) return "当前成员没有查看权限。";
  }
  return "暂时无法读取业务事项，请重试。";
}
const connectionSchema = z.object({
  organization: z.uuid("请输入有效的组织 ID"),
  token: z.string().trim().min(1, "请输入访问令牌"),
});
export function WorkspaceConnection() {
  const form = useForm<z.infer<typeof connectionSchema>>({
    resolver: zodResolver(connectionSchema),
  });
  return (
    <section className="connection-panel" aria-labelledby="connect-title">
      <p className="section-kicker">受控访问</p>
      <h1 id="connect-title">连接你的业务空间</h1>
      <p>使用当前组织的访问凭证。登录接入尚在本地验收阶段。</p>
      <form
        className="finance-form"
        onSubmit={form.handleSubmit(({ organization, token }) =>
          connectSession(organization, token),
        )}
      >
        <label>
          组织 ID
          <input
            {...form.register("organization")}
            aria-invalid={Boolean(form.formState.errors.organization)}
          />
        </label>
        {form.formState.errors.organization && (
          <p role="alert">{form.formState.errors.organization.message}</p>
        )}
        <label>
          访问令牌
          <input
            type="password"
            autoComplete="off"
            {...form.register("token")}
            aria-invalid={Boolean(form.formState.errors.token)}
          />
        </label>
        {form.formState.errors.token && (
          <p role="alert">{form.formState.errors.token.message}</p>
        )}
        <button className="primary-button" type="submit">
          连接业务空间
        </button>
      </form>
    </section>
  );
}
function ActionQueue({
  scope,
  kind,
  title,
}: {
  scope: string;
  kind: QueueKind;
  title: string;
}) {
  const [offset, setOffset] = useState(0);
  const query = useActionQueue(scope, kind, offset);
  return (
    <section
      className="action-queue"
      aria-labelledby={`queue-${kind}`}
      aria-busy={query.isFetching}
    >
      <header>
        <h2 id={`queue-${kind}`}>{title}</h2>
        <button
          className="secondary-button"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          刷新
        </button>
      </header>
      {query.isPending && <p role="status">正在读取事项…</p>}
      {query.isError && <p role="alert">{errorText(query.error)}</p>}
      {query.data && (
        <>
          <p className="queue-date">
            业务日 {query.data.business_date} · 本页 {query.data.items.length}{" "}
            项{query.data.has_more ? "，还有更多" : ""}
          </p>
          {query.data.items.length === 0 && (
            <p>当前页没有待处理事项。业务状态变化后可刷新查看。</p>
          )}
          <ul>
            {query.data.items.map((item) => (
              <li key={item.id}>
                <Link href={item.href}>
                  <strong>{item.title}</strong>
                  <span>
                    {item.next_action} <span aria-hidden="true">→</span>
                  </span>
                </Link>
                {item.due_date && (
                  <p className={item.overdue ? "queue-overdue" : "queue-date"}>
                    {item.overdue ? "已逾期" : "相关日期"} · {item.due_date}
                  </p>
                )}
                {item.missing_document_types.length > 0 && (
                  <p className="queue-overdue">
                    缺少：
                    {item.missing_document_types
                      .map((value) => documentNames[value] ?? value)
                      .join("、")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      <nav aria-label={`${title}分页`} className="queue-pagination">
        <button
          className="secondary-button"
          disabled={offset === 0 || query.isFetching}
          onClick={() => setOffset(Math.max(0, offset - 5))}
        >
          上一页
        </button>
        <button
          className="secondary-button"
          disabled={!query.data?.has_more || query.isFetching || query.isError}
          onClick={() => setOffset(query.data?.next_offset ?? offset)}
        >
          下一页
        </button>
      </nav>
    </section>
  );
}
function ConnectedOverview({ scope }: { scope: string }) {
  const member = useMemberContext(scope);
  if (member.isPending) return <p role="status">正在确认组织与权限…</p>;
  if (member.isError)
    return (
      <section role="alert">
        <p>{errorText(member.error)}</p>
        <button
          className="secondary-button"
          onClick={() => void member.refetch()}
        >
          重试连接
        </button>
        <button className="secondary-button" onClick={disconnectSession}>
          重新连接
        </button>
      </section>
    );
  if (!member.data.permissions.includes("overview.read"))
    return <p role="alert">当前成员没有首页查看权限。</p>;
  return (
    <>
      <section className="overview-heading">
        <p className="section-kicker">行动舱单 / 每日经营</p>
        <h1>今天，推进哪一笔订单？</h1>
        <p>
          从下一动作进入业务对象，核对款项、交付和证据。事项按当前组织实时读取，每分钟刷新。
        </p>
        <button className="secondary-button" onClick={disconnectSession}>
          切换业务空间
        </button>
        {member.data.permissions.includes("outbox.read") && (
          <Link className="secondary-button" href="/admin/outbox">
            失败事件管理
          </Link>
        )}
        {member.data.permissions.includes("organization.manage") && (
          <Link className="secondary-button" href="/admin/organization">
            组织与成员管理
          </Link>
        )}
        {member.data.permissions.includes("operations.monitor") && (
          <Link className="secondary-button" href="/admin/operations">
            运行监控
          </Link>
        )}
      </section>
      <div className="action-grid">
        {queues.map((queue) =>
          member.data.permissions.includes(queue.permission) ? (
            <ActionQueue key={queue.kind} scope={scope} {...queue} />
          ) : (
            <section className="action-queue" key={queue.kind}>
              <h2>{queue.title}</h2>
              <p>当前成员无查看权限。</p>
            </section>
          ),
        )}
      </div>
    </>
  );
}
export function OverviewWorkspace() {
  const scope = useSessionScope();
  return (
    <main id="main-content" className="overview-shell">
      <header className="topbar">
        <Link className="brand" href="/">
          外贸工作台
        </Link>
        <nav className="overview-nav" aria-label="业务导航">
          <Link href="/leads">线索</Link>
          <Link href="/companies">客商</Link>
          <Link href="/products">产品</Link>
          <Link href="/opportunities">商机</Link>
          <Link href="/quotations">报价</Link>
          <Link href="/orders">订单</Link>
          <Link href="/shipments">出货</Link>
          <Link href="/export/customs">报关／退税</Link>
          <Link href="/copilot">业务助手</Link>
        </nav>
      </header>
      {scope ? (
        <ConnectedOverview key={scope} scope={scope} />
      ) : (
        <WorkspaceConnection />
      )}
    </main>
  );
}
