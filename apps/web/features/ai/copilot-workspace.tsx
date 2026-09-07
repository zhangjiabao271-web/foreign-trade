"use client";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ApiClientError } from "@trade-workbench/api-client";
import { DisclosureQueue, SubmitDisclosure } from "./disclosure-panel";
import { useMemberContext } from "../overview/api";
import { WorkspaceConnection } from "../overview/overview-workspace";
import { disconnectSession, useSessionScope } from "../overview/session";
import {
  useAiCommand,
  useApprovals,
  useCalls,
  useRun,
  useRuns,
  type Approval,
  type Intent,
  type Run,
} from "./api";

const intents: Record<Intent, string> = {
  SEARCH: "搜索公司",
  TIMELINE: "摘要订单进度",
  PROFIT: "解释报价毛利",
  EMAIL_DRAFT: "拟写邮件草稿",
  TASK_DRAFT: "建议内部跟进任务",
};
const statuses: Record<string, string> = {
  PENDING: "等待处理",
  RUNNING: "处理中",
  SUCCEEDED: "已生成",
  FAILED: "未成功",
  APPROVED: "已批准并创建任务",
  REJECTED: "已拒绝",
};
function message(error: unknown) {
  if (error instanceof ApiClientError) {
    if (error.problem.status === 403)
      return "当前成员没有此操作权限，请刷新权限或联系管理员。";
    if (error.problem.status === 404) return "当前空间内找不到该记录。";
    if (error.problem.status === 409)
      return "记录已更新或不满足操作条件，请刷新后核对。";
  }
  return "操作未成功，请检查连接后重试。";
}
function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
const createSchema = z
  .object({
    intent: z.enum([
      "SEARCH",
      "TIMELINE",
      "PROFIT",
      "EMAIL_DRAFT",
      "TASK_DRAFT",
    ]),
    source: z.string().trim().min(2, "请填写来源").max(80),
  })
  .superRefine((value, ctx) => {
    if (value.intent !== "SEARCH" && !z.uuid().safeParse(value.source).success)
      ctx.addIssue({
        code: "custom",
        path: ["source"],
        message: "请输入有效的订单 ID",
      });
  });

