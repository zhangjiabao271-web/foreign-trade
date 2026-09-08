"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { parseApiError } from "@trade-workbench/api-client";
import { useMemberContext } from "../overview/api";
import { sessionClient, useSessionScope } from "../overview/session";
import { WorkTextReview } from "./work-review";

type Subject = "quotation" | "shipment" | "sales_order";
const settings = {
  quotation: { permission: "quotation.read", title: "报价时间线" },
  shipment: { permission: "shipment.read", title: "出货时间线" },
  sales_order: { permission: "order.read", title: "订单时间线" },
} as const;

async function readPage(subject: Subject, id: string, cursor?: string) {
  const client = sessionClient();
  const query = { cursor, limit: 20 };
  let result;
  if (subject === "quotation")
    result = await client.GET("/api/v1/quotations/{quotation_id}/activities", {
      params: { path: { quotation_id: id }, query },
    });
  else if (subject === "shipment")
    result = await client.GET("/api/v1/shipments/{shipment_id}/activities", {
      params: { path: { shipment_id: id }, query },
    });
  else
    result = await client.GET(
      "/api/v1/sales-orders/{order_id}/activity-history",
      {
        params: { path: { order_id: id }, query },
      },
    );
  if (!result.data) throw await parseApiError(result.response, result.error);
  return result.data;
}

function TimelinePage({
  subject,
  id,
  scope,
  revision,
}: {
  subject: Subject;
  id: string;
  scope: string;
  revision: string | number;
}) {
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const cursor = cursors[cursors.length - 1];
  const cache = useQueryClient();
  const prefix = ["commercial-timeline", scope, subject, id, revision];
  const query = useQuery({
    queryKey: [...prefix, cursor],
    queryFn: () => readPage(subject, id, cursor),
    retry: false,
    staleTime: 0,
    refetchInterval: 60_000,
  });
  const title = settings[subject].title;
  return (
    <section
      className="finance-section"
      aria-label={title}
      aria-busy={query.isFetching}
    >
      <h3>{title}</h3>
      <p>按发生时间倒序，每页 20 条；正文按审核范围显示。</p>
      {query.isFetching && <p role="status">正在读取历史记录…</p>}
      {query.isError && (
        <p role="alert">
          历史记录读取失败，请重试；若权限已变化，请重新登录核对。
        </p>
      )}
      <button
        className="secondary-button"
        disabled={query.isFetching}
        onClick={() => {
          void cache.invalidateQueries({
            queryKey: [...prefix, undefined],
            exact: true,
            refetchType: "none",
          });
          if (cursors.length === 1) void query.refetch();
          else setCursors([undefined]);
        }}
      >
        {query.isError ? "重试时间线" : "刷新时间线"}
      </button>
      {query.data && !query.isError && !query.isFetching && (
        <>
          {query.data.items.length === 0 && <p>暂无活动记录。</p>}
          <ol className="finance-timeline">
            {query.data.items.map((activity) => (
              <li key={activity.id} data-activity-id={activity.id}>
                <time>
                  {new Date(activity.occurred_at).toLocaleString("zh-CN")}
                </time>
                <p>{activity.summary ?? "正文待审核，仅授权审核人可查看。"}</p>
                <small>{activity.activity_type}</small>
                {activity.content_visible &&
                  Object.keys(activity.details).length > 0 && (
                    <details>
                      <summary>活动补充信息</summary>
                      <pre className="work-content-preview">
                        {JSON.stringify(activity.details, null, 2)}
                      </pre>
                    </details>
                  )}
                {subject === "sales_order" ? (
                  <WorkTextReview
                    orderId={id}
                    kind="activity"
                    recordId={activity.id}
                    onChanged={() => query.refetch()}
                  />
                ) : (
                  <WorkTextReview
                    subjectType={subject}
                    subjectId={id}
                    recordId={activity.id}
                    onChanged={() => query.refetch()}
                  />
                )}
              </li>
            ))}
          </ol>
        </>
      )}
      <nav className="queue-pagination" aria-label={`${title}分页`}>
        <button
          className="secondary-button"
          disabled={cursors.length === 1 || query.isFetching}
          onClick={() => setCursors((values) => values.slice(0, -1))}
        >
          上一页历史
        </button>
        <span>第 {cursors.length} 页</span>
        <button
          className="secondary-button"
          disabled={query.isFetching || query.isError || !query.data?.has_more}
          onClick={() => {
            const next = query.data?.next_cursor;
            if (next) setCursors((values) => [...values, next]);
          }}
        >
          下一页历史
        </button>
      </nav>
    </section>
  );
}

export function CommercialTimeline(props: {
  subject: Subject;
  id: string;
  revision: string | number;
}) {
  const scope = useSessionScope();
  const member = useMemberContext(scope);
  if (!scope || member.isPending)
    return <p role="status">正在确认时间线权限…</p>;
  if (
    member.isError ||
    !member.data?.permissions.includes(settings[props.subject].permission)
  )
    return <p role="alert">当前无法查看此业务时间线。</p>;
  return (
    <TimelinePage
      key={`${scope}:${props.subject}:${props.id}:${props.revision}`}
      {...props}
      scope={scope}
    />
  );
}
