import {
  createTradeApiClient,
  parseApiError,
  type components,
} from "@trade-workbench/api-client";

type Upload = components["schemas"]["DocumentUploadCreate"];

export type UploadRetry = {
  attempt?: { fingerprint: string; key: string };
};

async function fileMetadata(file: File) {
  const hash = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return {
    file_name: file.name,
    mime_type: file.type || "application/octet-stream",
    size_bytes: file.size,
    sha256: Array.from(new Uint8Array(hash), (value) =>
      value.toString(16).padStart(2, "0"),
    ).join(""),
  };
}

export async function resumeDocumentUpload(
  client: ReturnType<typeof createTradeApiClient>,
  documentId: string,
  versionId: string,
  file: File,
) {
  const metadata = await fileMetadata(file);
  const result = await client.POST(
    "/api/v1/documents/{document_id}/versions/{version_id}/upload-session",
    {
      params: { path: { document_id: documentId, version_id: versionId } },
      body: metadata,
    },
  );
  if (!result.data) throw await parseApiError(result.response, result.error);
  return transferUpload(client, result.data, file, metadata.mime_type);
}

export async function uploadDocument(
  client: ReturnType<typeof createTradeApiClient>,
  input: {
    file: File;
    documentType: Upload["document_type"];
    targetType: Upload["target_type"];
    targetId: string;
    replacement?: { documentId: string; expectedVersion: number };
  },
  retry: UploadRetry = {},
) {
  const metadata = await fileMetadata(input.file);
  const fingerprint = JSON.stringify({
    ...metadata,
    documentType: input.documentType,
    targetType: input.targetType,
    targetId: input.targetId,
    replacement: input.replacement,
  });
  if (retry.attempt?.fingerprint !== fingerprint) {
    retry.attempt = { fingerprint, key: crypto.randomUUID() };
  }
  const headers = { "Idempotency-Key": retry.attempt.key };
  const result = input.replacement
    ? await client.POST(
        "/api/v1/documents/{document_id}/version-upload-sessions",
        {
          headers,
          params: { path: { document_id: input.replacement.documentId } },
          body: {
            ...metadata,
            expected_version: input.replacement.expectedVersion,
          },
        },
      )
    : await client.POST("/api/v1/documents/upload-sessions", {
        headers,
        body: {
          ...metadata,
          title: input.file.name,
          document_type: input.documentType,
          target_type: input.targetType,
          target_id: input.targetId,
        },
      });
  if (!result.data) throw await parseApiError(result.response, result.error);
  const document = await transferUpload(
    client,
    result.data,
    input.file,
    metadata.mime_type,
  );
  retry.attempt = undefined;
  return document;
}

async function transferUpload(
  client: ReturnType<typeof createTradeApiClient>,
  upload: components["schemas"]["UploadSessionResponse"],
  file: File,
  mime: string,
) {
  if (upload.upload_url === null) {
    return upload.document;
  }
  const put = await fetch(upload.upload_url, {
    method: "PUT",
    headers: { "Content-Type": mime },
    body: file,
  });
  if (!put.ok) throw new Error(`文件上传失败（${put.status}）`);
  const completed = await client.POST(
    "/api/v1/documents/{document_id}/versions/{version_id}/complete",
    {
      params: {
        path: {
          document_id: upload.document.id,
          version_id: upload.version_id,
        },
      },
    },
  );
  if (!completed.data)
    throw await parseApiError(completed.response, completed.error);
  return completed.data;
}
