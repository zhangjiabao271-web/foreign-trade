"use client";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ApiClientError } from "@trade-workbench/api-client";
import {
  useDisclosureCommand,
  useDisclosures,
  type Disclosure,
} from "./disclosure-api";

function errorMessage(error: unknown) {
  if (error instanceof ApiClientError && error.problem.status === 409)
    return "草稿或审核状态已变化。请刷新并重新核对；不要把旧决定应用到新版本。";
  return "未能完成操作。请核对权限和连接，可原样重试上次操作。";
}

function Feedback({
  mutation,
}: {
  mutation: ReturnType<typeof useDisclosureCommand>;
}) {
  return (
    <>
      {mutation.isPending && <p role="status">正在记录内容审核操作…</p>}
      {mutation.isError && <p role="alert">{errorMessage(mutation.error)}</p>}
      {mutation.isSuccess && (
        <p role="status">内容审核操作已记录；未发送消息、未执行任务。</p>
      )}
      {mutation.isError && mutation.variables && (
        <button
          type="button"
          className="secondary-button"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate(mutation.variables!)}
        >
          原样重试上次操作
        </button>
      )}
    </>
  );
}

export function SubmitDisclosure({
  scope,
  id,
  version,
}: {
  scope: string;
  id: string;
  version: number;
}) {
  const mutation = useDisclosureCommand(scope);
  const [confirmed, setConfirmed] = useState(false);
  const [key] = useState(() => crypto.randomUUID());
  const busy = useRef(false);
  return (
    <section>
      <h3>主动提交这一条草稿</h3>
      <p>
        仅授权本空间管理员、经理或财务查看本次候选草稿，不开放其他对话或附件。内容审核不等于业务执行批准。
      </p>
      <label className="contract-confirm">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(event) => setConfirmed(event.target.checked)}
        />
        我同意将这一条草稿提交内容审核
      </label>
      <button
        type="button"
        className="secondary-button"
        disabled={!confirmed || mutation.isPending || mutation.isSuccess}
        onClick={async () => {
          if (busy.current) return;
          busy.current = true;
          try {
            await mutation.mutateAsync({
              action: "submit",
              id,
              key,
              body: { expected_version: version },
            });
          } catch {
            /* Feedback retains the exact retry. */
          } finally {
            busy.current = false;
          }
        }}
      >
        提交内容审核
      </button>
      <Feedback mutation={mutation} />
    </section>
  );
}

const revisionSchema = z.object({
  draft: z.string().max(5000),
  inferences: z
    .string()
    .refine(
      (value) => value.split("\n").filter(Boolean).length <= 8,
      "最多八条推断",
    ),
  task_title: z.string().max(240),
});
const decisionSchema = z.object({
  reason: z.string().trim().min(3, "请说明至少三个字的审核理由").max(1000),
  confirmed: z.boolean().refine(Boolean, "请确认已经核对完整候选内容"),
  release: z.enum(["release", "withhold"]),
});

