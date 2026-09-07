"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ApiClientError } from "@trade-workbench/api-client";
import { WorkTextReview } from "../finance/work-review";
import { useMemberContext } from "../overview/api";
import { useSessionScope } from "../overview/session";
import {
  type PurchaseOrder,
  usePurchaseReceiptCommand,
  usePurchaseActivities,
} from "./api";

const schema = z.object({
  reference: z.string().trim().min(1, "请填写收货凭证号或说明").max(200),
  received_date: z.iso.date("请选择收货日期"),
  lines: z
    .array(
      z.object({
        quantity: z
          .string()
          .trim()
          .regex(/^\d{1,14}(\.\d{1,4})?$/, "请输入非负数量，最多四位小数"),
      }),
    )
    .refine(
      (lines) => lines.some((line) => Number(line.quantity) > 0),
      "至少填写一项正数收货量",
    ),
});
const closeSchema = z.object({
  reason: z.string().trim().min(1, "请填写关闭原因").max(1000),
});
function errorText(error: unknown) {
  if (error instanceof ApiClientError) {
    if (error.problem.status === 409)
      return "采购数据已变化或数量不符合要求。请取消并刷新采购单后核对；不要重复收货。";
    if (error.problem.status === 403) return "当前成员没有采购操作权限。";
    if (error.problem.code === "RECEIPT_DATE_IN_FUTURE")
      return "收货日期不能晚于组织当前业务日。";
  }
  return "未能确认操作结果。保留原表单重试，系统会核对重复提交。";
}
function ReceiptForm({
  order,
  cancel,
}: {
  order: PurchaseOrder;
  cancel: () => void;
}) {
  const items = order.items ?? [];
  const command = usePurchaseReceiptCommand(order.id);
  const [submission, setSubmission] = useState<{
    payload: string;
    value: string;
  } | null>(null);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: {
      reference: "",
      received_date: "",
      lines: items.map(() => ({ quantity: "0" })),
    },
  });
  return (
    <form
      className="supplier-confirm"
      onSubmit={form.handleSubmit((data) => {
        const body = {
          reference: data.reference,
          received_date: data.received_date,
          expected_version: order.version,
          items: data.lines.flatMap((line, index) =>
            Number(line.quantity) > 0
              ? [
                  {
                    purchase_order_item_id: items[index].id,
                    quantity: line.quantity,
                  },
                ]
              : [],
          ),
        };
        const payload = JSON.stringify(body);
        const key =
          submission?.payload === payload
            ? submission.value
            : crypto.randomUUID();
        setSubmission({ payload, value: key });
        command.mutate(
          { command: "receive", body, key },
          { onSuccess: cancel },
        );
      })}
    >
      <h4>记录本次收货</h4>
      <label>
        收货凭证号或说明
        <input {...form.register("reference")} />
      </label>
      {form.formState.errors.reference && (
        <p role="alert">{form.formState.errors.reference.message}</p>
      )}
      <label>
        收货日期
        <input type="date" {...form.register("received_date")} />
      </label>
      {form.formState.errors.received_date && (
        <p role="alert">{form.formState.errors.received_date.message}</p>
      )}
      {items.map((item, index) => (
        <div key={item.id}>
          <label>
            {item.sku_snapshot} 本次收货量
            <input
              inputMode="decimal"
              {...form.register(`lines.${index}.quantity`)}
            />
          </label>
          <p>
            订货 {item.quantity} · 已收 {item.received_quantity}{" "}
            {item.unit_snapshot}
          </p>
          {form.formState.errors.lines?.[index]?.quantity && (
            <p role="alert">
              {form.formState.errors.lines[index]?.quantity?.message}
            </p>
          )}
        </div>
      ))}
      {form.formState.errors.lines?.root?.message && (
        <p role="alert">{form.formState.errors.lines.root.message}</p>
      )}
      {command.isError && <p role="alert">{errorText(command.error)}</p>}
      <div className="purchase-actions">
        <button
          type="submit"
          className="primary-button"
          disabled={command.isPending}
        >
          {command.isPending ? "正在记录…" : "确认本次收货"}
        </button>
        <button
          type="button"
          className="secondary-button"
          disabled={command.isPending}
          onClick={cancel}
        >
          取消收货
        </button>
      </div>
    </form>
  );
}
function CloseForm({
  order,
  cancel,
}: {
  order: PurchaseOrder;
  cancel: () => void;
}) {
  const command = usePurchaseReceiptCommand(order.id);
  const [submission, setSubmission] = useState<{
    payload: string;
    value: string;
  } | null>(null);
  const form = useForm<z.infer<typeof closeSchema>>({
    resolver: zodResolver(closeSchema),
    defaultValues: { reason: "" },
  });
  return (
    <form
      className="supplier-confirm"
      onSubmit={form.handleSubmit((body) => {
        const payload = JSON.stringify(body);
        const key =
          submission?.payload === payload
            ? submission.value
            : crypto.randomUUID();
        setSubmission({ payload, value: key });
        command.mutate(
          {
            command: "close",
            body: { ...body, expected_version: order.version },
            key,
          },
          { onSuccess: cancel },
        );
      })}
    >
      <p>关闭仅确认采购履约结束，不表示供应商款项已结清。</p>
      <label>
        关闭原因
        <textarea {...form.register("reason")} rows={3} />
      </label>
      {form.formState.errors.reason && (
        <p role="alert">{form.formState.errors.reason.message}</p>
      )}
      {command.isError && <p role="alert">{errorText(command.error)}</p>}
      <div className="purchase-actions">
        <button
          type="submit"
          className="primary-button"
          disabled={command.isPending}
        >
          确认关闭采购单
        </button>
        <button
          type="button"
          className="secondary-button"
          disabled={command.isPending}
          onClick={cancel}
        >
          取消关闭
        </button>
      </div>
    </form>
  );
}
export function PurchaseReceiving({ order }: { order: PurchaseOrder }) {
  const scope = useSessionScope();
  const member = useMemberContext(scope);
  const [editor, setEditor] = useState<{
    version: number;
    mode: "receive" | "close";
  } | null>(null);
  const editing = editor !== null && editor.version === order.version;
  const [history, setHistory] = useState(false);
  const canWrite = member.data?.permissions.includes("procurement.write");
  return (
    <section aria-label="采购收货进度">
      <dl>
        {(order.items ?? []).map((item) => (
          <div key={item.id}>
            <dt>{item.sku_snapshot}</dt>
            <dd>
              已收 {item.received_quantity} / {item.quantity}{" "}
              {item.unit_snapshot}
            </dd>
          </div>
        ))}
      </dl>
      {member.isPending && <p role="status">正在确认收货权限…</p>}
      {member.isError && <p role="alert">无法确认采购权限，请刷新页面。</p>}
      {!member.isPending && !member.isError && !canWrite && (
        <p>当前成员无收货或关闭权限。</p>
      )}
      {canWrite &&
        (order.status === "CONFIRMED" ||
          order.status === "PARTIALLY_RECEIVED") &&
        !editing && (
          <button
            className="secondary-button"
            onClick={() =>
              setEditor({ version: order.version, mode: "receive" })
            }
          >
            记录收货
          </button>
        )}
      {canWrite && order.status === "RECEIVED" && !editing && (
        <button
          className="secondary-button"
          onClick={() => setEditor({ version: order.version, mode: "close" })}
        >
          关闭采购单
        </button>
      )}
      {canWrite &&
        editing &&
        editor?.mode === "receive" &&
        (order.status === "CONFIRMED" ||
          order.status === "PARTIALLY_RECEIVED") && (
          <ReceiptForm
            key={order.version}
            order={order}
            cancel={() => setEditor(null)}
          />
        )}
      {canWrite &&
        editing &&
        editor?.mode === "close" &&
        order.status === "RECEIVED" && (
          <CloseForm
            key={order.version}
            order={order}
            cancel={() => setEditor(null)}
          />
        )}
      {editor !== null && !editing && (
        <p role="status">采购记录已更新，请核对最新数据后继续。</p>
      )}
      {order.closed_at && (
        <p>关闭时间：{new Date(order.closed_at).toLocaleString("zh-CN")}</p>
      )}
      {member.data?.permissions.includes("procurement.read") && (
        <button
          className="secondary-button"
          onClick={() => setHistory(!history)}
        >
          {history ? "收起采购记录" : "查看采购记录"}
        </button>
      )}
      {history && <PurchaseHistory id={order.id} />}
    </section>
  );
}

