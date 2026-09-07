"use client";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ApiClientError } from "@trade-workbench/api-client";
import { useMemberContext } from "../overview/api";
import { useSessionScope } from "../overview/session";
import { useDeadEvents, useReplayEvent, type OutboxEvent } from "./api";

const replaySchema = z.object({
  reason: z
    .string()
    .trim()
    .min(1, "请填写重放原因")
    .max(1000, "原因不能超过 1000 字"),
  confirmed: z.boolean().refine(Boolean, "请确认已核对失败原因和处理影响"),
});
function errorText(error: unknown) {
  if (error instanceof ApiClientError) {
    if (error.problem.status === 409)
      return "事件状态已变化。请刷新列表后重新核对，不要重复提交。";
    if (error.problem.status === 401) return "登录已失效，请重新登录。";
    if (error.problem.status === 403) return "当前成员没有执行此操作的权限。";
    if (error.problem.status === 404) return "事件已不可访问，请刷新列表。";
  }
  return "请求未能确认完成，请刷新列表核对状态后再试。";
}
function ReplayForm({
  event,
  scope,
  onCancel,
  onSuccess,
}: {
  event: OutboxEvent;
  scope: string;
  onCancel: () => void;
  onSuccess: () => void;
}) {
  const replay = useReplayEvent(scope);
  const form = useForm<z.infer<typeof replaySchema>>({
    resolver: zodResolver(replaySchema),
    defaultValues: { reason: "", confirmed: false },
  });
  return (
    <form
      className="outbox-replay"
      onSubmit={form.handleSubmit(({ reason }) =>
        replay.mutate({ event, reason }, { onSuccess }),
      )}
    >
      <label htmlFor={`reason-${event.id}`}>重放原因</label>
      <textarea
        id={`reason-${event.id}`}
        {...form.register("reason")}
        rows={3}
        aria-invalid={Boolean(form.formState.errors.reason)}
        aria-describedby={`reason-error-${event.id}`}
      />
      <p
        id={`reason-error-${event.id}`}
        role={form.formState.errors.reason ? "alert" : undefined}
      >
        {form.formState.errors.reason?.message}
      </p>
      <label className="outbox-confirm">
        <input type="checkbox" {...form.register("confirmed")} />
        已核对失败原因和处理影响，确认将此事件重新排队。
      </label>
      {form.formState.errors.confirmed && (
        <p role="alert">{form.formState.errors.confirmed.message}</p>
      )}
      {replay.isError && <p role="alert">{errorText(replay.error)}</p>}
      <div className="queue-pagination">
        <button
          className="primary-button"
          disabled={replay.isPending}
          type="submit"
        >
          {replay.isPending ? "正在重新排队…" : "确认重新排队"}
        </button>
        <button
          className="secondary-button"
          disabled={replay.isPending}
          type="button"
          onClick={onCancel}
        >
          取消
        </button>
      </div>
    </form>
  );
}
function EventList({
  scope,
  canReplay,
}: {
  scope: string;
  canReplay: boolean;
}) {
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const query = useDeadEvents(scope, offset);
  return (
    <section
      className="outbox-ledger"
      aria-label="失败事件列表"
      aria-busy={query.isFetching}
    >
      <header className="queue-pagination">
        <h2>等待人工处理</h2>
        <button
          className="secondary-button"
          disabled={query.isFetching || selected !== null}
          onClick={() => void query.refetch()}
        >
          刷新列表
        </button>
      </header>
      <p role="status">{notice}</p>
      {query.isPending && <p role="status">正在读取失败事件…</p>}
      {query.isError && <p role="alert">{errorText(query.error)}</p>}
      {query.data && !query.isError && (
        <>
          <p>
            第 {Math.floor(offset / 10) + 1} 页 · 本页 {query.data.items.length}{" "}
            项（不是全部事件总数）
          </p>
          {query.data.items.length === 0 && (
            <p>
              当前页没有失败事件。可返回上一页或刷新；重新排队的事件不会继续显示在这里。
            </p>
          )}
          {query.data.items.map((event) => (
            <article key={event.id} className="outbox-event">
              <header>
                <h3>{event.event_type}</h3>
                <span className="queue-overdue">
                  已停止自动重试 · {event.attempt_count} 次尝试
                </span>
              </header>
              <p>
                {event.last_error === "CONSUMER_RECEIPT_TIMEOUT"
                  ? "未收到处理确认，请核对后台处理服务。"
                  : "事件投递失败，请先核对依赖服务和处理日志。"}
              </p>
              <dl>
                <div>
                  <dt>事件编号</dt>
                  <dd>{event.id}</dd>
                </div>
                <div>
                  <dt>业务对象</dt>
                  <dd>
                    {event.aggregate_type} / {event.aggregate_id}
                  </dd>
                </div>
                <div>
                  <dt>追踪编号</dt>
                  <dd>{event.correlation_id}</dd>
                </div>
                <div>
                  <dt>创建时间</dt>
                  <dd>
                    <time dateTime={event.created_at}>
                      {new Date(event.created_at).toLocaleString("zh-CN")}
                    </time>
                  </dd>
                </div>
              </dl>
              {canReplay && selected === event.id && (
                <ReplayForm
                  key={event.version}
                  event={event}
                  scope={scope}
                  onCancel={() => setSelected(null)}
                  onSuccess={() => {
                    setSelected(null);
                    setNotice(
                      "事件已重新排队，尚不代表处理完成。请在相关业务对象核对结果。",
                    );
                    setOffset(0);
                  }}
                />
              )}
              {canReplay && selected !== event.id && (
                <button
                  className="secondary-button"
                  disabled={selected !== null}
                  onClick={() => {
                    setNotice("");
                    setSelected(event.id);
                  }}
                >
                  准备重放
                </button>
              )}
              {!canReplay && <p>当前成员只能查看，无重放权限。</p>}
            </article>
          ))}
        </>
      )}
      <nav className="queue-pagination" aria-label="失败事件分页">
        <button
          className="secondary-button"
          disabled={offset === 0 || query.isFetching || selected !== null}
          onClick={() => setOffset(Math.max(0, offset - 10))}
        >
          上一页
        </button>
        <button
          className="secondary-button"
          disabled={
            !query.data?.has_more ||
            query.isFetching ||
            query.isError ||
            selected !== null
          }
          onClick={() => setOffset(query.data?.next_offset ?? offset)}
        >
          下一页
        </button>
      </nav>
    </section>
  );
}
function AuthorizedOutbox({ scope }: { scope: string }) {
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
          重试权限检查
        </button>
      </section>
    );
  if (!member.data.permissions.includes("outbox.read"))
    return <p role="alert">当前成员没有失败事件查看权限。</p>;
  return (
    <EventList
      scope={scope}
      canReplay={member.data.permissions.includes("outbox.replay")}
    />
  );
}
export function OutboxWorkspace() {
  const scope = useSessionScope();
  return (
    <main id="main-content" className="overview-shell">
      <header className="topbar">
        <Link className="brand" href="/">
          外贸工作台
        </Link>
        <Link href="/">返回经营首页</Link>
      </header>
      <section className="overview-heading">
        <p className="section-kicker">运行保障 / 人工恢复</p>
        <h1>失败事件</h1>
        <p>
          仅显示当前组织已停止自动重试的事件。先排查原因，再人工重新排队；每次重放都会留存操作人和原因。
        </p>
      </section>
      {scope ? (
        <AuthorizedOutbox key={scope} scope={scope} />
      ) : (
        <p role="alert">请先登录并选择业务空间。</p>
      )}
    </main>
  );
}
