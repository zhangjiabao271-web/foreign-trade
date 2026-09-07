"use client";

import { WorkTextReview } from "../finance/work-review";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ApiClientError, type components } from "@trade-workbench/api-client";
import { useMemberContext } from "../overview/api";
import { WorkspaceConnection } from "../overview/overview-workspace";
import {
  useSessionScope,
  disconnectSession,
  sessionClient,
} from "../overview/session";
import { parseApiError } from "@trade-workbench/api-client";
import { useMutation } from "@tanstack/react-query";
import { refundDifference } from "./amounts";
import { DocumentVersionHistory } from "../documents/version-history";
import { ResumeUpload } from "../documents/resume-upload";
import { DocumentReview } from "../documents/review";
import {
  useCases,
  useRefreshExport,
  useExportCase,
  useCreateCase,
  useCaseCommand,
  useCaseActivities,
  useCaseDocuments,
  useCaseUpload,
  useScheduleFollowUp,
  type CaseKind,
  type ExportCase,
  type CaseAction,
} from "./api";

const labels: Record<string, string> = {
  DRAFT: "草稿",
  NOT_READY: "待准备",
  DOCUMENTS_PENDING: "待补文件",
  READY: "资料就绪",
  SUBMITTED: "已记录人工申报",
  CLEARED: "已清关",
  PROCESSING: "办理中",
  REFUNDED: "已收到退税",
  REJECTED: "已拒绝",
};
const documents = {
  COMMERCIAL_INVOICE: "商业发票",
  SALES_CONTRACT: "销售合同",
  PACKING_LIST: "装箱单",
  BILL_OF_LADING: "提单",
  CERTIFICATE_OF_ORIGIN: "原产地证",
  BOOKING_CONFIRMATION: "订舱确认",
  OTHER: "其他文件",
} as const;
const documentStates: Record<string, string> = {
  PENDING_UPLOAD: "等待上传",
  UPLOADED: "等待扫描",
  SCANNING: "扫描中",
  AVAILABLE: "可用",
  REJECTED: "已拒绝",
};
const actions: Record<CaseAction, string> = {
  prepare: "开始准备资料",
  ready: "确认资料就绪",
  submit: "记录人工申报",
  clear: "记录清关",
  process: "记录办理中",
  receive: "记录收到退税",
  reject: "记录拒绝",
};
function title(row: ExportCase) {
  return "declaration_number" in row ? row.declaration_number : row.case_number;
}
function problem(error: unknown) {
  if (error instanceof ApiClientError) {
    if (error.problem.status === 403) return "当前成员没有此操作权限。";
    if (error.problem.status === 401) return "访问凭证已失效，请重新连接。";
    if (error.problem.status === 404) return "当前组织中找不到此案件。";
    if (error.problem.code === "EXPORT_DOCUMENTS_INCOMPLETE")
      return "必需文件尚未齐备或扫描未完成，请补齐后重试。";
    if (error.problem.code === "VERSION_CONFLICT")
      return "案件已更新，请关闭表单并重新打开。";
    return `${error.problem.detail}（${error.problem.code}）`;
  }
  return "操作未成功，请检查服务连接后重试。";
}
function Validation({ message }: { message?: string }) {
  return message ? <p role="alert">{message}</p> : null;
}
const money = z
  .string()
  .regex(/^\d{1,14}(\.\d{1,4})?$/, "金额最多保留四位小数")
  .refine((value) => /[1-9]/.test(value), "金额必须大于零");
const createSchema = z.object({
  parentId: z.uuid("请输入有效的关联 ID"),
  amount: money,
  currency: z.string().regex(/^[A-Z]{3}$/, "请输入三位币种代码"),
  followUp: z.string(),
  notes: z.string().max(2000),
});

