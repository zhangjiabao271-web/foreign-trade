"use client";
import { useRef, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ApiClientError } from "@trade-workbench/api-client";
import {
  useArchiveCommand,
  type Company,
  type Contact,
  type CompanyRole,
} from "./api";

export const roleLabels: Record<CompanyRole, string> = {
  CUSTOMER: "客户",
  SUPPLIER: "供应商",
  FORWARDER: "货代",
  AGENT: "代理",
};
const roles = ["CUSTOMER", "SUPPLIER", "FORWARDER", "AGENT"] as const;
const reason = z.string().trim().max(1000, "原因最多 1000 字");
export function archiveError(error: unknown) {
  if (error instanceof ApiClientError) {
    if (error.problem.status === 409)
      return "名称已存在或资料版本已变化。请先检索现有档案，或刷新核对后再保存。";
    if (error.problem.status === 403) return "当前成员没有此操作权限。";
    if (error.problem.status === 404) return "档案不存在或不在当前组织中。";
    if (error.problem.status === 422)
      return "资料格式未通过校验，请核对各字段后重试。";
  }
  return "未能确认结果。可重试同一操作，或刷新核对是否已保存。";
}
function useRetryKey() {
  const previous = useRef<{ payload: string; key: string } | null>(null);
  return (body: unknown) => {
    const payload = JSON.stringify(body);
    if (previous.current?.payload !== payload)
      previous.current = { payload, key: crypto.randomUUID() };
    return previous.current.key;
  };
}
function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label>
        {label}
        {children}
      </label>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
