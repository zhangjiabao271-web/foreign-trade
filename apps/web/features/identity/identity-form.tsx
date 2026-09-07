"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ApiClientError } from "@trade-workbench/api-client";
import {
  type IdentityWrite,
  type Member,
  type Organization,
  useIdentityWrite,
} from "./api";

export type IdentityEdit =
  | { mode: "settings"; organization: Organization }
  | { mode: "add" }
  | { mode: "role" | "disable" | "reactivate"; member: Member };
export const roles = {
  ADMIN: "管理员",
  MANAGER: "经理",
  SALES: "销售",
  OPERATIONS: "运营",
  FINANCE: "财务",
  VIEWER: "只读成员",
};
const labels = {
  settings: "保存组织设置",
  add: "确认添加成员",
  role: "确认调整角色",
  disable: "确认停用成员",
  reactivate: "确认重新启用",
};
function identityFields(mode: IdentityEdit["mode"]) {
  if (mode === "settings") return ["name", "timezone", "reason"] as const;
  if (mode === "add") return ["subject", "displayName", "reason"] as const;
  return ["reason"] as const;
}
const schema = z.object({
  name: z.string().trim().max(200),
  timezone: z.string().trim().max(64),
  subject: z.string().trim().max(255),
  displayName: z.string().trim().max(200),
  role: z.enum([
    "ADMIN",
    "MANAGER",
    "SALES",
    "OPERATIONS",
    "FINANCE",
    "VIEWER",
  ]),
  reason: z.string().trim().min(3, "请填写至少三个字符的操作原因").max(500),
  confirmed: z.boolean().refine(Boolean, "请核对授权对象并确认影响"),
});
export function identityError(error: unknown) {
  if (error instanceof ApiClientError) {
    if (error.problem.code === "LAST_ADMINISTRATOR")
      return "不能移除最后一位有效管理员。请先授权并核实另一位管理员。";
    if (error.problem.code === "MEMBERSHIP_EXISTS")
      return "此账号已有关联成员，请在列表中调整角色或重新启用。";
    if (error.problem.status === 409)
      return "记录已变化或操作条件不满足。请取消并刷新，重新核对后操作。";
    if (error.problem.status === 403)
      return "当前账号已无管理权限，请返回首页或联系管理员。";
    if (error.problem.status === 401) return "登录已失效，请重新登录。";
    if (error.problem.status === 422)
      return "输入未通过校验，请核对账号标识、时区和操作原因。";
  }
  return "尚未确认请求结果。请先核对记录；未修改内容时重试不会重复授权。";
}
export function IdentityForm({
  scope,
  edit,
  onDone,
  onCancel,
}: {
  scope: string;
  edit: IdentityEdit;
  onDone: () => void;
  onCancel: () => void;
}) {
  const mutation = useIdentityWrite(scope);
  const [retry, setRetry] = useState<{ payload: string; key: string }>();
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(
      schema.superRefine((v, ctx) => {
        const required = identityFields(edit.mode).filter(
          (field) => field !== "reason",
        );
        for (const field of required)
          if (!v[field])
            ctx.addIssue({
              code: "custom",
              path: [field],
              message: "请填写此项",
            });
      }),
    ),
    defaultValues: {
      name: edit.mode === "settings" ? edit.organization.name : "",
      timezone: edit.mode === "settings" ? edit.organization.timezone : "",
      subject: "",
      displayName: "",
      role: "member" in edit ? edit.member.role : "VIEWER",
      reason: "",
      confirmed: false,
    },
  });
  const fields = identityFields(edit.mode);
  const fieldNames = {
    name: "组织名称",
    timezone: "业务时区（IANA）",
    subject: "已核实的 Logto 用户标识",
    displayName: "首次映射展示名",
    reason: "组织管理操作原因",
  };
  return (
    <form
      className="finance-form"
      onSubmit={form.handleSubmit((v) => {
        const payload = JSON.stringify({ edit, v });
        const key =
          retry?.payload === payload ? retry.key : crypto.randomUUID();
        setRetry({ payload, key });
        let command: IdentityWrite;
        if (edit.mode === "settings")
          command = {
            action: "settings",
            key,
            body: {
              name: v.name,
              timezone: v.timezone,
              expected_version: edit.organization.version,
              reason: v.reason,
            },
          };
        else if (edit.mode === "add")
          command = {
            action: "add",
            key,
            body: {
              external_subject: v.subject,
              display_name: v.displayName,
              role: v.role,
              reason: v.reason,
            },
          };
        else if (edit.mode === "role")
          command = {
            action: "role",
            id: edit.member.id,
            key,
            body: {
              role: v.role,
              expected_version: edit.member.version,
              reason: v.reason,
            },
          };
        else
          command = {
            action: edit.mode,
            id: edit.member.id,
            key,
            body: { expected_version: edit.member.version, reason: v.reason },
          };
        mutation.mutate(command, { onSuccess: onDone });
      })}
    >
      <h3>{labels[edit.mode]}</h3>
      {"member" in edit && (
        <p>
          授权对象：{edit.member.display_name} · {edit.member.external_subject}{" "}
          · 当前角色 {roles[edit.member.role]}
        </p>
      )}
      <p>
        {edit.mode === "add"
          ? "请先在登录服务核实准确用户标识。本操作直接授权当前组织，不创建登录账号、不发送邀请、不设置密码；已有账号展示名保持不变。"
          : "更改只影响当前组织。操作会记录原因；停用或调整自己的角色后，可能无法继续管理。"}
      </p>
      <fieldset disabled={mutation.isPending}>
        {fields.map((field) => (
          <div key={field}>
            <label>
              {fieldNames[field]}
              <input
                {...form.register(field)}
                aria-invalid={Boolean(form.formState.errors[field])}
                aria-describedby={`identity-${field}-error`}
              />
            </label>
            <p
              id={`identity-${field}-error`}
              role={form.formState.errors[field] ? "alert" : undefined}
            >
              {form.formState.errors[field]?.message}
            </p>
          </div>
        ))}
        {(edit.mode === "role" || edit.mode === "add") && (
          <label>
            授权角色
            <select {...form.register("role")}>
              {Object.entries(roles).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="contract-confirm">
          <input type="checkbox" {...form.register("confirmed")} />
          我已核对授权对象、操作原因和权限影响
        </label>
        {form.formState.errors.confirmed && (
          <p role="alert">{form.formState.errors.confirmed.message}</p>
        )}
        {mutation.isError && (
          <p role="alert">{identityError(mutation.error)}</p>
        )}
        <div className="queue-pagination">
          <button className="primary-button">
            {mutation.isPending ? "正在保存…" : labels[edit.mode]}
          </button>
          <button type="button" className="secondary-button" onClick={onCancel}>
            取消组织管理操作
          </button>
        </div>
      </fieldset>
    </form>
  );
}
