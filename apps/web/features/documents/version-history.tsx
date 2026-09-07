"use client";

import type { components } from "@trade-workbench/api-client";

export function DocumentVersionHistory({
  document,
  pending,
  onDownload,
}: {
  document: components["schemas"]["DocumentResponse"];
  pending: boolean;
  onDownload: (versionId: string) => void;
}) {
  const history = (document.versions ?? [])
    .filter(
      (version) => version.version_number !== document.latest_version_number,
    )
    .sort((a, b) => b.version_number - a.version_number);
  if (!history.length) return null;
  return (
    <details className="document-version-history">
      <summary>
        历史版本 · {document.title ?? "待审核附件"}（{history.length}）
      </summary>
      <p>历史证据只读保留，不替代当前版本的文件清单要求。</p>
      <ul>
        {history.map((version) => (
          <li key={version.id}>
            <span>
              第 {version.version_number} 版 ·{" "}
              {version.file_name ?? "文件名保密"}
            </span>
            {version.status === "AVAILABLE" && version.content_visible ? (
              <button
                type="button"
                className="quiet-button"
                disabled={pending}
                onClick={() => onDownload(version.id)}
              >
                {pending ? "正在授权…" : `下载第 ${version.version_number} 版`}
              </button>
            ) : (
              <span>尚未通过校验或开放审核，不可下载</span>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}
