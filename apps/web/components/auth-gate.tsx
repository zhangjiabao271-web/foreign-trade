"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import type { components } from "@trade-workbench/api-client";
import { sessionKeys } from "../features/leads/api";
import { useSessionScope } from "../features/overview/session";

type AuthSession = {
  configured: boolean;
  authenticated: boolean;
  test_bearer?: boolean;
  marker?: string;
  organizations?: components["schemas"]["MyOrganizationsResponse"];
};
const organizationSchema = z.object({ organization: z.uuid("请选择业务空间") });
const sessionEvent = "trade-workbench-session-change";

function OrganizationChoice({ session }: { session: AuthSession }) {
  const form = useForm<z.infer<typeof organizationSchema>>({
    resolver: zodResolver(organizationSchema),
    defaultValues: { organization: "" },
  });
  const organizations = session.organizations?.items ?? [];
  return (
    <>
      <h1>选择业务空间</h1>
      <p>只显示你已加入的有效组织。切换空间不会改变你的成员权限。</p>
      {organizations.length ? (
        <form
          onSubmit={form.handleSubmit(({ organization }) => {
            if (
              !organizations.some(
                (item) => item.organization_id === organization,
              )
            )
              return;
            localStorage.setItem(sessionKeys.organizationId, organization);
            window.dispatchEvent(new Event(sessionEvent));
          })}
        >
          <label htmlFor="business-organization">业务空间</label>
          <select
            id="business-organization"
            {...form.register("organization")}
            aria-invalid={Boolean(form.formState.errors.organization)}
          >
            <option value="">请选择</option>
            {organizations.map((item) => (
              <option key={item.organization_id} value={item.organization_id}>
                {item.name}
              </option>
            ))}
          </select>
          {form.formState.errors.organization && (
            <p role="alert">{form.formState.errors.organization.message}</p>
          )}
          <button className="primary-button" type="submit">
            进入业务空间
          </button>
        </form>
      ) : (
        <p role="status">
          当前账号没有有效业务成员关系，请联系组织管理员添加。
        </p>
      )}
      <form action="/api/auth/logout" method="post">
        <button className="secondary-button" type="submit">
          退出登录
        </button>
      </form>
    </>
  );
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [failed, setFailed] = useState(false);
  const [checking, setChecking] = useState(true);
  const scope = useSessionScope();
  const [attempt, setAttempt] = useState(0);
  const refresh = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    async function verify() {
      setFailed(false);
      try {
        const response = await fetch("/api/auth/session", {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Session unavailable");
        const next: AuthSession = await response.json();
        if (!active) return;
        if (!next.test_bearer) localStorage.removeItem(sessionKeys.accessToken);
        if (next.authenticated && next.marker) {
          localStorage.setItem(sessionKeys.marker, next.marker);
        } else {
          localStorage.removeItem(sessionKeys.marker);
        }
        window.dispatchEvent(new Event(sessionEvent));
        setSession(next);
      } catch {
        if (!active) return;
        localStorage.removeItem(sessionKeys.marker);
        localStorage.removeItem(sessionKeys.accessToken);
        window.dispatchEvent(new Event(sessionEvent));
        setSession(null);
        setFailed(true);
      } finally {
        if (active) setChecking(false);
      }
    }
    void verify();
    return () => {
      active = false;
      controller.abort();
    };
  }, [attempt]);

  useEffect(() => {
    const changedSession = (event: StorageEvent) => {
      if (event.key === sessionKeys.marker || event.key === null) refresh();
    };
    window.addEventListener("focus", refresh);
    window.addEventListener("storage", changedSession);
    const timer = window.setInterval(refresh, 60_000);
    return () => {
      window.removeEventListener("focus", refresh);
      window.removeEventListener("storage", changedSession);
      window.clearInterval(timer);
    };
  }, [refresh]);

  const organization =
    typeof window === "undefined"
      ? null
      : localStorage.getItem(sessionKeys.organizationId);
  const authorizedSpace =
    session?.authenticated &&
    session.marker &&
    session.marker === localStorage.getItem(sessionKeys.marker) &&
    scope &&
    session.organizations?.items.some(
      (item) => item.organization_id === organization,
    );
  if (!checking && (session?.test_bearer || authorizedSpace)) return children;
  return (
    <main id="main-content" className="connection-shell">
      <section
        className="connection-panel"
        aria-label="登录业务空间"
        aria-busy={checking}
      >
        <p className="section-kicker">外贸工作台 · 受控访问</p>
        {checking ? (
          <p role="status">正在确认登录状态…</p>
        ) : failed ? (
          <>
            <h1>暂时无法确认登录</h1>
            <p role="alert">登录服务或业务服务暂不可用，业务数据已隐藏。</p>
            <button className="primary-button" onClick={refresh}>
              重新检查
            </button>
          </>
        ) : !session?.configured ? (
          <>
            <h1>登录服务尚未配置</h1>
            <p>请管理员完成登录服务配置后再进入业务空间。</p>
            <button className="secondary-button" onClick={refresh}>
              重新检查
            </button>
          </>
        ) : !session.authenticated ? (
          <>
            <h1>登录你的业务空间</h1>
            <p>使用账号登录后，选择所属组织，继续推进订单。</p>
            <a className="primary-button" href="/api/auth/login">
              登录
            </a>
          </>
        ) : (
          <OrganizationChoice session={session} />
        )}
      </section>
    </main>
  );
}