function CreateCase({ kind }: { kind: CaseKind }) {
  const mutation = useCreateCase();
  const router = useRouter();
  const [key] = useState(() => crypto.randomUUID());
  const form = useForm<z.infer<typeof createSchema>>({
    resolver: zodResolver(createSchema),
    defaultValues: {
      parentId: "",
      amount: "",
      currency: "USD",
      followUp: "",
      notes: "",
    },
  });
  return (
    <details className="finance-section">
      <summary>新建{kind === "customs" ? "报关" : "退税"}案件</summary>
      <form
        className="finance-form"
        onSubmit={form.handleSubmit(async (value) => {
          const common = {
            follow_up_date: value.followUp || null,
            notes: value.notes || null,
          };
          try {
            const row = await mutation.mutateAsync(
              kind === "customs"
                ? {
                    kind,
                    key,
                    body: {
                      ...common,
                      shipment_id: value.parentId,
                      declared_amount: value.amount,
                      currency_code: value.currency,
                    },
                  }
                : {
                    kind,
                    key,
                    body: {
                      ...common,
                      customs_declaration_id: value.parentId,
                      expected_amount: value.amount,
                    },
                  },
            );
            router.push(`/export/${kind}/${row.id}`);
          } catch {
            /* The mutation error is displayed below. */
          }
        })}
      >
        <label>
          {kind === "customs" ? "出货 ID" : "报关案件 ID"}
          <input {...form.register("parentId")} />
        </label>
        <Validation message={form.formState.errors.parentId?.message} />
        <label>
          {kind === "customs" ? "人工申报金额" : "预计退税金额"}
          <input inputMode="decimal" {...form.register("amount")} />
        </label>
        <Validation message={form.formState.errors.amount?.message} />
        {kind === "customs" ? (
          <>
            <label>
              币种
              <input {...form.register("currency")} />
            </label>
            <Validation message={form.formState.errors.currency?.message} />
          </>
        ) : (
          <p>币种沿用报关案件。预计金额由人工核定，系统不计算法定应退额度。</p>
        )}
        <label>
          跟进日期
          <input type="date" {...form.register("followUp")} />
        </label>
        <label>
          备注
          <textarea {...form.register("notes")} />
        </label>
        <Validation message={form.formState.errors.notes?.message} />
        <p>
          默认清单：{kind === "customs" ? "商业发票、装箱单" : "商业发票、提单"}
          。这是作业证据清单，不代表满足法定申报要求。
        </p>
        {mutation.isError && <p role="alert">{problem(mutation.error)}</p>}
        <button className="primary-button" disabled={mutation.isPending}>
          {" "}
          {mutation.isPending ? "正在创建…" : "创建人工跟踪案件"}
        </button>
      </form>
    </details>
  );
}

function CaseList({
  kind,
  scope,
  canWrite,
}: {
  kind: CaseKind;
  scope: string;
  canWrite: boolean;
}) {
  const [cursors, setCursors] = useState<Array<string | undefined>>([
    undefined,
  ]);
  const query = useCases(scope, kind, cursors.at(-1));
  return (
    <>
      {canWrite && <CreateCase kind={kind} />}
      <section className="action-queue">
        <h2>案件列表</h2>
        {query.isPending && <p role="status">正在读取案件…</p>}
        {query.isError && <p role="alert">{problem(query.error)}</p>}
        <button
          className="secondary-button"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          刷新案件
        </button>
        {query.data?.items.length === 0 && (
          <p>暂无案件。适用时可从出货建立人工报关记录。</p>
        )}
        <ul>
          {query.data?.items.map((row) => (
            <li key={row.id}>
              <Link href={`/export/${kind}/${row.id}`}>
                <strong>{title(row)}</strong>
                <span>{labels[row.status]}</span>
              </Link>
              <p>
                缺少文件：
                {row.missing_document_types
                  ?.map((value) => documents[value])
                  .join("、") || "无"}
              </p>
            </li>
          ))}
        </ul>
        <nav className="queue-pagination" aria-label="案件分页">
          <button
            className="secondary-button"
            disabled={cursors.length === 1 || query.isFetching}
            onClick={() => setCursors(cursors.slice(0, -1))}
          >
            上一页
          </button>
          <button
            className="secondary-button"
            disabled={!query.data?.has_more || query.isFetching}
            onClick={() =>
              setCursors([...cursors, query.data?.next_cursor ?? undefined])
            }
          >
            下一页
          </button>
        </nav>
      </section>
    </>
  );
}

