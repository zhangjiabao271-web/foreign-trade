"use client";

import { useQuery } from "@tanstack/react-query";

import { getPlatformHealth } from "@/lib/platform-health";

const statusText = {
  ready: "就绪",
  degraded: "依赖未就绪",
  unavailable: "暂不可达",
} as const;

export function SystemHealth() {
  const query = useQuery({
    queryKey: ["platform-health"],
    queryFn: ({ signal }) => getPlatformHealth(signal),
    refetchInterval: 30_000,
  });

  const apiStatus = query.data?.api ?? "unavailable";
  const isLoading = query.isLoading;

  return (
    <section
      className="health-panel"
      aria-labelledby="health-title"
      aria-live="polite"
    >
      <div>
        <p className="section-kicker">系统检查</p>
        <h2 id="health-title">Task 002 基础服务</h2>
      </div>
      <dl className="health-list">
        <div>
          <dt>Web 壳层</dt>
          <dd data-status="ready">
            <span aria-hidden="true" />
            就绪
          </dd>
        </div>
        <div>
          <dt>API 与依赖</dt>
          <dd data-status={isLoading ? "checking" : apiStatus}>
            <span aria-hidden="true" />
            {isLoading ? "检查中" : statusText[apiStatus]}
          </dd>
        </div>
      </dl>
      {query.isError ? (
        <p className="health-note">
          API 尚未启动。运行 Docker Compose 后此处会自动复检。
        </p>
      ) : null}
    </section>
  );
}
