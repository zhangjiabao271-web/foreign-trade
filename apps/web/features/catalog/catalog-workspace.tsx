"use client";
import { WorkTextReview } from "../finance/work-review";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useSessionScope } from "../overview/session";
import { useMemberContext } from "../overview/api";
import {
  useProducts,
  useProduct,
  useSupplierLinks,
  useSupplierHistory,
  type SupplierLink,
} from "./api";
import { SupplierForm, supplierError } from "./supplier-form";

function ProductList({
  scope,
  canCreate,
}: {
  scope: string;
  canCreate: boolean;
}) {
  const [search, setSearch] = useState("");
  const [cursors, setCursors] = useState<Array<string | undefined>>([
    undefined,
  ]);
  const query = useProducts(scope, search, cursors.at(-1));
  const schema = z.object({
    query: z.string().trim().max(240, "检索条件最多 240 字"),
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { query: "" },
  });
  return (
    <section className="action-queue opportunity-panel">
      <h1>产品与供应商</h1>
      <p>检索产品名称、SKU 与单位。成本及供应商参考价格仅向获授权成员开放。</p>
      <form
        className="finance-form"
        onSubmit={form.handleSubmit((values) => {
          setSearch(values.query);
          setCursors([undefined]);
        })}
      >
        <label>
          产品名称或 SKU
          <input {...form.register("query")} />
        </label>
        {form.formState.errors.query && (
          <p role="alert">{form.formState.errors.query.message}</p>
        )}
        <button className="secondary-button" disabled={query.isFetching}>
          检索产品
        </button>
      </form>
      {canCreate ? (
        <Link href="/quotations">前往报价工作台建立产品</Link>
      ) : (
        <p>需要新产品时，请联系经理或管理员维护。</p>
      )}
      {query.isPending && <p role="status">正在读取产品…</p>}
      {query.isError && (
        <div role="alert">
          <p>{supplierError(query.error)}</p>
          <button
            className="secondary-button"
            onClick={() => void query.refetch()}
          >
            重试
          </button>
        </div>
      )}
      {query.data?.items.length === 0 && (
        <p>未找到产品。请调整名称或 SKU，或先建立产品。</p>
      )}
      <ul>
        {query.data?.items.map((row) => (
          <li key={row.id}>
            <Link href={`/products/${row.id}`}>
              <strong>{row.name}</strong>
              <span>
                {row.sku} · {row.unit}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      <nav className="queue-pagination" aria-label="产品目录分页">
        <button
          className="secondary-button"
          disabled={cursors.length === 1 || query.isFetching}
          onClick={() => setCursors(cursors.slice(0, -1))}
        >
          上一页产品
        </button>
        <span role="status">第 {cursors.length} 页</span>
        <button
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
          下一页产品
        </button>
      </nav>
    </section>
  );
}
function History({ scope, id }: { scope: string; id: string }) {
  const [offset, setOffset] = useState(0);
  const query = useSupplierHistory(scope, id, offset);
  return (
    <section>
      <h2>供应商参考时间线</h2>
      {query.isPending && <p role="status">正在读取记录…</p>}
      {query.isError && (
        <div role="alert">
          <p>{supplierError(query.error)}</p>
          <button
            className="secondary-button"
            onClick={() => void query.refetch()}
          >
            重试记录
          </button>
        </div>
      )}
      {query.data?.items.length === 0 && <p>暂无供应商参考记录。</p>}
      <ul>
        {query.data?.items.map((row) => (
          <li key={row.id}>
            <p>{row.summary}</p>
            <time dateTime={row.occurred_at}>
              {new Date(row.occurred_at).toLocaleString("zh-CN")}
            </time>
          </li>
        ))}
      </ul>
      <nav className="queue-pagination" aria-label="供应商时间线分页">
        <button
          className="secondary-button"
          disabled={offset === 0 || query.isFetching}
          onClick={() => setOffset(Math.max(0, offset - 10))}
        >
          较新记录
        </button>
        <button
          className="secondary-button"
          disabled={!query.data?.has_more || query.isFetching || query.isError}
          onClick={() => setOffset(offset + 10)}
        >
          更早记录
        </button>
      </nav>
    </section>
  );
}
function ProductDetail({
  scope,
  id,
  writable,
}: {
  scope: string;
  id: string;
  writable: boolean;
}) {
  const product = useProduct(scope, id);
  const [cursors, setCursors] = useState<Array<string | undefined>>([
    undefined,
  ]);
  const links = useSupplierLinks(scope, id, cursors.at(-1));
  const [editing, setEditing] = useState<SupplierLink | "new" | null>(null);
  const [notice, setNotice] = useState("");
  if (product.isPending) return <p role="status">正在读取产品…</p>;
  if (product.isError)
    return (
      <div role="alert">
        <p>{supplierError(product.error)}</p>
        <button
          className="secondary-button"
          onClick={() => void product.refetch()}
        >
          重试产品
        </button>
      </div>
    );
  return (
    <section className="action-queue opportunity-panel">
      <header>
        <h1>{product.data.name}</h1>
        <button
          className="secondary-button"
          disabled={Boolean(editing) || links.isFetching}
          onClick={() => {
            void product.refetch();
            void links.refetch();
          }}
        >
          刷新货源
        </button>
      </header>
      <p className="section-kicker">
        {product.data.sku} · 产品单位 {product.data.unit}
      </p>
      <section aria-label="产品说明审核">
        <p>
          {product.data.content_visible
            ? product.data.description || "未填写说明"
            : "产品说明待审核，当前不可见"}
        </p>
        <WorkTextReview
          sourceKind="product"
          recordId={id}
          onChanged={() => product.refetch()}
        />
      </section>
      <p>
        以下为供应商参考信息，不代表已下单或已锁定价格；下单前请重新核对币种、有效期和交期。
      </p>
      {notice && <p role="status">{notice}</p>}
      {writable && !editing && (
        <button
          className="primary-button"
          onClick={() => {
            setEditing("new");
            setNotice("");
          }}
        >
          关联供应商
        </button>
      )}
      {writable && editing && (
        <SupplierForm
          key={editing === "new" ? "new" : `${editing.id}-${editing.version}`}
          scope={scope}
          productId={id}
          row={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setCursors([undefined]);
            setNotice("供应商参考已保存，历史业务快照保持不变。");
          }}
        />
      )}
      {links.isPending && <p role="status">正在读取货源…</p>}
      {links.isError && (
        <div role="alert">
          <p>{supplierError(links.error)}</p>
          <button
            className="secondary-button"
            onClick={() => void links.refetch()}
          >
            重试货源
          </button>
        </div>
      )}
      {links.data?.items.length === 0 && (
        <p>尚未关联供应商。可从统一客商档案选择已有供应商。</p>
      )}
      <ul>
        {links.data?.items.map((row) => (
          <li key={row.id}>
            <Link href={`/companies/${row.supplier_id}`}>
              <strong>{row.supplier_name}</strong>
            </Link>
            <p>供应商货号：{row.supplier_sku}</p>
            <p className="section-kicker">
              {row.currency} {row.unit_price} / {product.data.unit} · 参考交期{" "}
              {row.lead_time_days} 天
            </p>
            <p>
              报价日期：{row.quoted_on} · 有效截止：
              {row.valid_until || "未注明，使用前需确认"}
            </p>
            <p>来源：{row.quotation_reference || "未填写"}</p>
            {writable && !editing && (
              <button
                className="secondary-button"
                onClick={() => {
                  setEditing(row);
                  setNotice("");
                }}
                aria-label={`更新参考 ${row.supplier_name}`}
              >
                更新参考
              </button>
            )}
          </li>
        ))}
      </ul>
      <nav className="queue-pagination" aria-label="产品货源分页">
        <button
          className="secondary-button"
          disabled={
            cursors.length === 1 || links.isFetching || Boolean(editing)
          }
          onClick={() => setCursors(cursors.slice(0, -1))}
        >
          上一页货源
        </button>
        <button
          className="secondary-button"
          disabled={
            !links.data?.has_more ||
            !links.data.next_cursor ||
            links.isFetching ||
            links.isError ||
            Boolean(editing)
          }
          onClick={() =>
            setCursors([...cursors, links.data?.next_cursor ?? undefined])
          }
        >
          下一页货源
        </button>
      </nav>
      <History scope={scope} id={id} />
    </section>
  );
}
function Connected({ scope, id }: { scope: string; id?: string }) {
  const member = useMemberContext(scope);
  if (member.isPending) return <p role="status">正在确认权限…</p>;
  if (member.isError) return <p role="alert">{supplierError(member.error)}</p>;
  const permissions = member.data.permissions;
  if (!permissions.includes("product.read"))
    return <p role="alert">当前成员无产品查看权限。</p>;
  if (
    id &&
    (!permissions.includes("product_supplier.read") ||
      !permissions.includes("profit.read"))
  )
    return <ProductBasics key={id} scope={scope} id={id} />;
  return id ? (
    <ProductDetail
      key={id}
      scope={scope}
      id={id}
      writable={
        permissions.includes("product_supplier.write") &&
        permissions.includes("profit.read")
      }
    />
  ) : (
    <ProductList
      scope={scope}
      canCreate={
        permissions.includes("product.write") &&
        permissions.includes("profit.read")
      }
    />
  );
}

function ProductBasics({ scope, id }: { scope: string; id: string }) {
  const product = useProduct(scope, id);
  if (product.isPending) return <p role="status">正在读取产品…</p>;
  if (product.isError)
    return (
      <div role="alert">
        <p>{supplierError(product.error)}</p>
        <button
          className="secondary-button"
          onClick={() => void product.refetch()}
        >
          重试产品
        </button>
      </div>
    );
  return (
    <section className="action-queue opportunity-panel">
      <h1>{product.data.name}</h1>
      <p>
        {product.data.sku} · 产品单位 {product.data.unit}
      </p>
      <p>
        {product.data.content_visible
          ? product.data.description || "未填写说明"
          : "产品说明待审核，当前不可见"}
      </p>
      <p>
        当前成员无成本与供应商参考价格查看权限。需要定价支持时，请联系经理或管理员。
      </p>
      <Link href="/products">返回产品目录</Link>
    </section>
  );
}
export function CatalogWorkspace({ id }: { id?: string }) {
  const scope = useSessionScope();
  return (
    <main id="main-content" className="overview-shell">
      <header className="topbar">
        <Link className="brand" href="/">
          外贸工作台
        </Link>
        <nav className="overview-nav" aria-label="产品导航">
          <Link href="/products">全部产品</Link>
          <Link href="/companies">客商</Link>
          <Link href="/quotations">报价</Link>
        </nav>
      </header>
      {scope ? (
        <Connected key={scope} scope={scope} id={id} />
      ) : (
        <p>请先登录并选择业务组织。</p>
      )}
    </main>
  );
}