function FollowUpForm({ kind, row }: { kind: CaseKind; row: ExportCase }) {
  const schema = z.object({
    date: z
      .string()
      .refine(
        (value) => !value || z.iso.date().safeParse(value).success,
        "请选择跟进日期",
      ),
    reason: z.string().trim().min(3, "请填写至少三个字的调整原因"),
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { date: row.follow_up_date ?? "", reason: "" },
  });
  const mutation = useScheduleFollowUp(kind, row.id);
  const [version] = useState(row.version);
  return (
    <form
      className="finance-form"
      onSubmit={form.handleSubmit(async (value) => {
        try {
          await mutation.mutateAsync({
            expected_version: version,
            follow_up_date: value.date || null,
            reason: value.reason,
          });
        } catch {
          /* Show command failure. */
        }
      })}
    >
      <h3>安排下一次跟进</h3>
      <label>
        新的跟进日期
        <input type="date" {...form.register("date")} />
      </label>
      <p>留空仅移除日期提醒，案件仍在行动队列中。</p>
      <Validation message={form.formState.errors.date?.message} />
      <label>
        调整原因
        <textarea {...form.register("reason")} />
      </label>
      <Validation message={form.formState.errors.reason?.message} />
      {mutation.isError && <p role="alert">{problem(mutation.error)}</p>}
      <button className="secondary-button" disabled={mutation.isPending}>
        保存跟进安排
      </button>
    </form>
  );
}

function nextActions(row: ExportCase): CaseAction[] {
  switch (row.status) {
    case "DRAFT":
    case "NOT_READY":
      return ["prepare"];
    case "DOCUMENTS_PENDING":
      return ["ready"];
    case "READY":
      return ["submit"];
    case "SUBMITTED":
      return "shipment_id" in row ? ["clear", "reject"] : ["process"];
    case "PROCESSING":
      return ["receive", "reject"];
    default:
      return [];
  }
}
function CommandForm({
  kind,
  row,
  action,
  close,
}: {
  kind: CaseKind;
  row: ExportCase;
  action: CaseAction;
  close: () => void;
}) {
  const needsDate = ["submit", "clear", "receive"].includes(action);
  const [expectedVersion] = useState(row.version);
  const schema = z.object({
    reason:
      action === "reject"
        ? z.string().trim().min(3, "请填写至少三个字的原因")
        : z
            .string()
            .refine(
              (value) => !value || value.trim().length >= 3,
              "原因至少三个字",
            ),
    date: needsDate ? z.iso.date("请选择实际发生日期") : z.string(),
    reference:
      action === "submit"
        ? z.string().trim().min(1, "请填写人工申报回执号")
        : z.string(),
    amount: action === "receive" ? money : z.string(),
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { reason: "", date: "", reference: "", amount: "" },
  });
  const mutation = useCaseCommand(kind, row.id);
  return (
    <form
      className="finance-form"
      onSubmit={form.handleSubmit(async (value) => {
        try {
          await mutation.mutateAsync({
            action,
            fact: {
              expected_version: expectedVersion,
              reason: value.reason,
              occurred_on: value.date,
              external_reference: value.reference,
              refunded_amount: value.amount,
            },
          });
          close();
        } catch {
          /* Show mutation feedback. */
        }
      })}
    >
      <h3>{actions[action]}</h3>
      <p>仅保存你已核实的人工办理事实，不向外部机关提交。</p>
      {needsDate && (
        <>
          <label>
            实际发生日期
            <input type="date" {...form.register("date")} />
          </label>
          <Validation message={form.formState.errors.date?.message} />
        </>
      )}
      {action === "submit" && (
        <>
          <label>
            人工申报回执号
            <input {...form.register("reference")} />
          </label>
          <Validation message={form.formState.errors.reference?.message} />
        </>
      )}
      {action === "receive" && (
        <>
          <label>
            实际收到退税金额
            <input inputMode="decimal" {...form.register("amount")} />
          </label>
          <Validation message={form.formState.errors.amount?.message} />
          <p>此操作结案。若实际金额小于预计金额，差额仍保留，不会自动补齐。</p>
        </>
      )}
      <label>
        原因／说明
        <textarea {...form.register("reason")} />
      </label>
      <Validation message={form.formState.errors.reason?.message} />
      {mutation.isError && <p role="alert">{problem(mutation.error)}</p>}
      <div className="queue-pagination">
        <button className="primary-button" disabled={mutation.isPending}>
          {mutation.isPending ? "正在记录…" : `确认${actions[action]}`}
        </button>
        <button
          className="secondary-button"
          type="button"
          disabled={mutation.isPending}
          onClick={close}
        >
          取消
        </button>
      </div>
    </form>
  );
}

