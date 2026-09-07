"use client";
import { WorkTextReview } from "../finance/work-review";
import { useState } from "react";
import { ResumeUpload } from "../documents/resume-upload";
import { DocumentReview } from "../documents/review";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import type { SalesOrder } from "../orders/api";
import { useMemberContext } from "../overview/api";
import { useSessionScope } from "../overview/session";
import { ContractForm, contractError } from "./forms";
import {
  useContracts,
  useContractDocuments,
  useContractUpload,
  useContractDownload,
  type Contract,
} from "./api";

const uploadSchema = z.object({
  file: z
    .custom<FileList>()
    .refine(
      (files) =>
        files?.length === 1 &&
        files[0]!.size > 0 &&
        files[0]!.size <= 25 * 1024 * 1024,
      "请选择一个非空且不超过 25 MB 的文件",
    ),
});
function Upload({ scope, orderId }: { scope: string; orderId: string }) {
  const mutation = useContractUpload(scope, orderId);
  const form = useForm<z.infer<typeof uploadSchema>>({
    resolver: zodResolver(uploadSchema),
  });
  return (
    <form
      className="finance-form"
      onSubmit={form.handleSubmit((v) =>
        mutation.mutate(v.file[0]!, { onSuccess: () => form.reset() }),
      )}
    >
      <label>
        上传签署合同文件
        <input
          type="file"
          {...form.register("file")}
          disabled={mutation.isPending}
        />
      </label>
      {form.formState.errors.file && (
        <p role="alert">{form.formState.errors.file.message}</p>
      )}
      {mutation.isError && <p role="alert">{contractError(mutation.error)}</p>}
      {mutation.isSuccess && (
        <p role="status">文件已上传，待校验完成后刷新证据列表。</p>
      )}
      <button className="secondary-button" disabled={mutation.isPending}>
        {mutation.isPending ? "正在上传…" : "上传合同证据"}
      </button>
    </form>
  );
}
function Panel({
  scope,
  order,
  permissions,
}: {
  scope: string;
  order: SalesOrder;
  permissions: string[];
}) {
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const query = useContracts(scope, order.id, cursors.at(-1));
  const docs = useContractDocuments(scope, order.id);
  const download = useContractDownload();
  const [editing, setEditing] = useState<{
    mode: "create" | "update" | "sign" | "void";
    contract?: Contract;
  }>();
  const [notice, setNotice] = useState("");
  const active = order.status !== "CANCELLED" && order.status !== "COMPLETED";
  return (
    <section className="finance-section contract-section" aria-label="销售合同">
      <p className="section-kicker">合同凭证 · 商业快照</p>
      <h2>销售合同</h2>
      <p>
        从已接受报价的订单建立合同，登记人工签署事实，不改变订单或收付款状态。
      </p>
      {notice && <p role="status">{notice}</p>}
      {query.isPending && <p role="status">正在读取合同…</p>}
      {query.isError && <p role="alert">{contractError(query.error)}</p>}
      <button
        className="quiet-button"
        onClick={() => query.refetch()}
        disabled={query.isFetching}
      >
        刷新合同
      </button>
      {active &&
        permissions.includes("contract.write") &&
        !editing &&
        query.isSuccess &&
        cursors.length === 1 &&
        !query.data.items.some((row) => row.status !== "VOIDED") && (
          <button
            className="secondary-button"
            onClick={() => {
              setNotice("");
              setEditing({ mode: "create" });
            }}
          >
            建立合同草稿
          </button>
        )}
      {editing && (
        <ContractForm
          scope={scope}
          orderId={order.id}
          mode={editing.mode}
          contract={editing.contract}
          documents={docs.data ?? []}
          onDone={() => {
            setEditing(undefined);
            setNotice("合同操作已保存，关键事实已记入订单时间线。");
          }}
          onCancel={() => setEditing(undefined)}
        />
      )}
      {query.data?.items.length === 0 && <p>此订单尚无合同记录。</p>}
      {query.data?.items.map((row) => (
        <article className="finance-payment" key={row.id}>
          <h3>
            {row.contract_number} ·{" "}
            {{ DRAFT: "草稿", SIGNED: "已签署", VOIDED: "已作废" }[row.status]}
          </h3>
          <p>
            {row.commercial_snapshot.seller_name} →{" "}
            {row.commercial_snapshot.customer_name}
          </p>
          <strong>
            {row.total} {row.currency_code}
          </strong>
          <p>外部编号：{row.external_reference ?? "未填写"}</p>
          <details>
            <summary>查看合同商业快照</summary>
            <p>
              付款：
              {row.content_visible
                ? (row.commercial_snapshot.payment_terms ?? "未填写")
                : "待审核"}
            </p>
            <p>
              交付：
              {row.content_visible
                ? (row.commercial_snapshot.delivery_terms ?? "未填写")
                : "待审核"}
            </p>
            <p>
              定金：{row.commercial_snapshot.deposit_amount} {row.currency_code}{" "}
              · {row.commercial_snapshot.deposit_due_date ?? "未约定日期"}
            </p>
            <ul>
              {row.commercial_snapshot.items.map((item) => (
                <li key={item.line_number}>
                  {item.sku} · {item.description ?? "说明待审核"} ·{" "}
                  {item.quantity} {item.unit} × {item.unit_price} ·
                  含税费运费合计 {item.line_total} {row.currency_code}
                </li>
              ))}
            </ul>
            <p>备注：{row.content_visible ? (row.notes ?? "无") : "待审核"}</p>
          </details>
          <section aria-label="合同文本审核">
            <WorkTextReview
              commercialKind="sales_contract"
              recordId={row.id}
              onChanged={() => query.refetch()}
            />
          </section>
          {row.status === "SIGNED" && (
            <p>
              签署日期：{row.signed_on} · 固定证据版本：
              {row.signed_document_version_id}
            </p>
          )}
          {row.signed_document_version_id &&
            docs.data?.map(
              (d) =>
                (d.versions ?? []).some(
                  (v) => v.id === row.signed_document_version_id,
                ) && (
                  <button
                    key={d.id}
                    className="secondary-button"
                    disabled={download.isPending}
                    onClick={() =>
                      download.mutate({
                        documentId: d.id,
                        versionId: row.signed_document_version_id!,
                      })
                    }
                  >
                    下载签署证据
                  </button>
                ),
            )}
          {row.status === "DRAFT" && active && !editing && (
            <div className="queue-pagination">
              {permissions.includes("contract.write") && (
                <>
                  <button
                    className="secondary-button"
                    onClick={() =>
                      setEditing({ mode: "update", contract: row })
                    }
                  >
                    编辑合同备注
                  </button>
                  <button
                    className="quiet-button"
                    onClick={() => setEditing({ mode: "void", contract: row })}
                  >
                    作废合同草稿
                  </button>
                </>
              )}
              {permissions.includes("contract.sign") &&
                order.status !== "DRAFT" && (
                  <button
                    className="primary-button"
                    onClick={() => setEditing({ mode: "sign", contract: row })}
                  >
                    登记合同签署
                  </button>
                )}
            </div>
          )}
        </article>
      ))}
      <nav className="queue-pagination" aria-label="合同分页">
        <button
          className="secondary-button"
          disabled={
            cursors.length === 1 || query.isFetching || Boolean(editing)
          }
          onClick={() => setCursors((v) => v.slice(0, -1))}
        >
          上一页合同
        </button>
        <button
          className="secondary-button"
          disabled={
            !query.data?.has_more ||
            query.isFetching ||
            query.isError ||
            Boolean(editing)
          }
          onClick={() => {
            const next = query.data?.next_cursor;
            if (next) setCursors((v) => [...v, next]);
          }}
        >
          下一页合同
        </button>
      </nav>
      <h3>签署文件证据</h3>
      {docs.isError && <p role="alert">{contractError(docs.error)}</p>}
      {download.isError && <p role="alert">{contractError(download.error)}</p>}
      <button
        className="secondary-button"
        onClick={() => docs.refetch()}
        disabled={docs.isFetching}
      >
        刷新合同证据
      </button>
      {docs.isPending && <p role="status">正在读取合同证据…</p>}
      {docs.data?.map((d) => (
        <div key={d.id}>
          <p>
            {d.title ?? "待审核附件"} ·{" "}
            {(d.versions ?? [])
              .map(
                (v) =>
                  `第 ${v.version_number} 版：${v.status === "AVAILABLE" ? "已验收" : "待校验或不可用"}`,
              )
              .join("；")}
          </p>
          <DocumentReview document={d} onChanged={() => docs.refetch()} />
          {active && permissions.includes("document.write") && (
            <ResumeUpload document={d} onRecovered={() => docs.refetch()} />
          )}
        </div>
      ))}
      {active && permissions.includes("document.write") && (
        <Upload scope={scope} orderId={order.id} />
      )}
      {!permissions.includes("document.write") && (
        <p>上传合同文件请交由经理或运营成员处理。</p>
      )}
    </section>
  );
}
export function OrderContracts({ order }: { order: SalesOrder }) {
  const scope = useSessionScope();
  const member = useMemberContext(scope);
  if (!scope || member.isPending) return <p role="status">正在确认合同权限…</p>;
  if (member.isError) return <p role="alert">{contractError(member.error)}</p>;
  if (!member.data.permissions.includes("contract.read"))
    return <p>当前成员无合同读取权限。</p>;
  return (
    <Panel
      key={`${scope}:${order.id}`}
      scope={scope}
      order={order}
      permissions={member.data.permissions}
    />
  );
}
