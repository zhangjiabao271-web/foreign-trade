"use client";
import Link from "next/link";
import { useState } from "react";
import { useMemberContext } from "../overview/api";
import { useSessionScope } from "../overview/session";
import { useMembers, useOrganization } from "./api";
import {
  IdentityForm,
  type IdentityEdit,
  identityError,
  roles,
} from "./identity-form";

function Administration({ scope }: { scope: string }) {
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const [edit, setEdit] = useState<IdentityEdit>();
  const [notice, setNotice] = useState("");
  const organization = useOrganization(scope);
  const members = useMembers(scope, cursors.at(-1));
  return (
    <section className="outbox-ledger" aria-label="当前组织管理">
      <p role="status">{notice}</p>
      {(organization.isPending || members.isPending) && (
        <p role="status">正在读取组织与成员…</p>
      )}
      {(organization.isError || members.isError) && (
        <p role="alert">{identityError(organization.error ?? members.error)}</p>
      )}
      <div className="queue-pagination">
        <button
          className="secondary-button"
          disabled={
            Boolean(edit) || organization.isFetching || members.isFetching
          }
          onClick={() => {
            void organization.refetch();
            void members.refetch();
          }}
        >
          刷新组织与成员
        </button>
      </div>
      {organization.data && !organization.isError && (
        <section className="outbox-event">
          <h2>{organization.data.name}</h2>
          <p>业务时区：{organization.data.timezone} · 不改写历史时间</p>
          <button
            className="secondary-button"
            disabled={Boolean(edit)}
            onClick={() =>
              setEdit({ mode: "settings", organization: organization.data })
            }
          >
            修改组织设置
          </button>
        </section>
      )}
      {edit && (
        <IdentityForm
          scope={scope}
          edit={edit}
          onCancel={() => setEdit(undefined)}
          onDone={() => {
            setEdit(undefined);
            setCursors([undefined]);
            setNotice("操作已保存并留存审计。当前权限已重新检查。");
          }}
        />
      )}
      <header className="queue-pagination">
        <h2>成员授权</h2>
        <button
          className="secondary-button"
          disabled={Boolean(edit)}
          onClick={() => {
            setNotice("");
            setEdit({ mode: "add" });
          }}
        >
          添加已核实成员
        </button>
      </header>
      {members.data && !members.isError && (
        <>
          <p>
            第 {cursors.length} 页 · 本页 {members.data.items.length}{" "}
            位，不是组织总人数
          </p>
          {members.data.items.length === 0 && (
            <p>当前页没有成员，请返回上一页或刷新。</p>
          )}
          {members.data.items.map((member) => (
            <article key={member.id} className="outbox-event">
              <h3>{member.display_name}</h3>
              <p style={{ overflowWrap: "anywhere" }}>
                {member.external_subject}
              </p>
              <p>
                {roles[member.role]} ·{" "}
                {member.status === "ACTIVE"
                  ? "已启用"
                  : member.status === "DISABLED"
                    ? "已停用"
                    : "待授权"}
                {member.user_status !== "ACTIVE" ? " · 全局账号不可用" : ""}
              </p>
              <div className="queue-pagination">
                <button
                  className="secondary-button"
                  disabled={Boolean(edit)}
                  onClick={() => setEdit({ mode: "role", member })}
                >
                  调整角色
                </button>
                {member.status === "DISABLED" ? (
                  <button
                    className="secondary-button"
                    disabled={Boolean(edit) || member.user_status !== "ACTIVE"}
                    onClick={() => setEdit({ mode: "reactivate", member })}
                  >
                    重新启用成员
                  </button>
                ) : (
                  <button
                    className="secondary-button"
                    disabled={Boolean(edit)}
                    onClick={() => setEdit({ mode: "disable", member })}
                  >
                    停用成员
                  </button>
                )}
              </div>
            </article>
          ))}
        </>
      )}
      <nav className="queue-pagination" aria-label="组织成员分页">
        <button
          className="secondary-button"
          disabled={Boolean(edit) || members.isFetching || cursors.length === 1}
          onClick={() => setCursors(cursors.slice(0, -1))}
        >
          上一页
        </button>
        <button
          className="secondary-button"
          disabled={
            Boolean(edit) ||
            members.isFetching ||
            members.isError ||
            !members.data?.has_more
          }
          onClick={() =>
            setCursors([...cursors, members.data?.next_cursor ?? undefined])
          }
        >
          下一页
        </button>
      </nav>
    </section>
  );
}
function Authorized({ scope }: { scope: string }) {
  const member = useMemberContext(scope);
  if (member.isPending) return <p role="status">正在核对管理权限…</p>;
  if (member.isError)
    return (
      <section role="alert">
        <p>{identityError(member.error)}</p>
        <button
          className="secondary-button"
          onClick={() => void member.refetch()}
        >
          重试权限检查
        </button>
      </section>
    );
  if (
    !member.data.permissions.includes("organization.manage") ||
    !member.data.permissions.includes("member.manage")
  )
    return <p role="alert">当前成员没有组织管理权限，请联系管理员。</p>;
  return <Administration scope={scope} />;
}
export function IdentityWorkspace() {
  const scope = useSessionScope();
  return (
    <main id="main-content" className="overview-shell">
      <header className="topbar">
        <Link className="brand" href="/">
          外贸工作台
        </Link>
        <Link href="/">返回经营首页</Link>
      </header>
      <section className="overview-heading">
        <p className="section-kicker">业务空间 / 访问授权</p>
        <h1>组织与成员</h1>
        <p>
          核对谁可以访问当前组织。最后一位有效管理员受到保护；密码与登录账号仍由登录服务管理。
        </p>
      </section>
      {scope ? (
        <Authorized key={scope} scope={scope} />
      ) : (
        <p role="alert">请先登录并选择业务空间。</p>
      )}
    </main>
  );
}