const purchaseActivityLabels: Record<string, string> = {
  "purchase_order.created": "已建立采购草稿",
  "purchase_order.approved": "采购审批通过",
  "purchase_order.sent": "已登记采购发送",
  "purchase_order.confirmed": "已登记供应商确认",
  "purchase_order.receipt_recorded": "已登记采购收货",
  "purchase_order.closed": "采购履约已关闭",
  "purchase_order.cancelled": "已取消未收货部分",
  "purchase_order.replaced": "已生成替代采购草稿",
};

function PurchaseHistory({ id }: { id: string }) {
  const [offset, setOffset] = useState(0);
  const query = usePurchaseActivities(id, offset);
  return (
    <section aria-label="采购操作记录">
      {query.isPending && <p role="status">正在读取采购记录…</p>}
      {query.isError && <p role="alert">无法读取采购记录，请重试。</p>}
      <button
        className="secondary-button"
        disabled={query.isFetching}
        onClick={() => void query.refetch()}
      >
        刷新采购记录
      </button>
      {query.data && (
        <ul>
          {query.data.items.slice(0, 10).map((item) => (
            <li key={item.id}>
              <time dateTime={item.occurred_at}>
                {new Date(item.occurred_at).toLocaleString("zh-CN")}
              </time>
              <p>
                {item.summary === null
                  ? "正文待审核"
                  : (purchaseActivityLabels[item.summary] ?? item.summary)}
              </p>
              <WorkTextReview
                subjectType="purchase_order"
                subjectId={id}
                recordId={item.id}
                onChanged={() => query.refetch()}
              />
            </li>
          ))}
        </ul>
      )}
      {query.data?.items.length === 0 && <p>本页暂无采购记录。</p>}
      <div className="purchase-actions">
        <button
          className="secondary-button"
          disabled={offset === 0 || query.isFetching}
          onClick={() => setOffset(Math.max(0, offset - 10))}
        >
          上一页记录
        </button>
        <button
          className="secondary-button"
          disabled={
            !query.data ||
            query.data.items.length <= 10 ||
            query.isFetching ||
            query.isError
          }
          onClick={() => setOffset(offset + 10)}
        >
          下一页记录
        </button>
      </div>
    </section>
  );
}