function CreateRun({
  scope,
  profit,
  onCreated,
}: {
  scope: string;
  profit: boolean;
  onCreated: (id: string) => void;
}) {
  const mutation = useAiCommand(scope);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const form = useForm<z.infer<typeof createSchema>>({
    resolver: zodResolver(createSchema),
    defaultValues: { intent: "TIMELINE", source: "" },
  });
  const [search, setSearch] = useState(false);
  return (
    <section className="finance-section">
      <h2>选择本次辅助工作</h2>
      <form
        className="finance-form"
        onSubmit={form.handleSubmit(async (value) => {
          try {
            const result = await mutation.mutateAsync({
              action: "run",
              key,
              body: {
                intent: value.intent,
                subject_id: value.intent === "SEARCH" ? null : value.source,
                search_term: value.intent === "SEARCH" ? value.source : null,
              },
            });
            onCreated(result.id);
            setKey(crypto.randomUUID());
          } catch {
            /* Keep the command key for a safe retry. */
          }
        })}
      >
        <label>
          辅助类型
          <select
            {...form.register("intent", {
              onChange: (e) => {
                setSearch(e.target.value === "SEARCH");
                setKey(crypto.randomUUID());
              },
            })}
          >
            {Object.entries(intents)
              .filter(([key]) => key !== "PROFIT" || profit)
              .map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
          </select>
        </label>
        <label>
          {search ? "公司名称关键词" : "订单 ID"}
          <input
            {...form.register("source", {
              onChange: () => setKey(crypto.randomUUID()),
            })}
          />
        </label>
        {form.formState.errors.source && (
          <p role="alert">{form.formState.errors.source.message}</p>
        )}
        <p>只提交所选意图与必要来源，不要填写密码、密钥或无关个人资料。</p>
        {mutation.isError && <p role="alert">{message(mutation.error)}</p>}
        <button className="primary-button" disabled={mutation.isPending}>
          {mutation.isPending ? "正在排队…" : "开始辅助工作"}
        </button>
      </form>
    </section>
  );
}

const decisionSchema = z.object({
  reason: z.string().trim().min(3, "请说明审核理由").max(1000),
});
function DecisionForm({
  scope,
  id,
  version,
  action,
  disclosureId,
  disclosureVersion,
}: {
  scope: string;
  id: string;
  version: number;
  action: "request" | "approve" | "reject";
  disclosureId?: string | null;
  disclosureVersion?: number | null;
}) {
  const mutation = useAiCommand(scope);
  const form = useForm<z.infer<typeof decisionSchema>>({
    resolver: zodResolver(decisionSchema),
    defaultValues: { reason: "" },
  });
  const label = {
    request: "提交任务建议供人工审核",
    approve: "批准并创建内部任务",
    reject: "拒绝建议",
  }[action];
  return (
    <form
      className="finance-form"
      onSubmit={form.handleSubmit(async (value) => {
        try {
          await mutation.mutateAsync({
            action,
            id,
            body: {
              expected_version: version,
              reason: value.reason,
              ...(action === "request"
                ? {
                    disclosure_id: disclosureId,
                    disclosure_version: disclosureVersion,
                  }
                : {}),
            },
          });
          form.reset();
        } catch {
          /* Render the decision error. */
        }
      })}
    >
      <label>
        {label}的理由
        <input {...form.register("reason")} />
      </label>
      {form.formState.errors.reason && (
        <p role="alert">{form.formState.errors.reason.message}</p>
      )}
      {mutation.isError && <p role="alert">{message(mutation.error)}</p>}
      {mutation.isSuccess && <p role="status">操作已记录。</p>}
      <button className="secondary-button" disabled={mutation.isPending}>
        {mutation.isPending ? "正在记录…" : label}
      </button>
    </form>
  );
}

function SourceFacts({ run }: { run: Run }) {
  const facts = run.output?.facts;
  return (
    <section>
      <h3>事实依据 · 来自业务记录</h3>
      <ul>
        {Array.isArray(facts) &&
          facts.map((fact, index) => {
            const result = record(record(fact).result);
            return (
              <li key={index}>
                {typeof result.order_number === "string" && (
                  <p>
                    订单 {result.order_number} · 金额 {String(result.total)}{" "}
                    {String(result.currency)} · 约定定金{" "}
                    {String(result.agreed_deposit)}
                  </p>
                )}
                {typeof result.gross_profit === "string" && (
                  <p>
                    预计毛利 {result.gross_profit} {String(result.currency)}
                    ，预计成本 {String(result.estimated_cost)}
                    。这是接受报价时的快照，不是已实现利润。
                  </p>
                )}
                {Array.isArray(result.events) && (
                  <p>
                    已查阅最近 {result.events.length} 条订单事件（上限 30 条）。
                  </p>
                )}
                {Array.isArray(result.items) && (
                  <ul>
                    {result.items.map((item, i) => (
                      <li key={i}>{String(record(item).name ?? "公司记录")}</li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
      </ul>
      <ul>
        {run.references.map((source, index) => (
          <li key={index}>
            {source.type === "sales_order" ? (
              <Link href={`/orders/${String(source.id)}`}>查看来源订单</Link>
            ) : (
              <span>公司来源：{String(source.id)}</span>
            )}
            {source.version !== undefined && (
              <span> · 版本 {String(source.version)}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
function RunDetail({
  scope,
  id,
  taskWrite,
  profit,
  canSubmit,
}: {
  scope: string;
  id: string;
  taskWrite: boolean;
  profit: boolean;
  canSubmit: boolean;
}) {
  const query = useRun(scope, id);
  const run = query.data;
  const calls = useCalls(
    scope,
    id,
    Boolean(run && ["SUCCEEDED", "FAILED"].includes(run.status)),
  );
  if (query.isPending) return <p role="status">正在读取辅助结果…</p>;
  if (query.isError || !run) return <p role="alert">{message(query.error)}</p>;
  const artifact = record(run.output?.artifact);
  return (
    <section className="finance-section">
      <h2>{intents[run.intent]}</h2>
      <p role="status">{statuses[run.status] ?? run.status}</p>
      <p>
        模型：{run.model} · 输入 {run.input_tokens} / 输出 {run.output_tokens}{" "}
        tokens ·{" "}
        {!profit
          ? "模型费用受保护"
          : run.estimated_cost_usd === null
            ? "费用估算未配置"
            : `估算费用 ${run.estimated_cost_usd} USD`}
      </p>
      {run.error_code && (
        <p role="alert">
          {run.error_code === "AI_PROVIDER_NOT_CONFIGURED"
            ? "模型服务尚未配置，未生成结果。请由管理员在服务环境中配置凭据与模型。"
            : `本次辅助未成功（${run.error_code}），没有执行任何业务动作。`}
        </p>
      )}
      {run.output && (
        <>
          {profit && <SourceFacts run={run} />}
          <h3>推断与建议 · 需人工判断</h3>
          <ul>
            {Array.isArray(artifact.inferences) &&
              artifact.inferences.map((item, i) => (
                <li key={i}>{String(item)}</li>
              ))}
          </ul>
          <h3>草稿 · 未发送、未执行</h3>
          <p className="copilot-draft">{String(artifact.draft ?? "")}</p>
          {artifact.task_title && (
            <p>建议任务：{String(artifact.task_title)}</p>
          )}
        </>
      )}
      {run.content_protected && (
        <p>
          正文默认保密，即使是本人创建也须审核后开放。原始输入、工具正文及引用内容不会随草稿开放。
        </p>
      )}
      {run.status === "SUCCEEDED" && canSubmit && (
        <SubmitDisclosure
          key={`${id}:${run.version}`}
          scope={scope}
          id={id}
          version={run.version}
        />
      )}
      {run.status === "SUCCEEDED" &&
        run.intent === "TASK_DRAFT" &&
        !run.content_protected &&
        taskWrite && (
          <DecisionForm
            scope={scope}
            id={id}
            version={run.version}
            action="request"
            disclosureId={run.released_disclosure_id}
            disclosureVersion={run.released_disclosure_version}
          />
        )}
      <h3>本次工具调用记录</h3>
      {calls.isError && <p role="alert">{message(calls.error)}</p>}
      <ul>
        {calls.data?.map((call) => (
          <li key={call.id}>
            {(
              {
                read_order: "读取订单",
                order_timeline: "读取订单时间线",
                order_profit: "读取预计毛利",
                search_companies: "搜索公司",
              } as Record<string, string>
            )[call.tool_name] ?? "未获准的工具"}{" "}
            · {call.status === "SUCCEEDED" ? "成功" : "已拦截"}
          </li>
        ))}
      </ul>
    </section>
  );
}
function ApprovalCard({
  scope,
  approval,
  canApprove,
}: {
  scope: string;
  approval: Approval;
  canApprove: boolean;
}) {
  return (
    <article className="finance-section">
      <h3>
        {approval.proposed_action
          ? String(approval.proposed_action.title)
          : "任务审批正文受保护"}
      </h3>
      <p>{statuses[approval.status]}</p>
      <p>
        批准后仅创建一个内部跟进任务，并分配给批准人；不发送邮件、不更改订单或资金状态。
      </p>
      {approval.proposed_action && (
        <Link href={`/orders/${String(approval.proposed_action.order_id)}`}>
          核对来源订单
        </Link>
      )}
      {approval.reason && <p>审核理由：{approval.reason}</p>}
      {canApprove && approval.status === "PENDING" && (
        <>
          <DecisionForm
            scope={scope}
            id={approval.id}
            version={approval.version}
            action="approve"
          />
          <DecisionForm
            scope={scope}
            id={approval.id}
            version={approval.version}
            action="reject"
          />
        </>
      )}
    </article>
  );
}
function ApprovalQueue({
  scope,
  canApprove,
}: {
  scope: string;
  canApprove: boolean;
}) {
  const [cursor, setCursor] = useState<string>();
  const query = useApprovals(scope, cursor);
  return (
    <section>
      <h2>人工审核任务建议</h2>
      {query.isError && <p role="alert">{message(query.error)}</p>}
      {query.isPending && <p role="status">正在读取审核记录…</p>}
      {query.data?.items.map((approval) => (
        <ApprovalCard
          key={approval.id}
          scope={scope}
          approval={approval}
          canApprove={canApprove}
        />
      ))}
      {query.data?.items.length === 0 && <p>暂无提交审核的建议。</p>}
      <button
        className="secondary-button"
        onClick={() => {
          setCursor(undefined);
          void query.refetch();
        }}
      >
        最新审核记录
      </button>
      <button
        className="secondary-button"
        disabled={!query.data?.has_more}
        onClick={() => setCursor(query.data?.next_cursor ?? undefined)}
      >
        更早审核记录
      </button>
    </section>
  );
}
function Connected({
  scope,
  permissions,
}: {
  scope: string;
  permissions: string[];
}) {
  const [cursor, setCursor] = useState<string>();
  const [selected, setSelected] = useState<string>();
  const query = useRuns(scope, cursor);
  return (
    <>
      <header className="overview-nav">
        <Link href="/">外贸工作台</Link>
        <Link href="/orders">订单</Link>
        <button className="quiet-button" onClick={disconnectSession}>
          切换空间
        </button>
      </header>
      <section className="workspace-intro">
        <p className="section-kicker">有依据的建议 · 由人决定</p>
        <h1>受控业务助手</h1>
        <p>
          事实来自当前空间，AI
          只作解释和草稿。所有对同事有影响的任务都需人工审核。
        </p>
      </section>
      {permissions.includes("ai.run") && (
        <CreateRun
          scope={scope}
          profit={permissions.includes("profit.read")}
          onCreated={setSelected}
        />
      )}
      <div className="copilot-grid">
        <section className="finance-section">
          <h2>我的辅助记录</h2>
          {query.isError && <p role="alert">{message(query.error)}</p>}
          {query.isPending && <p role="status">正在读取记录…</p>}
          <ul>
            {query.data?.items.map((run) => (
              <li key={run.id}>
                <button
                  className="quiet-button"
                  onClick={() => setSelected(run.id)}
                >
                  {intents[run.intent]} · {statuses[run.status]}
                </button>
              </li>
            ))}
          </ul>
          {query.data?.items.length === 0 && (
            <p>选择辅助类型和来源，开始第一项工作。</p>
          )}
          <button
            className="secondary-button"
            onClick={() => {
              setCursor(undefined);
              void query.refetch();
            }}
          >
            最新记录
          </button>
          <button
            className="secondary-button"
            disabled={!query.data?.has_more}
            onClick={() => setCursor(query.data?.next_cursor ?? undefined)}
          >
            更早记录
          </button>
        </section>
        {selected ? (
          <RunDetail
            key={selected}
            scope={scope}
            id={selected}
            taskWrite={permissions.includes("task.write")}
            profit={permissions.includes("profit.read")}
            canSubmit={permissions.includes("ai.run")}
          />
        ) : (
          <section className="finance-section">
            <p>选择一项记录，核对事实、建议和草稿。</p>
          </section>
        )}
      </div>
      <DisclosureQueue
        scope={scope}
        reviewer={permissions.includes("profit.read")}
      />
      {permissions.includes("ai.run") && permissions.includes("task.write") && (
        <ApprovalQueue
          scope={scope}
          canApprove={permissions.includes("ai.approve")}
        />
      )}
    </>
  );
}
export function CopilotWorkspace() {
  const scope = useSessionScope();
  const member = useMemberContext(scope);
  if (!scope) return <WorkspaceConnection />;
  return (
    <main id="main-content" className="overview-shell">
      {member.isPending ? (
        <p role="status">正在核对权限…</p>
      ) : member.isError ? (
        <p role="alert">{message(member.error)}</p>
      ) : member.data?.permissions.includes("ai.read") ? (
        <Connected
          key={scope}
          scope={scope}
          permissions={member.data.permissions}
        />
      ) : (
        <p>当前成员没有业务助手读取权限。</p>
      )}
    </main>
  );
}
