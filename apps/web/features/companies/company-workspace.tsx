"use client";

import { WorkTextReview } from "../finance/work-review";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMemberContext } from "../overview/api";
import { useSessionScope } from "../overview/session";
import {
  useCompanies,
  useCompany,
  useContacts,
  useCompanyHistory,
  useArchiveCommand,
  type Company,
  type Contact,
  type CompanyRole,
} from "./api";
import { CompanyForm, ContactForm, roleLabels, archiveError } from "./forms";

function Pager({
  previous,
  next,
  busy,
  onPrevious,
  onNext,
  label,
}: {
  previous: boolean;
  next: boolean;
  busy: boolean;
  onPrevious: () => void;
  onNext: () => void;
  label: string;
}) {
  return (
    <nav className="queue-pagination" aria-label={label}>
      <button
        className="secondary-button"
        disabled={!previous || busy}
        onClick={onPrevious}
      >
        上一页
      </button>
      <button
        className="secondary-button"
        disabled={!next || busy}
        onClick={onNext}
      >
        下一页
      </button>
    </nav>
  );
}
function CompanyList({
  scope,
  writable,
}: {
  scope: string;
  writable: boolean;
}) {
  const router = useRouter();
  const [filter, setFilter] = useState<{ query: string; role?: CompanyRole }>({
    query: "",
  });
  const [cursors, setCursors] = useState<Array<string | undefined>>([
    undefined,
  ]);
  const [creating, setCreating] = useState(false);
  const query = useCompanies(scope, filter.query, filter.role, cursors.at(-1));
  const schema = z.object({
    query: z.string().trim().max(240, "名称最多 240 字"),
    role: z.enum(["", "CUSTOMER", "SUPPLIER", "FORWARDER", "AGENT"]),
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { query: "", role: "" },
  });
  return (
    <section className="action-queue opportunity-panel">
      <header>
        <h1>客商档案</h1>
        {writable && !creating && (
          <button className="primary-button" onClick={() => setCreating(true)}>
            新建公司
          </button>
        )}
      </header>
      <p>一家公司，一份档案；客户、供应商、货代与代理角色在此汇合。</p>
      {creating && writable && (
        <CompanyForm
          scope={scope}
          onClose={() => setCreating(false)}
          onSaved={(id) => router.push(`/companies/${id}`)}
        />
      )}
      <form
        className="finance-form"
        onSubmit={form.handleSubmit((values) => {
          setFilter({ query: values.query, role: values.role || undefined });
          setCursors([undefined]);
        })}
      >
        <label>
          公司名称检索
          <input {...form.register("query")} maxLength={240} />
        </label>
        <label>
          业务角色
          <select {...form.register("role")}>
            <option value="">全部角色</option>
            {Object.entries(roleLabels).map(([value, label]) => (
              <option value={value} key={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {form.formState.errors.query && (
          <p role="alert">{form.formState.errors.query.message}</p>
        )}
        <button className="secondary-button" disabled={query.isFetching}>
          检索档案
        </button>
      </form>
      <button
        className="secondary-button"
        disabled={query.isFetching}
        onClick={() => void query.refetch()}
      >
        刷新列表
      </button>
      {query.isPending && <p role="status">正在读取档案…</p>}
      {query.isError && <p role="alert">{archiveError(query.error)}</p>}
      {query.data?.items.length === 0 && (
        <p>没有符合条件的档案。请调整检索条件，或确认后新建公司。</p>
      )}
      <ul>
        {query.data?.items.map((row) => (
          <li key={row.id}>
            <Link href={`/companies/${row.id}`}>
              <strong>{row.name}</strong>
              <span>
                {(row.roles ?? [])
                  .map((role) => roleLabels[role])
                  .join(" · ") || "暂无角色"}
              </span>
              <span>{row.country_code || "国家未填写"}</span>
            </Link>
          </li>
        ))}
      </ul>
      <Pager
        label="公司分页"
        previous={cursors.length > 1}
        next={Boolean(query.data?.has_more && query.data.next_cursor)}
        busy={query.isFetching || query.isError}
        onPrevious={() => setCursors(cursors.slice(0, -1))}
        onNext={() =>
          setCursors([...cursors, query.data?.next_cursor ?? undefined])
        }
      />
    </section>
  );
}
function RoleForm({
  scope,
  row,
  onSaved,
}: {
  scope: string;
  row: Company;
  onSaved: () => void;
}) {
  const mutation = useArchiveCommand(scope);
  const schema = z.object({
    role: z.enum(["CUSTOMER", "SUPPLIER", "FORWARDER", "AGENT"], {
      error: "请选择要增加的角色",
    }),
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
  });
  const available = (Object.keys(roleLabels) as CompanyRole[]).filter(
    (role) => !row.roles?.includes(role),
  );
  if (!available.length) return null;
  return (
    <form
      className="purchase-change-form"
      onSubmit={form.handleSubmit((body) =>
        mutation.mutate(
          { kind: "add-role", id: row.id, body },
          {
            onSuccess: () => {
              form.reset();
              onSaved();
            },
          },
        ),
      )}
    >
      <fieldset disabled={mutation.isPending}>
        <label>
          增加业务角色
          <select {...form.register("role")} defaultValue="">
            <option value="" disabled>
              请选择角色
            </option>
            {available.map((role) => (
              <option value={role} key={role}>
                {roleLabels[role]}
              </option>
            ))}
          </select>
        </label>
        <p>仅增加角色，已有角色和业务记录保持不变。</p>
        {form.formState.errors.role && (
          <p role="alert">{form.formState.errors.role.message}</p>
        )}
        {mutation.isError && <p role="alert">{archiveError(mutation.error)}</p>}
        <button className="secondary-button">
          {mutation.isPending ? "正在保存…" : "确认增加角色"}
        </button>
      </fieldset>
    </form>
  );
}
function Contacts({
  scope,
  id,
  writable,
}: {
  scope: string;
  id: string;
  writable: boolean;
}) {
  const [cursors, setCursors] = useState<Array<string | undefined>>([
    undefined,
  ]);
  const [editing, setEditing] = useState<Contact | "new" | null>(null);
  const [notice, setNotice] = useState("");
  const query = useContacts(scope, id, cursors.at(-1));
  return (
    <section aria-label="联系人档案">
      <h2>联系人</h2>
      {writable && !editing && (
        <button
          className="secondary-button"
          onClick={() => {
            setEditing("new");
            setNotice("");
          }}
        >
          新建联系人
        </button>
      )}
      {writable && editing && (
        <ContactForm
          key={editing === "new" ? "new" : `${editing.id}-${editing.version}`}
          scope={scope}
          companyId={id}
          row={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setCursors([undefined]);
            setNotice("联系人已保存。");
          }}
        />
      )}
      {notice && <p role="status">{notice}</p>}
      {query.isPending && <p role="status">正在读取联系人…</p>}
      {query.isError && (
        <div role="alert">
          <p>{archiveError(query.error)}</p>
          <button
            className="secondary-button"
            onClick={() => void query.refetch()}
          >
            重试联系人
          </button>
        </div>
      )}
      {query.data?.items.length === 0 && <p>暂无联系人。</p>}
      <ul>
        {query.data?.items.map((row) => (
          <li key={row.id}>
            <strong>{row.full_name}</strong>
            <p>{row.job_title || "职务未填写"}</p>
            <p>
              {row.email || "邮箱未填写"} · {row.phone || "电话未填写"}
            </p>
            {writable && !editing && (
              <button
                className="secondary-button"
                onClick={() => {
                  setEditing(row);
                  setNotice("");
                }}
                aria-label={`编辑联系人 ${row.full_name}`}
              >
                编辑联系人
              </button>
            )}
          </li>
        ))}
      </ul>
      <Pager
        label="联系人分页"
        previous={cursors.length > 1}
        next={Boolean(query.data?.has_more && query.data.next_cursor)}
        busy={query.isFetching || query.isError || Boolean(editing)}
        onPrevious={() => setCursors(cursors.slice(0, -1))}
        onNext={() =>
          setCursors([...cursors, query.data?.next_cursor ?? undefined])
        }
      />
    </section>
  );
}
function CompanyHistory({ scope, id }: { scope: string; id: string }) {
  const [offset, setOffset] = useState(0);
  const query = useCompanyHistory(scope, id, offset);
  return (
    <section>
      <h2>档案时间线</h2>
      {query.isPending && <p role="status">正在读取记录…</p>}
      {query.isError && (
        <div role="alert">
          <p>{archiveError(query.error)}</p>
          <button
            className="secondary-button"
            onClick={() => void query.refetch()}
          >
            重试时间线
          </button>
        </div>
      )}
      {query.data?.items.length === 0 && <p>暂无档案维护记录。</p>}
      <ul>
        {query.data?.items.map((item) => (
          <li key={item.id}>
            <p>{item.summary ?? "保密活动：待审核后开放"}</p>
            <WorkTextReview
              subjectType="company"
              subjectId={id}
              recordId={item.id}
              onChanged={() => query.refetch()}
            />
            <time dateTime={item.occurred_at}>
              {new Date(item.occurred_at).toLocaleString("zh-CN")}
            </time>
          </li>
        ))}
      </ul>
      <Pager
        label="档案时间线分页"
        previous={offset > 0}
        next={Boolean(query.data?.has_more)}
        busy={query.isFetching || query.isError}
        onPrevious={() => setOffset(Math.max(0, offset - 10))}
        onNext={() => setOffset(offset + 10)}
      />
    </section>
  );
}
function CompanyDetail({
  scope,
  id,
  writable,
}: {
  scope: string;
  id: string;
  writable: boolean;
}) {
  const query = useCompany(scope, id);
  const [editing, setEditing] = useState<Company | null>(null);
  const [notice, setNotice] = useState("");
  if (query.isPending) return <p role="status">正在读取公司档案…</p>;
  if (query.isError)
    return (
      <section role="alert">
        <p>{archiveError(query.error)}</p>
        <button
          className="secondary-button"
          onClick={() => void query.refetch()}
        >
          重试档案
        </button>
      </section>
    );
  const row = query.data;
  return (
    <section className="action-queue opportunity-panel">
      <header>
        <h1>{row.name}</h1>
        <button
          className="secondary-button"
          disabled={query.isFetching || Boolean(editing)}
          onClick={() => void query.refetch()}
        >
          刷新档案
        </button>
      </header>
      <p className="section-kicker">
        {(row.roles ?? []).map((role) => roleLabels[role]).join(" · ") ||
          "暂无业务角色"}
      </p>
      <p>国家：{row.country_code || "未填写"}</p>
      <p>网站：{row.website || "未填写"}</p>
      <p>此处维护当前资料，不改写已发送报价和订单商业快照。</p>
      {notice && <p role="status">{notice}</p>}
      {writable && !editing && (
        <button
          className="secondary-button"
          onClick={() => {
            setEditing(row);
            setNotice("");
          }}
        >
          编辑公司资料
        </button>
      )}
      {writable && editing && (
        <CompanyForm
          key={`${editing.id}-${editing.version}`}
          scope={scope}
          row={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setNotice("公司资料已保存。");
          }}
        />
      )}
      {writable && !editing && (
        <RoleForm
          key={row.id}
          scope={scope}
          row={row}
          onSaved={() => setNotice("业务角色已增加。")}
        />
      )}
      <Contacts scope={scope} id={id} writable={writable} />
      <CompanyHistory scope={scope} id={id} />
    </section>
  );
}
function Connected({ scope, id }: { scope: string; id?: string }) {
  const member = useMemberContext(scope);
  if (member.isPending) return <p role="status">正在确认权限…</p>;
  if (member.isError) return <p role="alert">{archiveError(member.error)}</p>;
  if (!member.data.permissions.includes("company.read"))
    return <p role="alert">当前成员无档案查看权限。</p>;
  const writable = member.data.permissions.includes("company.write");
  return id ? (
    <CompanyDetail key={id} scope={scope} id={id} writable={writable} />
  ) : (
    <CompanyList scope={scope} writable={writable} />
  );
}
export function CompanyWorkspace({ id }: { id?: string }) {
  const scope = useSessionScope();
  return (
    <main id="main-content" className="overview-shell">
      <header className="topbar">
        <Link className="brand" href="/">
          外贸工作台
        </Link>
        <nav className="overview-nav" aria-label="客商导航">
          <Link href="/companies">全部客商</Link>
          <Link href="/leads">线索</Link>
          <Link href="/opportunities">商机</Link>
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
