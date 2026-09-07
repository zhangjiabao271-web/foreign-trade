"use client";
import Link from "next/link";
import { ApiClientError } from "@trade-workbench/api-client";
import { useMemberContext } from "../overview/api";
import { useSessionScope } from "../overview/session";
import { useOperations, type Operations } from "./operations-api";

function errorText(error: unknown) {
  if (error instanceof ApiClientError && error.problem.status === 403)
    return "当前成员没有运行监控权限，请联系管理员。";
  return "运行数据暂时无法读取，请刷新重试；不要将读取失败当作没有积压。";
}
function Counts({
  title,
  states,
  labels,
}: {
  title: string;
  states: Record<string, number>;
  labels: Record<string, string>;
}) {
  return (
    <section className="action-queue">
      <h2>{title}</h2>
      <dl>
        {Object.entries(labels).map(([state, label]) => (
          <div key={state}>
            <dt>{label}</dt>
            <dd>{states[state] ?? 0}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
export function OperationsPanel({ data }: { data: Operations }) {
  const timing = data.request_metrics;
  return (
    <>
      <p>
        读取时间：
        <time dateTime={data.captured_at}>
          {new Date(data.captured_at).toLocaleString("zh-CN")}
        </time>{" "}
        · 仅当前组织
      </p>
      <section className="outbox-ledger">
        <h2>先处理未完成的投递</h2>
        <p>尚无后台消费确认：{data.awaiting_consumer_count} 项</p>
        <p>
          最老未确认等待：
          {data.oldest_awaiting_seconds === null
            ? "无待确认事件"
            : `${Math.floor(data.oldest_awaiting_seconds)} 秒`}
        </p>
        <p>
          已投递不等于处理成功；等待年龄从事件创建起算，含延迟调度与重试，不是
          Redis 队列长度。
        </p>
        <Link href="/admin/outbox" className="secondary-button">
          检查失败事件
        </Link>
      </section>
      <div className="action-grid">
        <Counts
          title="事件投递状态"
          states={data.outbox_states}
          labels={{
            PENDING: "等待投递",
            PROCESSING: "正在投递",
            PUBLISHED: "已交给队列（含已处理）",
            DEAD: "停止自动重试",
          }}
        />
        <Counts
          title="异步任务状态"
          states={data.job_states}
          labels={{
            PENDING: "等待执行",
            RUNNING: "执行中",
            SUCCEEDED: "执行成功",
            FAILED: "执行失败",
            CANCELLED: "已取消",
          }}
        />
        <Counts
          title="文件处理状态"
          states={data.document_states}
          labels={{
            PENDING_UPLOAD: "等待完成上传",
            UPLOADED: "等待扫描",
            SCANNING: "扫描中",
            AVAILABLE: "可用版本",
            REJECTED: "未通过验收",
          }}
        />
        <Counts
          title="AI 执行状态"
          states={data.ai_run_states}
          labels={{
            PENDING: "等待执行",
            RUNNING: "执行中",
            SUCCEEDED: "已完成",
            FAILED: "执行失败",
          }}
        />
        <section className="action-queue">
          <h2>AI 成本与人工批准</h2>
          <dl>
            <div>
              <dt>已知估算费用（USD）</dt>
              <dd>{data.known_estimated_cost_usd}</dd>
            </div>
            <div>
              <dt>费用未知的运行数</dt>
              <dd>{data.unknown_cost_runs}</dd>
            </div>
            <div>
              <dt>输入 / 输出 token</dt>
              <dd>
                {data.ai_input_tokens} / {data.ai_output_tokens}
              </dd>
            </div>
            <div>
              <dt>已决请求批准率</dt>
              <dd>
                {data.approval_rate === null
                  ? "暂无已决请求"
                  : `${(Number(data.approval_rate) * 100).toFixed(1)}%`}
              </dd>
            </div>
            <div>
              <dt>仍待人工决定</dt>
              <dd>{data.approval_states.PENDING ?? 0}</dd>
            </div>
          </dl>
          <p>
            批准率 = 批准 /（批准 +
            拒绝）。未知费用不按零处理；估算不是供应商账单。
          </p>
        </section>
        <section className="action-queue">
          <h2>接口临时运行样本</h2>
          {timing ? (
            <>
              <p>
                窗口起点：{new Date(timing.started_at).toLocaleString("zh-CN")}
              </p>
              <dl>
                <div>
                  <dt>已认证请求</dt>
                  <dd>{timing.requests}</dd>
                </div>
                <div>
                  <dt>错误响应 / 服务端错误</dt>
                  <dd>
                    {timing.errors} / {timing.server_errors}
                  </dd>
                </div>
                <div>
                  <dt>文件写入接口错误</dt>
                  <dd>{timing.upload_errors}</dd>
                </div>
                <div>
                  <dt>平均 / 最大耗时（ms）</dt>
                  <dd>
                    {timing.requests
                      ? (timing.duration_sum_ms / timing.requests).toFixed(2)
                      : "暂无样本"}{" "}
                    / {timing.duration_max_ms.toFixed(2)}
                  </dd>
                </div>
              </dl>
            </>
          ) : (
            <p>当前进程尚无本组织运行样本。</p>
          )}
          <p>
            仅当前 API
            进程的有界内存窗口，重启或缓存淘汰后重置；不代表全服务历史或生产性能验收。
          </p>
        </section>
      </div>
      <section className="overview-heading">
        <h2>如何理解这些数字</h2>
        <p>
          数据库状态统计覆盖当前组织未删除的记录。文件“未通过验收”不等于检测到恶意文件，“等待上传”也不等于上传失败；当前扫描仍是框架占位。文件接口错误包含输入校验和权限拒绝，不是对象存储失败总数。
        </p>
        <p>
          数据库连接池属于共享基础设施，仅在运维日志输出，不在组织页面披露。页面只读，不能代替业务核验或直接修改状态。
        </p>
      </section>
    </>
  );
}
function Data({ scope }: { scope: string }) {
  const query = useOperations(scope);
  return (
    <section aria-label="当前组织运行监控" aria-busy={query.isFetching}>
      <button
        className="secondary-button"
        disabled={query.isFetching}
        onClick={() => void query.refetch()}
      >
        刷新运行数据
      </button>
      {query.isPending && <p role="status">正在读取运行状态…</p>}
      {query.isError && <p role="alert">{errorText(query.error)}</p>}
      {query.data && !query.isError && <OperationsPanel data={query.data} />}
    </section>
  );
}
function Authorized({ scope }: { scope: string }) {
  const member = useMemberContext(scope);
  if (member.isPending) return <p role="status">正在确认监控权限…</p>;
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
  if (!member.data.permissions.includes("operations.monitor"))
    return <p role="alert">当前成员没有运行监控权限，请联系管理员。</p>;
  return <Data scope={scope} />;
}
export function OperationsWorkspace() {
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
        <p className="section-kicker">运行保障 / 当前组织</p>
        <h1>运行监控</h1>
        <p>
          先查积压与失败，再核对处理记录。每分钟刷新，不将读取失败或未知费用当作零。
        </p>
      </section>
      {scope ? (
        <Authorized key={scope} scope={scope} />
      ) : (
        <p role="alert">请先登录并选择业务空间。</p>
      )}
    </main>
  );
}