function ReviewForms({ scope, row }: { scope: string; row: Disclosure }) {
  const mutation = useDisclosureCommand(scope);
  const busy = useRef(false);
  const revision = useForm<z.infer<typeof revisionSchema>>({
    resolver: zodResolver(revisionSchema),
    defaultValues: {
      draft: row.candidate?.draft ?? "",
      inferences: row.candidate?.inferences.join("\n") ?? "",
      task_title: row.candidate?.task_title ?? "",
    },
  });
  const decision = useForm<z.infer<typeof decisionSchema>>({
    resolver: zodResolver(decisionSchema),
    defaultValues: { reason: "", confirmed: false, release: "withhold" },
  });
  if (!row.candidate || !row.content_digest || !row.current) return null;
  const base = {
    id: row.id,
    body: { expected_version: row.version, content_digest: row.content_digest },
  };
  return (
    <>
      <form
        className="finance-form"
        onSubmit={(event) =>
          void revision.handleSubmit(async (value) => {
            if (busy.current) return;
            busy.current = true;
            try {
              await mutation.mutateAsync({
                action: "revise",
                id: base.id,
                key: crypto.randomUUID(),
                body: {
                  ...base.body,
                  candidate: {
                    draft: value.draft,
                    inferences: value.inferences.split("\n").filter(Boolean),
                    task_title: value.task_title || null,
                  },
                },
              });
            } catch {
              /* Show error and exact retry. */
            } finally {
              busy.current = false;
            }
          })(event)
        }
      >
        <h4>追加脱敏候选版本</h4>
        <p>
          这里的编辑不会改变上方待决定的版本。保存为新候选后，须再次核对并批准；原稿永久保留。
        </p>
        <label>
          脱敏草稿
          <textarea rows={6} {...revision.register("draft")} />
        </label>
        <label>
          脱敏推断（每行一条）
          <textarea rows={3} {...revision.register("inferences")} />
        </label>
        <label>
          脱敏任务标题
          <input {...revision.register("task_title")} />
        </label>
        {Object.values(revision.formState.errors).map((error, i) => (
          <p key={i} role="alert">
            {error.message}
          </p>
        ))}
        <button className="secondary-button" disabled={mutation.isPending}>
          保存新候选，重新审核
        </button>
      </form>
      <form
        className="finance-form"
        onSubmit={(event) =>
          void decision.handleSubmit(async (value) => {
            if (busy.current) return;
            busy.current = true;
            try {
              await mutation.mutateAsync({
                action: "decide",
                id: base.id,
                key: crypto.randomUUID(),
                body: {
                  ...base.body,
                  reason: value.reason,
                  confirmed: value.confirmed,
                  release: value.release === "release",
                },
              });
            } catch {
              /* Show error and exact retry. */
            } finally {
              busy.current = false;
            }
          })(event)
        }
      >
        <h4>决定上方候选版本的可见性</h4>
        <label>
          内容决定
          <select {...decision.register("release")}>
            <option value="withhold">保持保密／撤回开放</option>
            <option value="release">确认无成本利润，向原创建者开放</option>
          </select>
        </label>
        <label>
          内容审核理由
          <input {...decision.register("reason")} />
        </label>
        <label className="contract-confirm">
          <input type="checkbox" {...decision.register("confirmed")} />
          我已核对上方完整候选；若开放，确认不含成本或利润
        </label>
        {Object.values(decision.formState.errors).map((error, i) => (
          <p key={i} role="alert">
            {error.message}
          </p>
        ))}
        <button className="primary-button" disabled={mutation.isPending}>
          记录内容决定
        </button>
      </form>
      <Feedback mutation={mutation} />
    </>
  );
}

export function DisclosureQueue({
  scope,
  reviewer,
}: {
  scope: string;
  reviewer: boolean;
}) {
  const [cursor, setCursor] = useState<string>();
  const query = useDisclosures(scope, cursor);
  return (
    <section className="finance-section">
      <h2>草稿内容审核 · 不执行业务</h2>
      <p>
        {reviewer
          ? "仅展示主动提交的候选版本，不授予查看其他私有运行的权限。"
          : "仅展示你主动提交的草稿；未经审核的正文仍保密。"}
      </p>
      {query.isPending && <p role="status">正在读取提交记录…</p>}
      {query.isError && <p role="alert">读取失败，请刷新审核记录。</p>}
      {query.data?.items.length === 0 && <p>暂无主动提交的草稿。</p>}
      {query.data?.items.map((row) => (
        <article key={`${row.id}:${row.version}`} className="finance-section">
          <h3>候选版本 {row.revision}</h3>
          <p style={{ overflowWrap: "anywhere" }}>草稿记录：{row.run_id}</p>
          <p>
            状态：
            {
              (
                {
                  PENDING: "待内容审核",
                  APPROVED: "已审核开放",
                  REJECTED: "保持保密",
                } as Record<string, string>
              )[row.status]
            }
            {!row.current && " · 历史或内容已变化，不再生效"}
          </p>
          {row.candidate ? (
            <>
              <h4>本次完整候选内容</h4>
              <ul>
                {row.candidate.inferences.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
              <p className="copilot-draft">{row.candidate.draft}</p>
              {row.candidate.task_title && (
                <p>候选任务标题：{row.candidate.task_title}</p>
              )}
            </>
          ) : (
            <p>候选正文受保护。</p>
          )}
          {reviewer && <ReviewForms scope={scope} row={row} />}
        </article>
      ))}
      <button
        className="secondary-button"
        onClick={() => {
          setCursor(undefined);
          void query.refetch();
        }}
      >
        刷新内容审核记录
      </button>
      <button
        className="secondary-button"
        disabled={!query.data?.has_more || query.isFetching}
        onClick={() => setCursor(query.data?.next_cursor ?? undefined)}
      >
        更早提交版本
      </button>
    </section>
  );
}
