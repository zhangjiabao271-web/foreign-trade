"use client";

import { useId, useRef } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ApiClientError, type components } from "@trade-workbench/api-client";
import { sessionClient, useSessionScope } from "../overview/session";
import { resumeDocumentUpload } from "./transfer";

type Document = components["schemas"]["DocumentResponse"];
type Version = components["schemas"]["DocumentVersionResponse"];
const schema = z.object({
  files: z
    .custom<FileList>()
    .refine(
      (files) =>
        files?.length === 1 &&
        files[0].size > 0 &&
        files[0].size <= 25 * 1024 * 1024,
      "请选择原来的非空文件（最大 25 MB）。",
    ),
});

function recoveryError(error: unknown) {
  if (error instanceof ApiClientError) {
    switch (error.problem.code) {
      case "UPLOAD_FILE_MISMATCH":
        return "文件不匹配，请重新选择原来的文件；名称、类型、大小和内容都必须一致。";
      case "UPLOAD_VERSION_SUPERSEDED":
        return "已有更新版本，请刷新文件清单后继续。";
      case "DOCUMENT_TARGET_FINALIZED":
        return "业务已终结，不能继续上传。请刷新查看当前文件状态。";
      case "INVALID_DOCUMENT_STATE":
        return "该版本不可续传，请刷新清单并查看文件状态。";
    }
    if ([401, 403, 404].includes(error.problem.status))
      return "当前会话无法访问此文件，请确认登录、组织和文件权限。";
  }
  return "续传未确认成功，请检查连接后重试；不会新建文件版本。";
}

function ResumeForm({
  documentId,
  version,
  disabled,
  onRecovered,
}: {
  documentId: string;
  version: Version;
  disabled: boolean;
  onRecovered: () => Promise<unknown>;
}) {
  const id = useId();
  const busy = useRef(false);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
  });
  const pending = form.formState.isSubmitting;
  return (
    <form
      className="document-resume"
      aria-label={`继续上传 ${version.file_name ?? "待审核附件"}`}
      data-document-version-id={version.id}
      aria-busy={pending}
      noValidate
      onSubmit={(event) =>
        form.handleSubmit(async ({ files }) => {
          if (disabled || busy.current) return;
          busy.current = true;
          const client = sessionClient();
          try {
            await resumeDocumentUpload(
              client,
              documentId,
              version.id,
              files[0],
            );
            await onRecovered();
          } catch (error) {
            form.setError("files", { message: recoveryError(error) });
          } finally {
            busy.current = false;
          }
        })(event)
      }
    >
      <p id={`${id}-hint`}>
        第 {version.version_number} 版尚未上传完成。重新选择原文件{" "}
        {version.file_name ?? "（文件名保密）"}（{version.expected_size_bytes}{" "}
        字节）继续，不会新建版本。
      </p>
      <label htmlFor={id}>重新选择原文件</label>
      <input
        id={id}
        type="file"
        {...form.register("files")}
        disabled={disabled || pending}
        aria-invalid={Boolean(form.formState.errors.files)}
        aria-describedby={`${id}-hint ${id}-error`}
        required
      />
      {form.formState.errors.files && (
        <p id={`${id}-error`} className="form-error" role="alert">
          {form.formState.errors.files.message}
        </p>
      )}
      <button className="secondary-button" disabled={disabled || pending}>
        {pending ? "续传并校验中…" : "继续上传原文件"}
      </button>
    </form>
  );
}

export function ResumeUpload({
  document,
  disabled = false,
  onRecovered,
}: {
  document: Document;
  disabled?: boolean;
  onRecovered: () => Promise<unknown>;
}) {
  const scope = useSessionScope();
  const version = document.versions?.find(
    (item) => item.version_number === document.latest_version_number,
  );
  if (!scope || version?.status !== "PENDING_UPLOAD") return null;
  return (
    <ResumeForm
      key={`${scope}:${version.id}`}
      documentId={document.id}
      version={version}
      disabled={disabled}
      onRecovered={onRecovered}
    />
  );
}