function Actions({
  pending,
  onClose,
}: {
  pending: boolean;
  onClose: () => void;
}) {
  return (
    <div className="purchase-actions">
      <button className="primary-button" type="submit">
        {pending ? "正在保存…" : "保存档案"}
      </button>
      <button className="secondary-button" type="button" onClick={onClose}>
        取消编辑
      </button>
    </div>
  );
}
export function CompanyForm({
  scope,
  row,
  onClose,
  onSaved,
}: {
  scope: string;
  row?: Company;
  onClose: () => void;
  onSaved: (id: string) => void;
}) {
  const mutation = useArchiveCommand(scope);
  const retryKey = useRetryKey();
  const schema = z.object({
    name: z
      .string()
      .trim()
      .min(1, "请填写公司名称")
      .max(240, "名称最多 240 字"),
    country_code: z
      .string()
      .trim()
      .regex(/^([A-Z]{2})?$/, "请填写两位大写国家代码，例如 CN"),
    website: z
      .string()
      .trim()
      .max(500, "网址最多 500 字")
      .regex(/^(https?:\/\/[^\s]+)?$/, "网址须以 http:// 或 https:// 开头"),
    roles: z.array(z.enum(roles)).min(row ? 0 : 1, "至少选择一种业务角色"),
    reason: row ? reason.min(1, "请填写修改原因") : reason,
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: row?.name ?? "",
      country_code: row?.country_code ?? "",
      website: row?.website ?? "",
      roles: row?.roles ?? [],
      reason: "",
    },
  });
  const errors = form.formState.errors;
  return (
    <form
      className="purchase-change-form"
      onSubmit={form.handleSubmit((values) => {
        const fields = {
          name: values.name,
          country_code: values.country_code || null,
          website: values.website || null,
        };
        const command = row
          ? {
              kind: "update-company" as const,
              id: row.id,
              body: {
                ...fields,
                expected_version: row.version,
                reason: values.reason,
              },
            }
          : {
              kind: "create-company" as const,
              body: { ...fields, roles: values.roles },
            };
        mutation.mutate(
          { ...command, key: retryKey(command) },
          { onSuccess: (result) => onSaved(result.id) },
        );
      })}
    >
      <h2>{row ? "编辑公司资料" : "新建公司档案"}</h2>
      <p>客户和供应商可共用同一档案。请先检索，避免重复建档。</p>
      <fieldset disabled={mutation.isPending}>
        <Field label="公司名称" error={errors.name?.message}>
          <input
            maxLength={240}
            {...form.register("name")}
            aria-invalid={Boolean(errors.name)}
          />
        </Field>
        <Field label="国家代码（选填）" error={errors.country_code?.message}>
          <input
            maxLength={2}
            {...form.register("country_code")}
            aria-invalid={Boolean(errors.country_code)}
          />
        </Field>
        <Field label="公司网站（选填）" error={errors.website?.message}>
          <input
            {...form.register("website")}
            aria-invalid={Boolean(errors.website)}
          />
        </Field>
        {!row && (
          <fieldset>
            <legend>业务角色（可多选）</legend>
            {roles.map((role) => (
              <label className="outbox-confirm" key={role}>
                <input
                  type="checkbox"
                  value={role}
                  {...form.register("roles")}
                />
                {roleLabels[role]}
              </label>
            ))}
            {errors.roles && <p role="alert">{errors.roles.message}</p>}
          </fieldset>
        )}
        {row && (
          <Field label="修改原因" error={errors.reason?.message}>
            <textarea
              {...form.register("reason")}
              aria-invalid={Boolean(errors.reason)}
            />
          </Field>
        )}
        {mutation.isError && <p role="alert">{archiveError(mutation.error)}</p>}
        <Actions pending={mutation.isPending} onClose={onClose} />
      </fieldset>
    </form>
  );
}
export function ContactForm({
  scope,
  companyId,
  row,
  onClose,
  onSaved,
}: {
  scope: string;
  companyId: string;
  row?: Contact;
  onClose: () => void;
  onSaved: () => void;
}) {
  const mutation = useArchiveCommand(scope);
  const retryKey = useRetryKey();
  const schema = z.object({
    full_name: z
      .string()
      .trim()
      .min(1, "请填写联系人姓名")
      .max(200, "姓名最多 200 字"),
    email: z
      .string()
      .trim()
      .max(320, "邮箱最多 320 字")
      .regex(/^([^\s@]+@[^\s@]+\.[^\s@]+)?$/, "请填写有效邮箱"),
    phone: z.string().trim().max(80, "电话最多 80 字"),
    job_title: z.string().trim().max(160, "职务最多 160 字"),
    reason: row ? reason.min(1, "请填写修改原因") : reason,
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: {
      full_name: row?.full_name ?? "",
      email: row?.email ?? "",
      phone: row?.phone ?? "",
      job_title: row?.job_title ?? "",
      reason: "",
    },
  });
  const errors = form.formState.errors;
  return (
    <form
      className="purchase-change-form"
      onSubmit={form.handleSubmit((values) => {
        const fields = {
          full_name: values.full_name,
          email: values.email || null,
          phone: values.phone || null,
          job_title: values.job_title || null,
        };
        const command = row
          ? {
              kind: "update-contact" as const,
              id: companyId,
              contactId: row.id,
              body: {
                ...fields,
                expected_version: row.version,
                reason: values.reason,
              },
            }
          : { kind: "create-contact" as const, id: companyId, body: fields };
        mutation.mutate(
          { ...command, key: retryKey(command) },
          { onSuccess: onSaved },
        );
      })}
    >
      <h2>{row ? "编辑联系人" : "新建联系人"}</h2>
      <fieldset disabled={mutation.isPending}>
        <Field label="联系人姓名" error={errors.full_name?.message}>
          <input
            {...form.register("full_name")}
            aria-invalid={Boolean(errors.full_name)}
          />
        </Field>
        <Field label="邮箱（选填）" error={errors.email?.message}>
          <input
            {...form.register("email")}
            aria-invalid={Boolean(errors.email)}
          />
        </Field>
        <Field label="电话（选填）" error={errors.phone?.message}>
          <input
            type="tel"
            {...form.register("phone")}
            aria-invalid={Boolean(errors.phone)}
          />
        </Field>
        <Field label="职务（选填）" error={errors.job_title?.message}>
          <input
            {...form.register("job_title")}
            aria-invalid={Boolean(errors.job_title)}
          />
        </Field>
        {row && (
          <Field label="修改原因" error={errors.reason?.message}>
            <textarea
              {...form.register("reason")}
              aria-invalid={Boolean(errors.reason)}
            />
          </Field>
        )}
        {mutation.isError && <p role="alert">{archiveError(mutation.error)}</p>}
        <Actions pending={mutation.isPending} onClose={onClose} />
      </fieldset>
    </form>
  );
}