const uploadSchema = z.object({
  documentType: z.enum([
    "SALES_CONTRACT",
    "COMMERCIAL_INVOICE",
    "PACKING_LIST",
    "BILL_OF_LADING",
    "CERTIFICATE_OF_ORIGIN",
    "BOOKING_CONFIRMATION",
    "OTHER",
  ]),
  file: z
    .custom<FileList>()
    .refine((files) => files?.length === 1, "请选择一个文件")
    .refine(
      (files) =>
        !files?.[0] || (files[0].size > 0 && files[0].size <= 25 * 1024 * 1024),
      "文件须大于零且不超过 25 MB",
    ),
});
function CaseDocuments({
  scope,
  kind,
  id,
  canWrite,
}: {
  scope: string;
  kind: CaseKind;
  id: string;
  canWrite: boolean;
}) {
  const query = useCaseDocuments(scope, kind, id);
  const refresh = useRefreshExport();
  const upload = useCaseUpload(kind, id);
  const [replacement, setReplacement] = useState<{
    documentId: string;
    expectedVersion: number;
    title: string;
  }>();
  const form = useForm<z.infer<typeof uploadSchema>>({
    resolver: zodResolver(uploadSchema),
    defaultValues: { documentType: "COMMERCIAL_INVOICE" },
  });
  const download = useMutation({
    mutationFn: async ({
      documentId,
      versionId,
    }: {
      documentId: string;
      versionId?: string;
    }) => {
      const r = versionId
        ? await sessionClient().POST(
            "/api/v1/documents/{document_id}/versions/{version_id}/download-session",
            {
              params: {
                path: { document_id: documentId, version_id: versionId },
              },
            },
          )
        : await sessionClient().POST(
            "/api/v1/documents/{document_id}/download-session",
            { params: { path: { document_id: documentId } } },
          );
      if (!r.data) throw await parseApiError(r.response, r.error);
      window.location.assign(r.data.download_url);
    },
  });
  return (
    <section className="finance-section">
      <h2>案件证据文件</h2>
      <p>上传完成后等待扫描；仅“可用”的当前版本满足清单。</p>
      {query.isPending && <p role="status">正在读取文件…</p>}
      {query.isError && <p role="alert">{problem(query.error)}</p>}
      <ul>
        {query.data?.items.map((doc) => (
          <li key={doc.id}>
            {documents[doc.document_type]} · {doc.title ?? "待审核附件"} ·{" "}
            {
              documentStates[
                doc.versions?.find(
                  (version) =>
                    version.version_number === doc.latest_version_number,
                )?.status ?? "PENDING_UPLOAD"
              ]
            }
            <button
              className="secondary-button"
              disabled={
                download.isPending ||
                !doc.versions?.find(
                  (v) => v.version_number === doc.latest_version_number,
                )?.content_visible
              }
              onClick={() => download.mutate({ documentId: doc.id })}
            >
              下载 {doc.title ?? "待审核附件"}
            </button>
            <DocumentVersionHistory
              document={doc}
              pending={download.isPending}
              onDownload={(versionId) =>
                download.mutate({ documentId: doc.id, versionId })
              }
            />
            <DocumentReview document={doc} onChanged={refresh} />
            {canWrite && (
              <ResumeUpload
                document={doc}
                disabled={upload.isPending}
                onRecovered={refresh}
              />
            )}
            {canWrite && (
              <button
                className="secondary-button"
                disabled={upload.isPending}
                onClick={() => {
                  setReplacement({
                    documentId: doc.id,
                    expectedVersion: doc.version,
                    title: doc.title ?? "待审核附件",
                  });
                  form.setValue("documentType", doc.document_type);
                }}
              >
                替换文件 {doc.title}
              </button>
            )}
          </li>
        ))}
      </ul>
      {download.isError && <p role="alert">{problem(download.error)}</p>}
      {canWrite && (
        <form
          className="finance-form"
          onSubmit={form.handleSubmit(async (value) => {
            try {
              await upload.mutateAsync({
                file: value.file[0]!,
                documentType: value.documentType,
                replacement,
              });
              form.reset();
              setReplacement(undefined);
            } catch {
              /* Show upload feedback. */
            }
          })}
        >
          {replacement && (
            <p>
              为 {replacement.title} 新建版本，旧版本与证据保留。
              <button
                type="button"
                className="secondary-button"
                disabled={upload.isPending}
                onClick={() => setReplacement(undefined)}
              >
                取消替换
              </button>
            </p>
          )}
          <label>
            文件类型
            <select {...form.register("documentType")}>
              {Object.entries(documents).map(([value, label]) => (
                <option
                  key={value}
                  value={value}
                  disabled={
                    Boolean(replacement) &&
                    value !== form.getValues("documentType")
                  }
                >
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            选择证据文件
            <input type="file" {...form.register("file")} />
          </label>
          <Validation message={form.formState.errors.file?.message} />
          {upload.isError && <p role="alert">{problem(upload.error)}</p>}
          {upload.isSuccess && <p role="status">上传已记录，等待扫描结果。</p>}
          <button className="primary-button" disabled={upload.isPending}>
            {upload.isPending ? "正在上传…" : "上传案件文件"}
          </button>
        </form>
      )}
    </section>
  );
}
function Timeline({
  scope,
  kind,
  id,
}: {
  scope: string;
  kind: CaseKind;
  id: string;
}) {
  const [cursor, setCursor] = useState<string>();
  const query = useCaseActivities(scope, kind, id, cursor);
  return (
    <section className="finance-section">
      <h2>案件时间线</h2>
      {query.isPending && <p role="status">正在读取时间线…</p>}
      {query.isError && <p role="alert">{problem(query.error)}</p>}
      <ol className="finance-timeline">
        {query.data?.items.map((item) => (
          <li key={item.id}>
            <time>{new Date(item.occurred_at).toLocaleString("zh-CN")}</time>
            <p>{item.summary ?? "保密活动：待审核后开放"}</p>
            <WorkTextReview
              subjectType={
                kind === "customs" ? "customs_declaration" : "tax_refund_case"
              }
              subjectId={id}
              recordId={item.id}
              onChanged={() => query.refetch()}
            />
          </li>
        ))}
      </ol>
      <div className="queue-pagination">
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
          disabled={!query.data?.has_more || query.isFetching}
          onClick={() => setCursor(query.data?.next_cursor ?? undefined)}
        >
          更早记录
        </button>
      </div>
    </section>
  );
}
function CaseDetail({
  scope,
  kind,
  id,
  permissions,
}: {
  scope: string;
  kind: CaseKind;
  id: string;
  permissions: components["schemas"]["Permission"][];
}) {
  const query = useExportCase(scope, kind, id);
  const [action, setAction] = useState<CaseAction>();
  if (query.isPending) return <p role="status">正在读取案件…</p>;
  if (query.isError)
    return (
      <section role="alert">
        <p>{problem(query.error)}</p>
        <button
          className="secondary-button"
          onClick={() => void query.refetch()}
        >
          重试
        </button>
      </section>
    );
  const row = query.data;
  return (
    <>
      <section className="finance-section">
        <h2>{title(row)}</h2>
        <p>状态：{labels[row.status]}</p>
        <p>案件 ID：{row.id}</p>
        {"shipment_id" in row ? (
          <>
            <Link href={`/shipments/${row.shipment_id}`}>查看关联出货</Link>
            <p>
              人工申报金额：{row.declared_amount} {row.currency_code}
            </p>
            <p>清关日期：{row.cleared_on ?? "尚未记录"}</p>
          </>
        ) : (
          <>
            <Link href={`/export/customs/${row.customs_declaration_id}`}>
              查看关联报关
            </Link>
            <p>
              预计退税：{row.expected_amount} {row.currency_code} · 实收退税：
              {row.refunded_amount} {row.currency_code}
            </p>
            <p>
              预计与实收差额：
              {refundDifference(row.expected_amount, row.refunded_amount)}{" "}
              {row.currency_code}（仅展示差额，不推定应补退权益）
            </p>
            <p>实际退税日期：{row.refunded_on ?? "尚未记录"}</p>
          </>
        )}
        <p>跟进日期：{row.follow_up_date ?? "未安排"}</p>
        <p>
          人工申报日期：{row.submitted_on ?? "尚未记录"} · 回执号：
          {row.external_reference ?? "尚未记录"}
        </p>
        <p>
          缺少文件：
          {row.missing_document_types
            ?.map((value) => documents[value])
            .join("、") || "无"}
        </p>
        {permissions.includes("export.write") && (
          <div className="queue-pagination">
            {nextActions(row).map((value) => (
              <button
                className="secondary-button"
                key={value}
                disabled={Boolean(action)}
                onClick={() => setAction(value)}
              >
                {actions[value]}
              </button>
            ))}
          </div>
        )}
        {action && (
          <CommandForm
            key={action}
            kind={kind}
            row={row}
            action={action}
            close={() => setAction(undefined)}
          />
        )}
      </section>
      <section className="finance-section" aria-label="案件备注审核">
        <h2>案件备注与退回原因</h2>
        {row.content_visible ? (
          <>
            <p>备注：{row.notes ?? "未填写"}</p>
            <p>退回原因：{row.rejection_reason ?? "未填写"}</p>
          </>
        ) : (
          <p>保密内容：待审核后开放</p>
        )}
        <WorkTextReview
          exportKind={kind === "customs" ? "customs" : "refund"}
          recordId={id}
          onChanged={() => query.refetch()}
        />
      </section>
      {permissions.includes("export.write") && nextActions(row).length > 0 && (
        <FollowUpForm key={row.version} kind={kind} row={row} />
      )}
      {permissions.includes("document.read") ? (
        <CaseDocuments
          scope={scope}
          kind={kind}
          id={id}
          canWrite={
            permissions.includes("document.write") &&
            nextActions(row).length > 0
          }
        />
      ) : (
        <p>无文件查看权限。</p>
      )}
      <Timeline scope={scope} kind={kind} id={id} />
    </>
  );
}
function ConnectedExport({
  scope,
  kind,
  id,
}: {
  scope: string;
  kind: CaseKind;
  id?: string;
}) {
  const member = useMemberContext(scope);
  if (member.isPending) return <p role="status">正在核对权限…</p>;
  if (member.isError)
    return (
      <section role="alert">
        <p>{problem(member.error)}</p>
        <button className="secondary-button" onClick={disconnectSession}>
          重新连接
        </button>
      </section>
    );
  if (!member.data.permissions.includes("export.read"))
    return <p role="alert">当前成员无案件查看权限。</p>;
  return id ? (
    <CaseDetail
      scope={scope}
      kind={kind}
      id={id}
      permissions={member.data.permissions}
    />
  ) : (
    <CaseList
      scope={scope}
      kind={kind}
      canWrite={member.data.permissions.includes("export.write")}
    />
  );
}
export function ExportWorkspace({ kind, id }: { kind: CaseKind; id?: string }) {
  const scope = useSessionScope();
  return (
    <main id="main-content" className="overview-shell">
      <header className="topbar">
        <Link className="brand" href="/">
          外贸工作台
        </Link>
        <nav className="overview-nav" aria-label="案件导航">
          <Link href="/">行动首页</Link>
          <Link href="/export/customs">报关案件</Link>
          <Link href="/export/refunds">退税案件</Link>
        </nav>
      </header>
      <section className="overview-heading">
        <p className="section-kicker">人工作业记录</p>
        <h1>{kind === "customs" ? "报关" : "退税"}案件跟踪</h1>
        <p>记录人工办理进度、日期、金额和证据。本系统不对接政府申报接口。</p>
      </section>
      {scope ? (
        <ConnectedExport
          key={`${scope}:${kind}:${id}`}
          scope={scope}
          kind={kind}
          id={id}
        />
      ) : (
        <WorkspaceConnection />
      )}
    </main>
  );
}
