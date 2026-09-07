"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useSessionScope } from "../overview/session";
import { useMemberContext } from "../overview/api";
import { useCustomerReview } from "./api";

const schema = z.object({
  reason: z
    .string()
    .trim()
    .min(1, "请填写客户审阅依据")
    .max(500, "依据最多 500 字"),
});
function ReviewForm({ id, versionId }: { id: string; versionId: string }) {
  const mutation = useCustomerReview(id);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { reason: "" },
  });
  const [retry, setRetry] = useState({ payload: "", key: "" });
  return (
    <form
      className="finance-form"
      onSubmit={form.handleSubmit((values) => {
        const body = { expected_version_id: versionId, reason: values.reason };
        const payload = JSON.stringify(body);
        const key = retry.payload === payload ? retry.key : crypto.randomUUID();
        setRetry({ payload, key });
        mutation.mutate({ body, key });
      })}
    >
      <p>仅记录已确认的客户审阅事实，不代表客户接受，也不会发送消息。</p>
      <label>
        客户审阅依据
        <input {...form.register("reason")} disabled={mutation.isPending} />
      </label>
      {form.formState.errors.reason && (
        <p role="alert">{form.formState.errors.reason.message}</p>
      )}
      {mutation.isError && (
        <p role="alert">记录失败，请刷新核对当前报价版本和权限后重试。</p>
      )}
      <button className="secondary-button" disabled={mutation.isPending}>
        {mutation.isPending ? "正在记录…" : "记录客户审阅"}
      </button>
    </form>
  );
}
function AuthorizedReview({
  scope,
  id,
  versionId,
}: {
  scope: string;
  id: string;
  versionId: string;
}) {
  const member = useMemberContext(scope);
  if (!member.data?.permissions.includes("quotation.send")) return null;
  return <ReviewForm key={versionId} id={id} versionId={versionId} />;
}
export function CustomerReview({
  id,
  versionId,
}: {
  id: string;
  versionId: string;
}) {
  const scope = useSessionScope();
  return scope ? (
    <AuthorizedReview key={scope} scope={scope} id={id} versionId={versionId} />
  ) : null;
}
