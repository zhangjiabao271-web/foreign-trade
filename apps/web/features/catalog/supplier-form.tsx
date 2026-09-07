"use client";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ApiClientError } from "@trade-workbench/api-client";
import { useCompanies } from "../companies/api";
import { useWriteSupplier, type SupplierLink } from "./api";

export function supplierError(error: unknown) {
  if (error instanceof ApiClientError) {
    if (error.problem.code === "SUPPLIER_LINK_EXISTS")
      return "此产品已有该供应商，请编辑现有记录。";
    if (error.problem.code === "SUPPLIER_ROLE_REQUIRED")
      return "请先在客商档案中增加供应商角色。";
    if (error.problem.status === 409)
      return "记录已变化，请取消编辑并刷新核对后再保存。";
    if (error.problem.status === 403) return "当前成员无此项权限。";
    if (error.problem.status === 404)
      return "产品或供应商记录不存在，或不在当前组织。";
  }
  return "未能确认保存结果，请重试同一操作或刷新核对。";
}
function SupplierPicker({
  scope,
  selected,
  onChoose,
}: {
  scope: string;
  selected: string;
  onChoose: (id: string, name: string) => void;
}) {
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [cursors, setCursors] = useState<Array<string | undefined>>([
    undefined,
  ]);
  const query = useCompanies(scope, search, "SUPPLIER", cursors.at(-1));
  return (
    <fieldset>
      <legend>选择供应商</legend>
      <label>
        供应商名称检索
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          maxLength={240}
        />
      </label>
      <button
        type="button"
        className="secondary-button"
        disabled={query.isFetching}
        onClick={() => {
          setSearch(input.trim());
          setCursors([undefined]);
        }}
      >
        查找供应商
      </button>
      {query.isPending && <p role="status">正在读取供应商…</p>}
      {query.isError && <p role="alert">{supplierError(query.error)}</p>}
      {query.data?.items.length === 0 && (
        <p>未找到供应商，请先在客商档案中建档或增加供应商角色。</p>
      )}
      {query.data?.items.map((company) => (
        <label className="outbox-confirm" key={company.id}>
          <input
            type="radio"
            name="supplier-choice"
            checked={selected === company.id}
            onChange={() => onChoose(company.id, company.name)}
          />
          {company.name}
        </label>
      ))}
      <div className="purchase-actions">
        <button
          type="button"
          className="secondary-button"
          disabled={cursors.length === 1 || query.isFetching}
          onClick={() => setCursors(cursors.slice(0, -1))}
        >
          上一页供应商
        </button>
        <button
          type="button"
          className="secondary-button"
          disabled={
            !query.data?.has_more ||
            !query.data.next_cursor ||
            query.isFetching ||
            query.isError
          }
          onClick={() =>
            setCursors([...cursors, query.data?.next_cursor ?? undefined])
          }
        >
          下一页供应商
        </button>
      </div>
    </fieldset>
  );
}
export function SupplierForm({
  scope,
  productId,
  row,
  onClose,
  onSaved,
}: {
  scope: string;
  productId: string;
  row?: SupplierLink;
  onClose: () => void;
  onSaved: () => void;
}) {
  const mutation = useWriteSupplier(scope, productId);
  const [submission, setSubmission] = useState<{
    payload: string;
    key: string;
  } | null>(null);
  const [selectedName, setSelectedName] = useState(row?.supplier_name ?? "");
  const schema = z
    .object({
      supplier_id: z.string().uuid("请选择供应商"),
      supplier_sku: z
        .string()
        .trim()
        .min(1, "请填写供应商货号")
        .max(80, "货号最多 80 字"),
      unit_price: z
        .string()
        .trim()
        .regex(
          /^\d{1,14}(\.\d{1,4})?$/,
          "请输入非负价格，最多 14 位整数和 4 位小数",
        ),
      currency: z
        .string()
        .trim()
        .regex(/^[A-Z]{3}$/, "请填写三位大写币种代码"),
      lead_time_days: z
        .string()
        .regex(/^\d{1,4}$/, "请填写整数天数")
        .refine((value) => Number(value) <= 3650, "交期最多 3650 天"),
      quoted_on: z.iso.date("请填写有效报价日期"),
      valid_until: z.union([z.literal(""), z.iso.date("请填写有效截止日期")]),
      quotation_reference: z.string().trim().max(500, "参考说明最多 500 字"),
      reason: row
        ? z.string().trim().min(1, "请填写修改原因").max(1000)
        : z.string(),
    })
    .refine(
      (values) => !values.valid_until || values.valid_until >= values.quoted_on,
      { path: ["valid_until"], message: "有效期不能早于报价日期" },
    );
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: {
      supplier_id: row?.supplier_id ?? "",
      supplier_sku: row?.supplier_sku ?? "",
      unit_price: row?.unit_price ?? "",
      currency: row?.currency ?? "CNY",
      lead_time_days: row ? String(row.lead_time_days) : "",
      quoted_on: row?.quoted_on ?? "",
      valid_until: row?.valid_until ?? "",
      quotation_reference: row?.quotation_reference ?? "",
      reason: "",
    },
  });
  const selectedSupplier = useWatch({
    control: form.control,
    name: "supplier_id",
  });
  const fields = [
    ["supplier_sku", "供应商货号", "text"],
    ["unit_price", "参考单价", "text"],
    ["currency", "报价币种", "text"],
    ["lead_time_days", "参考交期（天）", "text"],
    ["quoted_on", "报价日期", "date"],
    ["valid_until", "有效截止日期（选填）", "date"],
    ["quotation_reference", "报价来源或参考号（选填）", "text"],
  ] as const;
  return (
    <form
      className="purchase-change-form"
      onSubmit={form.handleSubmit((values) => {
        const body = {
          supplier_sku: values.supplier_sku,
          unit_price: values.unit_price,
          currency: values.currency,
          lead_time_days: Number(values.lead_time_days),
          quoted_on: values.quoted_on,
          valid_until: values.valid_until || null,
          quotation_reference: values.quotation_reference || null,
        };
        const command = row
          ? {
              kind: "update" as const,
              linkId: row.id,
              body: {
                ...body,
                expected_version: row.version,
                reason: values.reason,
              },
            }
          : {
              kind: "create" as const,
              body: { ...body, supplier_id: values.supplier_id },
            };
        const payload = JSON.stringify(command);
        const key =
          submission?.payload === payload
            ? submission.key
            : crypto.randomUUID();
        setSubmission({ payload, key });
        mutation.mutate({ ...command, key }, { onSuccess: onSaved });
      })}
    >
      <h2>{row ? "更新供应商参考记录" : "关联产品供应商"}</h2>
      <p>参考单价按产品单位记录，不自动修改产品成本、历史报价或已确认采购。</p>
      <fieldset disabled={mutation.isPending}>
        {!row && (
          <SupplierPicker
            scope={scope}
            selected={selectedSupplier}
            onChoose={(id, name) => {
              form.setValue("supplier_id", id, { shouldValidate: true });
              setSelectedName(name);
            }}
          />
        )}
        <p>已选供应商：{selectedName || "尚未选择"}</p>
        {form.formState.errors.supplier_id && (
          <p role="alert">{form.formState.errors.supplier_id.message}</p>
        )}
        {fields.map(([name, label, type]) => (
          <div key={name}>
            <label>
              {label}
              <input
                type={type}
                {...form.register(name)}
                aria-invalid={Boolean(form.formState.errors[name])}
              />
            </label>
            {form.formState.errors[name] && (
              <p role="alert">{form.formState.errors[name]?.message}</p>
            )}
          </div>
        ))}
        {row && (
          <label>
            修改原因
            <textarea
              {...form.register("reason")}
              aria-invalid={Boolean(form.formState.errors.reason)}
            />
          </label>
        )}
        {form.formState.errors.reason && (
          <p role="alert">{form.formState.errors.reason.message}</p>
        )}
        {mutation.isError && (
          <p role="alert">{supplierError(mutation.error)}</p>
        )}
        <div className="purchase-actions">
          <button className="primary-button">
            {mutation.isPending ? "正在保存…" : "保存供应商参考"}
          </button>
          <button type="button" className="secondary-button" onClick={onClose}>
            取消编辑
          </button>
        </div>
      </fieldset>
    </form>
  );
}
