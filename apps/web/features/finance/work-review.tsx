"use client";

import { useId, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  parseApiError,
  type components,
  type paths,
} from "@trade-workbench/api-client";
import { useMemberContext } from "../overview/api";
import { sessionClient, useSessionScope } from "../overview/session";

type WorkSnapshot = components["schemas"]["WorkReviewResponse"];
type CrmSnapshot = components["schemas"]["CrmTextReviewResponse"];
type ExportSnapshot = components["schemas"]["ExportTextReviewResponse"];
type CommercialSnapshot = components["schemas"]["CommercialTextReviewResponse"];
type Snapshot =
  | WorkSnapshot
  | CrmSnapshot
  | ExportSnapshot
  | CommercialSnapshot
  | components["schemas"]["ProductTextReviewResponse"]
  | components["schemas"]["InquiryTextReviewResponse"]
  | components["schemas"]["PurchaseTextReviewResponse"]
  | components["schemas"]["PaymentTextReviewResponse"];
const paymentRoute = "/api/v1/payments/{payment_id}/text-review";
const sourceRoutes = {
  product: "/api/v1/products/{record_id}/text-review",
  inquiry: "/api/v1/inquiries/{record_id}/text-review",
  purchase: "/api/v1/purchase-orders/{record_id}/text-review",
} as const;
const sourcePermissions = {
  product: "product.read",
  inquiry: "inquiry.read",
  purchase: "procurement.read",
} as const;
const commercialRoute = "/api/v1/commercial-text/{kind}/{record_id}/review";
const commercialPermissions = {
  quotation_version: "quotation.read",
  sales_order: "order.read",
  sales_contract: "contract.read",
} as const;
const exportRoute = "/api/v1/export-text/{kind}/{record_id}/review";
const crmRoute = "/api/v1/crm-text/{kind}/{record_id}/review";
const activityRoute =
  "/api/v1/work/{subject_type}/{subject_id}/activities/{record_id}/review";
type Subject =
  paths[typeof activityRoute]["get"]["parameters"]["path"]["subject_type"];
type Target = { recordId: string } & (
  | { orderId: string; kind: WorkSnapshot["kind"] }
  | { subjectType: Subject; subjectId: string }
  | { crmKind: CrmSnapshot["kind"] }
  | { exportKind: ExportSnapshot["kind"] }
  | { paymentText: true }
  | { sourceKind: keyof typeof sourceRoutes }
  | { commercialKind: CommercialSnapshot["kind"] }
);
const subjectPermission = {
  lead: "lead.read",
  company: "company.read",
  opportunity: "opportunity.read",
  customs_declaration: "export.read",
  tax_refund_case: "export.read",
  purchase_order: "procurement.read",
  quotation: "quotation.read",
  shipment: "shipment.read",
} as const;
function targetKey(target: Target) {
  if ("sourceKind" in target)
    return `source-text:${target.sourceKind}:${target.recordId}`;
  if ("commercialKind" in target)
    return `commercial-text:${target.commercialKind}:${target.recordId}`;
  if ("paymentText" in target) return `payment-text:${target.recordId}`;
  if ("exportKind" in target)
    return ["export-text", target.exportKind, target.recordId].join(":");
  if ("orderId" in target)
    return [target.orderId, target.kind, target.recordId].join(":");
  if ("crmKind" in target)
    return ["crm-text", target.crmKind, target.recordId].join(":");
  return [target.subjectType, target.subjectId, target.recordId].join(":");
}
function readPermission(target: Target) {
  if ("sourceKind" in target) return sourcePermissions[target.sourceKind];
  if ("commercialKind" in target)
    return commercialPermissions[target.commercialKind];
  if ("paymentText" in target) return "payment.read" as const;
  if ("exportKind" in target) return "export.read" as const;
  if ("orderId" in target) return "order.read" as const;
  if ("crmKind" in target) return subjectPermission[target.crmKind];
  return subjectPermission[target.subjectType];
}
function crmPath(target: Extract<Target, { crmKind: string }>) {
  return { kind: target.crmKind, record_id: target.recordId };
}
function activityPath(target: Extract<Target, { subjectId: string }>) {
  return {
    subject_type: target.subjectType,
    subject_id: target.subjectId,
    record_id: target.recordId,
  };
}
const schema = z.object({
  decision: z.enum(["release", "restrict"], { error: "请选择开放或保密。" }),
  reason: z.string().trim().min(3, "请填写至少 3 个字的审核说明。").max(1000),
  confirmed: z.boolean().refine(Boolean, "请确认已核对下方全部文本。"),
});
const route = "/api/v1/sales-orders/{order_id}/work/{kind}/{record_id}/review";
function path(target: Extract<Target, { orderId: string }>) {
  return {
    order_id: target.orderId,
    kind: target.kind,
    record_id: target.recordId,
  };
}

