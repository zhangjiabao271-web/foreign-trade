"use client";

import { useId, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { parseApiError, type components } from "@trade-workbench/api-client";
import { useMemberContext } from "../overview/api";
import { sessionClient, useSessionScope } from "../overview/session";

type Document = components["schemas"]["DocumentResponse"];
type Snapshot = components["schemas"]["DocumentReviewResponse"];
const schema = z.object({
  decision: z.enum(["release", "restrict"], { error: "请选择开放或保密。" }),
  reason: z.string().trim().min(3, "请填写至少 3 个字的审核说明。").max(1000),
  confirmed: z.boolean().refine(Boolean, "请确认已核对本版文件和开放范围。"),
});

function ReviewForm({
  documentId,
  snapshot,
  onChanged,
  onRecorded,
}: {
  documentId: string;
  snapshot: Snapshot;
  onChanged: () => Promise<unknown>;
  onRecorded: (message: string) => void;
}) {
  const id = useId();
  const retry = useRef<{ fingerprint: string; key: string }>(undefined);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
  });
  const pending = form.formState.isSubmitting;
  return (
    <form
      className="finance-form document-review-form"
      noValidate
      onSubmit={(event) =>
        form.handleSubmit(async (values) => {
          const body = {
            expected_version: snapshot.version,
            content_digest: snapshot.content_digest,
            release: values.decision === "release",
            reason: values.reason,
            confirmed: values.confirmed,
          };
          const fingerprint = JSON.stringify(body);
          if (retry.current?.fingerprint !== fingerprint)
            retry.current = { fingerprint, key: crypto.randomUUID() };
          onRecorded("");
          try {
            const result = await sessionClient().POST(
              "/api/v1/documents/{document_id}/versions/{version_id}/review",
              {
                params: {
                  header: { "idempotency-key": retry.current.key },
                  path: {
                    document_id: documentId,
                    version_id: snapshot.version_id,
                  },
                },
                body,
              },
            );
            if (!result.data)
              throw await parseApiError(result.response, result.error);
            onRecorded(
              result.data.released
                ? "本版已开放。"
                : "本版保持保密，停止签发普通角色下载链接。",
            );
            await onChanged();
          } catch {
            form.setError("root", {
              message:
                "审核未确认完成。请检查权限或刷新后重新核对；重复提交不会重复记录。",
            });
          }
        })(event)
      }
    >
      <fieldset disabled={pending}>
        <legend>本版开放范围</legend>
        <label htmlFor={`${id}-decision`}>审核决定</label>
        <select
          id={`${id}-decision`}
          {...form.register("decision")}
          aria-invalid={Boolean(form.formState.errors.decision)}
        >
          <option value="">请选择</option>
          <option value="release">开放：已确认不含成本或利润</option>
          <option value="restrict">保密：仅管理员、经理、财务查看</option>
        </select>
        {form.formState.errors.decision && (
          <p role="alert">{form.formState.errors.decision.message}</p>
        )}
        <label htmlFor={`${id}-reason`}>审核说明</label>
        <textarea
          id={`${id}-reason`}
          {...form.register("reason")}
          aria-invalid={Boolean(form.formState.errors.reason)}
        />
        {form.formState.errors.reason && (
          <p role="alert">{form.formState.errors.reason.message}</p>
        )}
        <label className="contract-confirm">
          <input type="checkbox" {...form.register("confirmed")} />
          我已核对本版文件内容、标题及文件名，确认以上开放范围。
        </label>
        {form.formState.errors.confirmed && (
          <p role="alert">{form.formState.errors.confirmed.message}</p>
        )}
        <button className="secondary-button" disabled={pending}>
          {pending ? "正在记录…" : "确认审核决定"}
        </button>
      </fieldset>
      {form.formState.errors.root && (
        <p role="alert">{form.formState.errors.root.message}</p>
      )}
    </form>
  );
}

function VersionReview({
  scope,
  documentId,
  versionId,
  onChanged,
}: {
  scope: string;
  documentId: string;
  versionId: string;
  onChanged: () => Promise<unknown>;
}) {
  const query = useQuery({
    queryKey: ["document-review", scope, documentId, versionId],
    retry: false,
    queryFn: async () => {
      const result = await sessionClient().GET(
        "/api/v1/documents/{document_id}/versions/{version_id}/review",
        {
          params: { path: { document_id: documentId, version_id: versionId } },
        },
      );
      if (!result.data)
        throw await parseApiError(result.response, result.error);
      return result.data;
    },
  });
  const [downloadError, setDownloadError] = useState(false);
  const [notice, setNotice] = useState("");
  return (
    <div>
      <button
        type="button"
        className="quiet-button"
        onClick={async () => {
          setDownloadError(false);
          try {
            const result = await sessionClient().POST(
              "/api/v1/documents/{document_id}/versions/{version_id}/download-session",
              {
                params: {
                  path: { document_id: documentId, version_id: versionId },
                },
              },
            );
            if (!result.data)
              throw await parseApiError(result.response, result.error);
            window.location.assign(result.data.download_url);
          } catch {
            setDownloadError(true);
          }
        }}
      >
        下载本版核对
      </button>
      {downloadError && (
        <p role="alert">下载未成功，请确认文件已完成校验及当前权限。</p>
      )}
      {query.isPending && <p role="status">正在读取本版审核状态…</p>}
      {query.isError && (
        <p role="alert">
          无法读取审核状态。
          <button onClick={() => query.refetch()}>重试</button>
        </p>
      )}
      {query.data && (
        <ReviewForm
          onRecorded={setNotice}
          key={`${versionId}:${query.data.version}:${query.data.content_digest}`}
          documentId={documentId}
          snapshot={query.data}
          onChanged={async () => {
            await onChanged();
            await query.refetch();
          }}
        />
      )}
      {notice && <p role="status">{notice}</p>}
    </div>
  );
}

export function DocumentReview({
  document,
  onChanged,
}: {
  document: Document;
  onChanged: () => Promise<unknown>;
}) {
  const scope = useSessionScope();
  const member = useMemberContext(scope);
  const [versionId, setVersionId] = useState<string>();
  const allowed =
    member.data?.permissions.includes("profit.read") &&
    member.data.permissions.includes("document.read");
  if (!allowed)
    return <p>未经审核的附件内容及名称保密，请联系管理员、经理或财务审核。</p>;
  return (
    <details className="document-version-history">
      <summary>审核文件开放范围</summary>
      <p>
        只开放核对过的具体版本；新版本须重新审核。撤回后，已签发链接最多仍可使用五分钟。
      </p>
      {(document.versions ?? []).map((version) => (
        <button
          key={version.id}
          type="button"
          className="quiet-button"
          onClick={() => setVersionId(version.id)}
        >
          审核第 {version.version_number} 版 ·{" "}
          {version.released ? "已开放" : "保密"}
        </button>
      ))}
      {versionId && (
        <VersionReview
          key={`${scope}:${document.id}:${versionId}`}
          scope={scope}
          documentId={document.id}
          versionId={versionId}
          onChanged={onChanged}
        />
      )}
    </details>
  );
}
