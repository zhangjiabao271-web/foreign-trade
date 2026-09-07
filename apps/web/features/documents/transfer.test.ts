import { webcrypto } from "node:crypto";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createTradeApiClient } from "@trade-workbench/api-client";
import {
  resumeDocumentUpload,
  uploadDocument,
  type UploadRetry,
} from "./transfer";

afterEach(() => vi.unstubAllGlobals());

function fixture() {
  vi.stubGlobal("crypto", webcrypto);
  const put = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal("fetch", put);
  const post = vi.fn();
  const client = { POST: post } as unknown as ReturnType<
    typeof createTradeApiClient
  >;
  const file = new File(["proof"], "proof.txt", { type: "text/plain" });
  Object.defineProperty(file, "arrayBuffer", {
    value: async () => new TextEncoder().encode("proof").buffer,
  });
  const input = {
    file,
    documentType: "PACKING_LIST" as const,
    targetType: "SHIPMENT" as const,
    targetId: "shipment",
  };
  const pending = {
    data: {
      document: { id: "document" },
      version_id: "version",
      upload_url: "https://storage.test/put",
    },
  };
  const complete = { data: { id: "document" } };
  return { post, put, client, input, pending, complete };
}

describe("upload recovery", () => {
  it.each([false, true])(
    "resumes persisted identity, accepted=%s",
    async (accepted) => {
      const f = fixture();
      f.post.mockResolvedValueOnce({
        data: {
          ...f.pending.data,
          upload_url: accepted ? null : f.pending.data.upload_url,
        },
      });
      if (!accepted) f.post.mockResolvedValueOnce(f.complete);
      await resumeDocumentUpload(f.client, "document", "version", f.input.file);
      expect(f.post.mock.calls[0][0]).toBe(
        "/api/v1/documents/{document_id}/versions/{version_id}/upload-session",
      );
      expect(f.post.mock.calls[0][1]).toMatchObject({
        params: { path: { document_id: "document", version_id: "version" } },
        body: {
          file_name: "proof.txt",
          mime_type: "text/plain",
          size_bytes: 5,
        },
      });
      expect(f.post.mock.calls[0][1].body.sha256).toMatch(/^[a-f0-9]{64}$/);
      expect(f.put).toHaveBeenCalledTimes(accepted ? 0 : 1);
      expect(f.post).toHaveBeenCalledTimes(accepted ? 1 : 2);
    },
  );
  it.each(["session", "put", "complete"])(
    "retains one key after lost %s result",
    async (stage) => {
      const f = fixture();
      const retry: UploadRetry = {};
      if (stage === "session") f.post.mockRejectedValueOnce(new Error("lost"));
      else {
        f.post.mockResolvedValueOnce(f.pending);
        if (stage === "put") f.put.mockRejectedValueOnce(new Error("lost"));
        else f.post.mockRejectedValueOnce(new Error("lost"));
      }
      await expect(uploadDocument(f.client, f.input, retry)).rejects.toThrow(
        "lost",
      );
      const key = retry.attempt?.key;
      f.post.mockResolvedValueOnce(f.pending).mockResolvedValueOnce(f.complete);
      await expect(uploadDocument(f.client, f.input, retry)).resolves.toEqual(
        f.complete.data,
      );
      const creates = f.post.mock.calls.filter(([path]) =>
        path.endsWith("upload-sessions"),
      );
      expect(creates).toHaveLength(2);
      expect(
        creates.map(([, options]) => options.headers["Idempotency-Key"]),
      ).toEqual([key, key]);
      expect(retry.attempt).toBeUndefined();
    },
  );

  it("does not PUT or complete an already accepted version", async () => {
    const f = fixture();
    const retry: UploadRetry = {};
    f.post.mockResolvedValueOnce({
      data: { ...f.pending.data, upload_url: null },
    });
    await expect(uploadDocument(f.client, f.input, retry)).resolves.toEqual({
      id: "document",
    });
    expect(f.put).not.toHaveBeenCalled();
    expect(f.post).toHaveBeenCalledTimes(1);
  });

  it("rotates identity for changed target and retains replacement precondition", async () => {
    const f = fixture();
    const retry: UploadRetry = {};
    f.post.mockRejectedValue(new Error("lost"));
    const input = {
      ...f.input,
      replacement: { documentId: "document", expectedVersion: 3 },
    };
    await expect(uploadDocument(f.client, input, retry)).rejects.toThrow(
      "lost",
    );
    const key = retry.attempt?.key;
    await expect(
      uploadDocument(f.client, { ...input, targetId: "other" }, retry),
    ).rejects.toThrow("lost");
    expect(retry.attempt?.key).not.toEqual(key);
    expect(f.post.mock.calls[0][1].body.expected_version).toBe(3);
    expect(f.post.mock.calls[1][1].body.expected_version).toBe(3);
  });
});