async function readReview(target: Target) {
  if ("sourceKind" in target)
    return sessionClient().GET(sourceRoutes[target.sourceKind], {
      params: { path: { record_id: target.recordId } },
    });
  if ("commercialKind" in target)
    return sessionClient().GET(commercialRoute, {
      params: {
        path: { kind: target.commercialKind, record_id: target.recordId },
      },
    });
  if ("paymentText" in target)
    return sessionClient().GET(paymentRoute, {
      params: { path: { payment_id: target.recordId } },
    });
  if ("exportKind" in target)
    return sessionClient().GET(exportRoute, {
      params: { path: { kind: target.exportKind, record_id: target.recordId } },
    });
  if ("orderId" in target)
    return sessionClient().GET(route, { params: { path: path(target) } });
  if ("crmKind" in target)
    return sessionClient().GET(crmRoute, { params: { path: crmPath(target) } });
  return sessionClient().GET(activityRoute, {
    params: { path: activityPath(target) },
  });
}
async function submitReview(
  target: Target,
  body: components["schemas"]["WorkReviewRequest"],
  key: string,
) {
  const header = { "idempotency-key": key };
  if ("sourceKind" in target)
    return sessionClient().POST(sourceRoutes[target.sourceKind], {
      params: { path: { record_id: target.recordId }, header },
      body,
    });
  if ("commercialKind" in target)
    return sessionClient().POST(commercialRoute, {
      params: {
        path: { kind: target.commercialKind, record_id: target.recordId },
        header,
      },
      body,
    });
  if ("paymentText" in target)
    return sessionClient().POST(paymentRoute, {
      params: {
        path: { payment_id: target.recordId },
        header: { "Idempotency-Key": key },
      },
      body,
    });
  if ("exportKind" in target)
    return sessionClient().POST(exportRoute, {
      params: {
        path: { kind: target.exportKind, record_id: target.recordId },
        header,
      },
      body,
    });
  if ("orderId" in target)
    return sessionClient().POST(route, {
      params: { path: path(target), header },
      body,
    });
  if ("crmKind" in target)
    return sessionClient().POST(crmRoute, {
      params: { path: crmPath(target), header },
      body,
    });
  return sessionClient().POST(activityRoute, {
    params: { path: activityPath(target), header },
    body,
  });
}

function DecisionForm({
  target,
  snapshot,
  onChanged,
  onRecorded,
  onBusy,
}: {
  target: Target;
  snapshot: Snapshot;
  onChanged: () => Promise<unknown>;
  onRecorded: (value: string) => void;
  onBusy: (value: boolean) => void;
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
          onBusy(true);
          try {
            const result = await submitReview(target, body, retry.current.key);
            if (!result.data)
              throw await parseApiError(result.response, result.error);
            onRecorded(
              result.data.released
                ? "本条文本已开放。"
                : "本条文本已设为保密。",
            );
            await onChanged();
          } catch {
            form.setError("root", {
              message:
                "审核未确认完成。可重试；若内容或权限已变化，请刷新后重新核对。",
            });
          } finally {
            onBusy(false);
          }
        })(event)
      }
    >
      <p>
        本次核对第 {snapshot.version}{" "}
        版。开放后，有原业务读取权限的销售、运营和只读成员可查看以下全部内容；修改后须重新审核。
      </p>
      <div className="work-content-preview" aria-label="待审核文本">
        <p>{snapshot.text}</p>
        <pre>{JSON.stringify(snapshot.details, null, 2)}</pre>
      </div>
      <fieldset disabled={pending}>
        <legend>文本开放范围</legend>
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
          我已核对以上标题或正文及全部补充信息，确认开放范围。
        </label>
        {form.formState.errors.confirmed && (
          <p role="alert">{form.formState.errors.confirmed.message}</p>
        )}
        <button className="secondary-button" disabled={pending}>
          {pending ? "正在记录…" : "确认文本审核"}
        </button>
      </fieldset>
      {form.formState.errors.root && (
        <p role="alert">{form.formState.errors.root.message}</p>
      )}
    </form>
  );
}

function ReviewSession({
  target,
  scope,
  onChanged,
  busy,
  onBusy,
}: {
  target: Target;
  scope: string;
  onChanged: () => Promise<unknown>;
  busy: boolean;
  onBusy: (value: boolean) => void;
}) {
  const [notice, setNotice] = useState("");
  const query = useQuery({
    queryKey: ["work-review", scope, targetKey(target)],
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const result = await readReview(target);
      if (!result.data)
        throw await parseApiError(result.response, result.error);
      return result.data;
    },
  });
  return (
    <div>
      {query.isPending && <p role="status">正在读取待审核文本…</p>}
      {query.isError && <p role="alert">无法读取文本，请检查权限或重试。</p>}
      <button
        className="quiet-button"
        type="button"
        disabled={busy || query.isFetching}
        onClick={() => query.refetch()}
      >
        刷新待审核文本
      </button>
      {query.data && !query.isError && (
        <DecisionForm
          key={`${query.data.version}:${query.data.content_digest}`}
          target={target}
          snapshot={query.data}
          onRecorded={setNotice}
          onBusy={onBusy}
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

export function WorkTextReview({
  onChanged,
  ...target
}: Target & { onChanged: () => Promise<unknown> }) {
  const scope = useSessionScope();
  const member = useMemberContext(scope);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const permissions = member.data?.permissions ?? [];
  const required = readPermission(target);
  const allowed =
    permissions.includes("profit.read") &&
    permissions.includes(required) &&
    (!("kind" in target) ||
      target.kind !== "task" ||
      permissions.includes("task.read"));
  if (!allowed) return null;
  return (
    <div className="work-text-review">
      <button
        type="button"
        className="quiet-button"
        aria-expanded={open}
        disabled={busy}
        onClick={() => setOpen(!open)}
      >
        {open ? "收起文本审核" : "审核文本开放范围"}
      </button>
      {open && (
        <ReviewSession
          key={`${scope}:${targetKey(target)}`}
          target={target}
          scope={scope}
          onChanged={onChanged}
          busy={busy}
          onBusy={setBusy}
        />
      )}
    </div>
  );
}
