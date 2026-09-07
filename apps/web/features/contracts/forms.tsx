"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ApiClientError } from "@trade-workbench/api-client";
import {
  useContractWrite,
  type Contract,
  type ContractDocument,
  type ContractWrite,
} from "./api";

export function contractError(error: unknown) {
  if (error instanceof ApiClientError) return error.problem.detail;
  return error instanceof Error ? error.message : "暂时无法读取合同，请重试。";
}
const schema = z.object({
  reference: z.string().trim().max(160, "外部编号最多 160 字"),
  notes: z.string().trim().max(2000, "备注最多 2000 字"),
  reason: z.string().trim().min(3, "请填写至少三个字符的原因").max(500),
  signedOn: z.string(),
  versionId: z.string(),
  confirmed: z.boolean(),
});
type Mode = "create" | "update" | "sign" | "void";
const labels: Record<Mode, string> = {
  create: "建立合同草稿",
  update: "保存合同备注",
  sign: "确认登记已签署",
  void: "确认作废草稿",
};

export function ContractForm({
  scope,
  orderId,
  mode,
  contract,
  documents,
  onDone,
  onCancel,
}: {
  scope: string;
  orderId: string;
  mode: Mode;
  contract?: Contract;
  documents: ContractDocument[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const command = useContractWrite(scope, orderId);
  const [retry, setRetry] = useState<{ payload: string; key: string }>();
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(
      schema.superRefine((v, ctx) => {
        if (mode === "sign") {
          if (!/^\d{4}-\d{2}-\d{2}$/.test(v.signedOn))
            ctx.addIssue({
              code: "custom",
              path: ["signedOn"],
              message: "请选择已发生的签署日期",
            });
          if (!z.uuid().safeParse(v.versionId).success)
            ctx.addIssue({
              code: "custom",
              path: ["versionId"],
              message: "请选择已验收的合同文件版本",
            });
        }
        if ((mode === "sign" || mode === "void") && !v.confirmed)
          ctx.addIssue({
            code: "custom",
            path: ["confirmed"],
            message: "请确认操作含义",
          });
      }),
    ),
    defaultValues: {
      reference: contract?.external_reference ?? "",
      notes: contract?.notes ?? "",
      reason: mode === "create" ? "建立合同草稿" : "",
      signedOn: "",
      versionId: "",
      confirmed: false,
    },
  });
  return (
    <form
      className="finance-form"
      onSubmit={form.handleSubmit((values) => {
        const payload = JSON.stringify({
          mode,
          values,
          version: contract?.version,
        });
        const key =
          retry?.payload === payload ? retry.key : crypto.randomUUID();
        setRetry({ payload, key });
        let write: ContractWrite;
        const fields = {
          external_reference: values.reference || null,
          ...(mode === "update" && !contract?.content_visible
            ? {}
            : { notes: values.notes || null }),
        };
        if (mode === "create") write = { action: "create", body: fields, key };
        else {
          if (!contract) return;
          const base = {
            expected_version: contract.version,
            reason: values.reason,
          };
          if (mode === "sign")
            write = {
              action: "sign",
              id: contract.id,
              key,
              body: {
                ...base,
                signed_on: values.signedOn,
                document_version_id: values.versionId,
              },
            };
          else if (mode === "void")
            write = { action: "void", id: contract.id, key, body: base };
          else
            write = {
              action: "update",
              id: contract.id,
              key,
              body: { ...base, ...fields },
            };
        }
        command.mutate(write, { onSuccess: onDone });
      })}
    >
      <h3>{labels[mode]}</h3>
      <fieldset disabled={command.isPending}>
        {(mode === "create" || mode === "update") && (
          <>
            <label>
              外部合同编号
              <input {...form.register("reference")} />
            </label>
            <label>
              合同备注
              <textarea
                {...form.register("notes")}
                disabled={mode === "update" && !contract?.content_visible}
              />
            </label>
            <p>备注不覆盖订单价格、付款和交付条款；商业快照保持不变。</p>
            {mode === "update" && !contract?.content_visible && (
              <p>原备注尚未开放，本次仅修改编号，不改写保密备注。</p>
            )}
          </>
        )}
        {mode === "sign" && (
          <>
            <label>
              合同签署日期
              <input type="date" {...form.register("signedOn")} />
            </label>
            <label>
              签署证据版本
              <select {...form.register("versionId")}>
                <option value="">请选择已验收文件</option>
                {documents.flatMap((d) =>
                  (d.versions ?? [])
                    .filter((v) => v.status === "AVAILABLE")
                    .map((v) => (
                      <option key={v.id} value={v.id}>
                        {d.title} · 第 {v.version_number} 版
                      </option>
                    )),
                )}
              </select>
            </label>
            <p>
              仅登记已发生的签署，不提供电子签章。文件内容与合同条款的一致性须人工核对。
            </p>
          </>
        )}
        {mode !== "create" && (
          <label>
            合同操作原因
            <textarea {...form.register("reason")} />
          </label>
        )}
        {(mode === "sign" || mode === "void") && (
          <label className="contract-confirm">
            <input type="checkbox" {...form.register("confirmed")} />
            {mode === "sign"
              ? "我已核对签署文件与合同商业条款"
              : "我确认仅作废此草稿，不取消订单"}
          </label>
        )}
        {Object.values(form.formState.errors).map((e, i) => (
          <p key={i} role="alert" className="form-error">
            {e.message}
          </p>
        ))}
        {command.isError && (
          <p role="alert" className="form-error">
            {contractError(command.error)}
          </p>
        )}
        <div className="queue-pagination">
          <button className="primary-button">
            {command.isPending ? "正在保存…" : labels[mode]}
          </button>
          <button type="button" className="secondary-button" onClick={onCancel}>
            取消合同操作
          </button>
        </div>
      </fieldset>
    </form>
  );
}
