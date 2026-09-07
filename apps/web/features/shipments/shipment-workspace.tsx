"use client";
import { CursorPageControls } from "../../components/cursor-page-controls";

import { ApiClientError } from "@trade-workbench/api-client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  FormEvent,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMemberContext } from "../overview/api";
import { useSessionScope } from "../overview/session";
import {
  shipmentConnectionSchema,
  shipmentCreateSchema,
  shipmentUploadSchema,
} from "./form-schemas";

import { sessionKeys } from "../leads/api";
import { DocumentVersionHistory } from "../documents/version-history";
import { ResumeUpload } from "../documents/resume-upload";
import { DocumentReview } from "../documents/review";
import { useSalesOrders } from "../orders/api";
import { OrderPageControls } from "../orders/page-controls";

import {
  useCreateShipment,
  useRefreshShipment,
  useDownloadShipmentDocument,
  useShipment,
  useShipmentCommand,
  useShipmentDocuments,
  useShipmentSources,
  useShipments,
  useUploadShipmentDocument,
  type DocumentRecord,
  type Shipment,
  type ShipmentCreate,
} from "./api";

const sessionEvent = "trade-workbench-session-change";

const bookingSchema = z.object({
  bookingReference: z
    .string()
    .trim()
    .min(1, "请输入订舱参考号")
    .max(120, "订舱参考号最多 120 个字符"),
});

const shipmentStatusLabels: Record<Shipment["status"], string> = {
  PLANNING: "计划中",
  BOOKED: "已订舱",
  READY: "文件齐备",
  CUSTOMS: "报关中",
  DEPARTED: "已离港",
  IN_TRANSIT: "运输中",
  ARRIVED: "已到港",
  DELIVERED: "已交付",
};

const documentTypeLabels = {
  COMMERCIAL_INVOICE: "商业发票",
  SALES_CONTRACT: "销售合同",
  PACKING_LIST: "装箱单",
  BILL_OF_LADING: "提单",
  CERTIFICATE_OF_ORIGIN: "原产地证",
  BOOKING_CONFIRMATION: "订舱确认",
  OTHER: "其他文件",
} as const;

const documentStatusLabels = {
  PENDING_UPLOAD: "等待上传",
  UPLOADED: "等待扫描",
  SCANNING: "扫描中",
  AVAILABLE: "可用",
  REJECTED: "已拒绝",
} as const;

const milestones: Array<{ status: Shipment["status"]; label: string }> = [
  { status: "PLANNING", label: "计划" },
  { status: "BOOKED", label: "订舱" },
  { status: "READY", label: "齐套" },
  { status: "CUSTOMS", label: "报关" },
  { status: "DEPARTED", label: "离港" },
  { status: "IN_TRANSIT", label: "在途" },
  { status: "ARRIVED", label: "到港" },
  { status: "DELIVERED", label: "交付" },
];

function loadSessionSnapshot() {
  if (typeof window === "undefined") return "";
  const organizationId = window.localStorage.getItem(
    sessionKeys.organizationId,
  );
  const accessToken = window.localStorage.getItem(sessionKeys.accessToken);
  return organizationId &&
    (accessToken || window.localStorage.getItem(sessionKeys.marker))
    ? JSON.stringify({ organizationId, accessToken })
    : "";
}

function subscribeToSession(onStoreChange: () => void) {
  window.addEventListener("storage", onStoreChange);
  window.addEventListener(sessionEvent, onStoreChange);
  return () => {
    window.removeEventListener("storage", onStoreChange);
    window.removeEventListener(sessionEvent, onStoreChange);
  };
}

function describeError(error: unknown) {
  if (error instanceof ApiClientError) {
    if (error.problem.status === 403) return "当前成员没有执行此命令的权限。";
    if (error.problem.status === 401)
      return "访问凭证已失效，请重新连接业务空间。";
    if (error.problem.code === "SHIPMENT_DOCUMENTS_INCOMPLETE")
      return "商业发票与装箱单必须完成上传和扫描后，才能推进出运。";
    return `${error.problem.detail}（${error.problem.code}）`;
  }
  return "服务暂时不可用，请检查连接后重试。";
}

function CompassMark() {
  return (
    <svg viewBox="0 0 40 40" aria-hidden="true">
      <path d="M7 29 20 7l13 22-13 5Z" />
      <circle cx="20" cy="22" r="3" />
    </svg>
  );
}

function formatDate(value: string | null) {
  if (!value) return "待记录";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}

function ConnectionPanel() {
  const form = useForm<z.infer<typeof shipmentConnectionSchema>>({
    resolver: zodResolver(shipmentConnectionSchema),
    defaultValues: { organizationId: "", accessToken: "" },
  });
  const connect = form.handleSubmit((data) => {
    window.localStorage.setItem(
      sessionKeys.organizationId,
      data.organizationId,
    );
    window.localStorage.setItem(sessionKeys.accessToken, data.accessToken);
    window.dispatchEvent(new Event(sessionEvent));
  });
  return (
    <main id="main-content" className="connection-shell">
      <section
        className="connection-panel"
        aria-labelledby="shipment-connect-title"
      >
        <p className="section-kicker">受控访问</p>
        <h1 id="shipment-connect-title">连接你的业务空间</h1>
        <p>出运计划、货运节点与文件只在当前组织范围内读取。</p>
        <form onSubmit={connect} noValidate>
          <label htmlFor="shipment-organization-id">组织 ID</label>
          <input
            id="shipment-organization-id"
            {...form.register("organizationId")}
            aria-invalid={Boolean(form.formState.errors.organizationId)}
            aria-describedby="shipment-connection-organization-error"
          />
          {form.formState.errors.organizationId && (
            <p id="shipment-connection-organization-error" role="alert">
              {form.formState.errors.organizationId.message}
            </p>
          )}
          <label htmlFor="shipment-access-token">访问令牌</label>
          <textarea
            id="shipment-access-token"
            {...form.register("accessToken")}
            aria-invalid={Boolean(form.formState.errors.accessToken)}
            aria-describedby="shipment-connection-token-error"
            rows={4}
            required
          />
          {form.formState.errors.accessToken && (
            <p id="shipment-connection-token-error" role="alert">
              {form.formState.errors.accessToken.message}
            </p>
          )}
          <button className="primary-button" type="submit">
            连接业务空间
          </button>
        </form>
      </section>
    </main>
  );
}

function CreateShipmentPanel({
  connected,
  onClose,
  onCreated,
}: {
  connected: boolean;
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const orders = useSalesOrders(connected);
  const mutation = useCreateShipment();
  const submission = useRef<{ payload: string; key: string } | null>(null);
  const form = useForm<z.infer<typeof shipmentCreateSchema>>({
    resolver: zodResolver(shipmentCreateSchema),
    defaultValues: {
      forwarderCompanyId: "",
      plannedDepartureDate: "",
      plannedArrivalDate: "",
      lines: {},
    },
  });
  const lines = useWatch({ control: form.control, name: "lines" });
  const eligibleOrders =
    orders.data?.items.filter((order) =>
      ["EXECUTING", "READY_TO_SHIP"].includes(order.status),
    ) ?? [];

  const submit = (event: FormEvent<HTMLFormElement>) => {
    void form.handleSubmit(async (data) => {
      if (mutation.isPending) return;
      const items = eligibleOrders.flatMap((order) =>
        (order.items ?? [])
          .filter((item) => data.lines[item.id]?.selected)
          .map((item) => ({
            sales_order_item_id: item.id,
            quantity: data.lines[item.id].quantity,
          })),
      );
      if (!items.length) {
        form.setError("lines", { message: "可出运行已更新，请重新选择" });
        return;
      }
      const body: ShipmentCreate = {
        forwarder_company_id: data.forwarderCompanyId || null,
        planned_departure_date: data.plannedDepartureDate || null,
        planned_arrival_date: data.plannedArrivalDate || null,
        items,
      };
      const payload = JSON.stringify(body);
      if (submission.current?.payload !== payload) {
        submission.current = { payload, key: crypto.randomUUID() };
      }
      try {
        const shipment = await mutation.mutateAsync({
          body,
          key: submission.current.key,
        });
        onCreated(shipment.id);
      } catch {
        // Keep the original payload and key available after a lost response.
      }
    })(event);
  };

  return (
    <section
      className="shipment-form-panel"
      aria-labelledby="create-shipment-title"
    >
      <div className="panel-heading">
        <div>
          <p className="section-kicker">订单行 → 出运计划</p>
          <h2 id="create-shipment-title">编排本次装运</h2>
        </div>
        <button
          className="quiet-button"
          type="button"
          onClick={onClose}
          disabled={mutation.isPending}
        >
          取消
        </button>
      </div>
      <form onSubmit={submit} noValidate aria-busy={mutation.isPending}>
        <label>
          货代公司 ID
          <input
            {...form.register("forwarderCompanyId")}
            disabled={mutation.isPending}
            aria-invalid={Boolean(form.formState.errors.forwarderCompanyId)}
            aria-describedby="shipment-forwarder-error"
          />
          {form.formState.errors.forwarderCompanyId && (
            <span
              id="shipment-forwarder-error"
              className="form-error"
              role="alert"
            >
              {form.formState.errors.forwarderCompanyId?.message}
            </span>
          )}
        </label>
        <label>
          计划离港日
          <input
            {...form.register("plannedDepartureDate")}
            type="date"
            disabled={mutation.isPending}
            aria-invalid={Boolean(form.formState.errors.plannedDepartureDate)}
            aria-describedby="shipment-departure-error"
          />
          {form.formState.errors.plannedDepartureDate && (
            <span
              id="shipment-departure-error"
              className="form-error"
              role="alert"
            >
              {form.formState.errors.plannedDepartureDate?.message}
            </span>
          )}
        </label>
        <label>
          计划到港日
          <input
            {...form.register("plannedArrivalDate")}
            type="date"
            disabled={mutation.isPending}
            aria-invalid={Boolean(form.formState.errors.plannedArrivalDate)}
            aria-describedby="shipment-arrival-error"
          />
          {form.formState.errors.plannedArrivalDate && (
            <span
              id="shipment-arrival-error"
              className="form-error"
              role="alert"
            >
              {form.formState.errors.plannedArrivalDate?.message}
            </span>
          )}
        </label>
        <fieldset
          className="shipment-lines field-span-full"
          disabled={mutation.isPending}
        >
          <legend>选择可出运行</legend>
          {typeof form.formState.errors.lines?.message === "string" && (
            <p className="form-error" role="alert">
              {form.formState.errors.lines.message}
            </p>
          )}
          {orders.isLoading && <p aria-live="polite">正在读取执行中订单…</p>}
          {orders.isError && (
            <p className="form-error" role="alert">
              {describeError(orders.error)}
            </p>
          )}
          {eligibleOrders.map((order) => (
            <section className="shipment-order-group" key={order.id}>
              <header>
                <strong>{order.order_number}</strong>
                <span>
                  {order.status === "EXECUTING" ? "执行中" : "待出货"}
                </span>
              </header>
              {(order.items ?? []).map((item) => {
                const current = lines[item.id];
                return (
                  <div className="shipment-line" key={item.id}>
                    <label className="shipment-line-select">
                      <input
                        type="checkbox"
                        {...form.register(`lines.${item.id}.selected`)}
                      />
                      <span>
                        <strong>{item.sku_snapshot}</strong>
                        <small>{item.description_snapshot}</small>
                      </span>
                    </label>
                    <label>
                      本次数量（订单 {item.quantity} {item.unit_snapshot}）
                      <input
                        aria-label={`${item.sku_snapshot} 本次出运数量`}
                        inputMode="decimal"
                        {...form.register(`lines.${item.id}.quantity`)}
                        defaultValue={item.quantity}
                        disabled={!current?.selected}
                        aria-invalid={Boolean(
                          form.formState.errors.lines?.[item.id]?.quantity,
                        )}
                        aria-describedby={`shipment-quantity-${item.id}-error`}
                      />
                      {form.formState.errors.lines?.[item.id]?.quantity && (
                        <span
                          id={`shipment-quantity-${item.id}-error`}
                          className="form-error"
                          role="alert"
                        >
                          {
                            form.formState.errors.lines[item.id]?.quantity
                              ?.message
                          }
                        </span>
                      )}
                    </label>
                  </div>
                );
              })}
            </section>
          ))}
          {!orders.isLoading && eligibleOrders.length === 0 && (
            <p className="empty-copy">
              已加载记录中没有可出运订单。可继续加载较早订单；订单须进入执行中或待出货。
            </p>
          )}
        </fieldset>
        <OrderPageControls query={orders} disabled={mutation.isPending} />
        {mutation.isError && (
          <p className="form-error field-span-full" role="alert">
            {describeError(mutation.error)}
          </p>
        )}
        <button
          className="primary-button"
          disabled={
            mutation.isPending ||
            !Object.values(lines).some((line) => line.selected)
          }
        >
          {mutation.isPending ? "正在建立装运…" : "创建出运计划"}
        </button>
        <p className="field-span-full">
          连接中断时可保留原表单重试；修改内容或关闭表单前，请先核对出运清单。
        </p>
      </form>
    </section>
  );
}

function ShipmentRoute({ shipment }: { shipment: Shipment }) {
  const currentIndex = milestones.findIndex(
    (milestone) => milestone.status === shipment.status,
  );
  return (
    <ol className="shipment-route" aria-label="出运进度">
      {milestones.map((milestone, index) => (
        <li
          key={milestone.status}
          data-state={
            index < currentIndex
              ? "complete"
              : index === currentIndex
                ? "current"
                : "upcoming"
          }
          aria-current={index === currentIndex ? "step" : undefined}
        >
          <span>{String(index + 1).padStart(2, "0")}</span>
          <strong>{milestone.label}</strong>
        </li>
      ))}
    </ol>
  );
}

function ShipmentCommands({
  shipment,
  finalized,
}: {
  shipment: Shipment;
  finalized: boolean;
}) {
  const mutation = useShipmentCommand(shipment.id);
  const member = useMemberContext(useSessionScope());
  const [bookingVersion, setBookingVersion] = useState(shipment.version);
  const form = useForm<z.infer<typeof bookingSchema>>({
    resolver: zodResolver(bookingSchema),
    defaultValues: { bookingReference: "" },
  });
  const nextCommands: Partial<
    Record<
      Shipment["status"],
      {
        command: Exclude<
          Parameters<typeof mutation.mutate>[0]["command"],
          "book"
        >;
        label: string;
      }
    >
  > = {
    BOOKED: { command: "ready", label: "确认文件齐备" },
    READY: { command: "enter-customs", label: "进入报关" },
    CUSTOMS: { command: "depart", label: "确认离港" },
    DEPARTED: { command: "start-transit", label: "开始在途运输" },
    IN_TRANSIT: { command: "arrive", label: "确认到港" },
    ARRIVED: { command: "deliver", label: "确认完成交付" },
  };
  const next = nextCommands[shipment.status];

  if (!member.data?.permissions.includes("shipment.transition")) {
    return (
      <p className="empty-copy">当前为只读视图，出运节点由有权限的成员推进。</p>
    );
  }

  const recovery = mutation.isError && (
    <div>
      <p className="form-error" role="alert">
        {describeError(mutation.error)}
      </p>
      <p>连接中断时可原样重试；修改内容或离开页面前，请先核对当前出运记录。</p>
      {mutation.variables && (
        <button
          type="button"
          className="secondary-button"
          disabled={mutation.isPending}
          onClick={() =>
            mutation.variables && mutation.mutate(mutation.variables)
          }
        >
          原样重试出运操作
        </button>
      )}
      {shipment.status === "PLANNING" &&
        !finalized &&
        bookingVersion !== shipment.version && (
          <button
            type="button"
            className="quiet-button"
            disabled={mutation.isPending}
            onClick={() => {
              setBookingVersion(shipment.version);
              form.reset();
              mutation.reset();
            }}
          >
            按当前版本重新填写订舱
          </button>
        )}
    </div>
  );

  if (finalized)
    return (
      <div>
        <p>关联订单已终结，不能记录新的出运节点。</p>
        {recovery}
      </div>
    );

  if (shipment.status === "PLANNING") {
    return (
      <form
        className="booking-form"
        noValidate
        aria-busy={mutation.isPending}
        onSubmit={form.handleSubmit(({ bookingReference }) => {
          if (!mutation.isPending)
            mutation.mutate({
              command: "book",
              body: {
                expected_version: bookingVersion,
                booking_reference: bookingReference,
              },
            });
        })}
      >
        <label>
          订舱参考号 *
          <input
            {...form.register("bookingReference")}
            disabled={mutation.isPending}
            aria-invalid={Boolean(form.formState.errors.bookingReference)}
            aria-describedby={
              form.formState.errors.bookingReference
                ? "booking-reference-error"
                : undefined
            }
          />
          {form.formState.errors.bookingReference && (
            <span
              id="booking-reference-error"
              className="form-error"
              role="alert"
            >
              {form.formState.errors.bookingReference.message}
            </span>
          )}
        </label>
        <button className="primary-button" disabled={mutation.isPending}>
          {mutation.isPending ? "正在记录…" : "记录已订舱"}
        </button>
        {recovery}
      </form>
    );
  }

  return (
    <div className="shipment-command-bar">
      {next ? (
        <button
          className="primary-button"
          disabled={mutation.isPending}
          onClick={() =>
            mutation.mutate({
              command: next.command,
              body: { expected_version: shipment.version },
            })
          }
        >
          {mutation.isPending ? "正在推进…" : next.label}
        </button>
      ) : (
        <span>本次出运已经交付，节点记录保持只读。</span>
      )}
      {recovery}
    </div>
  );
}

function DocumentCard({
  document,
  onReplace,
  onRecovered,
  onReviewChanged,
}: {
  document: DocumentRecord;
  onReviewChanged: () => Promise<unknown>;
  onReplace?: () => void;
  onRecovered?: () => Promise<unknown>;
}) {
  const download = useDownloadShipmentDocument();
  const latest = document.versions?.find(
    (version) => version.version_number === document.latest_version_number,
  );
  const downloadFile = (versionId?: string) => {
    download.mutate(
      { documentId: document.id, versionId },
      {
        onSuccess: (session) => window.location.assign(session.download_url),
      },
    );
  };
  return (
    <article className="document-card">
      <div>
        <p>{documentTypeLabels[document.document_type]}</p>
        <strong>{document.title ?? "待审核附件"}</strong>
        <small>{latest?.file_name ?? "文件名保密"}</small>
      </div>
      <div>
        <span className="status-chip" data-status={latest?.status}>
          {latest ? documentStatusLabels[latest.status] : "无版本"}
        </span>
        <small>第 {document.latest_version_number} 版</small>
        {onReplace && (
          <button className="quiet-button" type="button" onClick={onReplace}>
            替换文件
          </button>
        )}
        {latest?.status === "AVAILABLE" && latest.content_visible && (
          <button
            className="quiet-button"
            type="button"
            disabled={download.isPending}
            onClick={() => downloadFile()}
          >
            {download.isPending ? "正在授权…" : "下载"}
          </button>
        )}
      </div>
      <DocumentVersionHistory
        document={document}
        pending={download.isPending}
        onDownload={downloadFile}
      />
      <DocumentReview document={document} onChanged={onReviewChanged} />
      {onRecovered && (
        <ResumeUpload document={document} onRecovered={onRecovered} />
      )}
      {download.isError && (
        <p className="form-error" role="alert">
          {describeError(download.error)}
        </p>
      )}
    </article>
  );
}

function ShipmentDocuments({
  shipment,
  connected,
}: {
  shipment: Shipment;
  connected: boolean;
}) {
  const documents = useShipmentDocuments(shipment.id, connected);
  const upload = useUploadShipmentDocument(shipment.id);
  const refresh = useRefreshShipment(shipment.id);
  const member = useMemberContext(useSessionScope());
  const canUpload =
    shipment.status !== "DELIVERED" &&
    member.data?.permissions.includes("document.write");
  const form = useForm<z.infer<typeof shipmentUploadSchema>>({
    resolver: zodResolver(shipmentUploadSchema),
    defaultValues: { documentType: "COMMERCIAL_INVOICE" },
  });
  const [replacement, setReplacement] = useState<DocumentRecord>();
  const uploadDocument = form.handleSubmit(async (data, event) => {
    if (!canUpload || upload.isPending) return;
    const element = event?.target as HTMLFormElement | undefined;
    try {
      await upload.mutateAsync({
        file: data.files[0],
        documentType: replacement?.document_type ?? data.documentType,
        replacement: replacement
          ? { documentId: replacement.id, expectedVersion: replacement.version }
          : undefined,
      });
      element?.reset();
      form.reset();
      setReplacement(undefined);
    } catch {
      // Keep the selected file and show the mutation error for retry.
    }
  });
  const missing = shipment.missing_required_documents ?? [];

  return (
    <section
      className="document-ledger"
      aria-labelledby="document-ledger-title"
    >
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Clearance papers</p>
          <h2 id="document-ledger-title">出运文件</h2>
        </div>
        <span>{documents.data?.count ?? 0} 份</span>
      </div>
      <div className="document-clearance" data-ready={missing.length === 0}>
        <span aria-hidden="true" />
        <div>
          <strong>
            {missing.length === 0 ? "离港文件已齐套" : "离港文件仍有缺口"}
          </strong>
          <p>
            {missing.length === 0
              ? "商业发票与装箱单均已通过扫描。"
              : `缺少：${missing.map((type) => documentTypeLabels[type as keyof typeof documentTypeLabels] ?? type).join("、")}`}
          </p>
        </div>
      </div>
      {canUpload && (
        <form
          className="document-upload"
          onSubmit={uploadDocument}
          noValidate
          aria-busy={upload.isPending}
        >
          {replacement && (
            <p className="field-span-full">
              替换 {replacement.title}：将创建新版，旧版保留。
              <button
                type="button"
                className="quiet-button"
                disabled={upload.isPending}
                onClick={() => {
                  setReplacement(undefined);
                  form.setValue("documentType", "COMMERCIAL_INVOICE");
                }}
              >
                取消替换
              </button>
            </p>
          )}
          <label>
            文件类型
            <select
              key={replacement?.id ?? "new-document"}
              {...form.register("documentType")}
              disabled={Boolean(replacement) || upload.isPending}
            >
              {Object.entries(documentTypeLabels).map(([value, label]) => (
                <option value={value} key={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            选择文件（最大 25 MB）
            <input
              {...form.register("files")}
              type="file"
              aria-label="选择文件（最大 25 MB）"
              disabled={upload.isPending}
              aria-invalid={Boolean(form.formState.errors.files)}
              aria-describedby="shipment-upload-file-error"
              required
            />
            {form.formState.errors.files && (
              <span
                id="shipment-upload-file-error"
                className="form-error"
                role="alert"
              >
                {form.formState.errors.files.message}
              </span>
            )}
          </label>
          <button className="secondary-button" disabled={upload.isPending}>
            {upload.isPending ? "上传并校验中…" : "上传文件"}
          </button>
          {upload.isError && (
            <p className="form-error field-span-full" role="alert">
              {describeError(upload.error)}
            </p>
          )}
        </form>
      )}
      {documents.isLoading && <p aria-live="polite">正在读取文件清单…</p>}
      {documents.isError && (
        <p className="form-error" role="alert">
          {describeError(documents.error)}
        </p>
      )}
      <div className="document-grid">
        {documents.data?.items.map((document) => (
          <DocumentCard
            onReviewChanged={refresh}
            document={document}
            key={document.id}
            onRecovered={canUpload && !upload.isPending ? refresh : undefined}
            onReplace={
              canUpload && !upload.isPending
                ? () => {
                    setReplacement(document);
                    form.setValue("documentType", document.document_type);
                  }
                : undefined
            }
          />
        ))}
      </div>
      {documents.data?.count === 0 && (
        <p className="empty-copy">先上传商业发票和装箱单，再确认文件齐备。</p>
      )}
    </section>
  );
}

function ShipmentDetail({
  id,
  connected,
}: {
  id?: string;
  connected: boolean;
}) {
  const query = useShipment(id, connected);
  const sources = useShipmentSources(id, connected);
  const lineLookup = useMemo(() => {
    return new Map((sources.data?.items ?? []).map((item) => [item.id, item]));
  }, [sources.data]);

  if (!id)
    return (
      <section className="shipment-detail empty-detail">
        <p>选择一份装运，查看航程节点、订单行与通关文件。</p>
      </section>
    );
  if (query.isLoading)
    return (
      <section className="shipment-detail" aria-busy="true">
        <div className="detail-skeleton" />
        <div className="detail-skeleton short" />
      </section>
    );
  if (query.isError || !query.data)
    return (
      <section className="shipment-detail error-state" role="alert">
        <h2>无法读取出运计划</h2>
        <p>{describeError(query.error)}</p>
        <button className="secondary-button" onClick={() => query.refetch()}>
          重试
        </button>
      </section>
    );

  const shipment = query.data;
  return (
    <section
      className="shipment-detail"
      aria-labelledby="shipment-detail-title"
    >
      <div className="detail-heading">
        <div>
          <p className="manifest-code">SHIPMENT / CONTROLLED</p>
          <h2 id="shipment-detail-title">{shipment.shipment_number}</h2>
          <p>订舱参考号 · {shipment.booking_reference ?? "尚未记录"}</p>
        </div>
        <span className="status-chip large" data-status={shipment.status}>
          {shipmentStatusLabels[shipment.status]}
        </span>
      </div>
      <ShipmentRoute shipment={shipment} />
      <dl className="shipment-facts">
        <div>
          <dt>计划离港</dt>
          <dd>{formatDate(shipment.planned_departure_date)}</dd>
        </div>
        <div>
          <dt>计划到港</dt>
          <dd>{formatDate(shipment.planned_arrival_date)}</dd>
        </div>
        <div>
          <dt>货代</dt>
          <dd>{shipment.forwarder_company_id ?? "未指定"}</dd>
        </div>
      </dl>
      <ShipmentCommands
        key={shipment.id}
        shipment={shipment}
        finalized={(shipment.items ?? []).some((item) => {
          const status = lineLookup.get(item.sales_order_item_id)?.order_status;
          return status === "COMPLETED" || status === "CANCELLED";
        })}
      />
      <div className="shipment-cargo">
        <div className="panel-heading">
          <div>
            <p className="section-kicker">Cargo manifest</p>
            <h2>本次货物</h2>
          </div>
          <span>{shipment.items?.length ?? 0} 行</span>
        </div>
        {(shipment.items ?? []).map((shipmentItem) => {
          const source = lineLookup.get(shipmentItem.sales_order_item_id);
          let description = sources.isError
            ? "来源快照暂不可用"
            : "订单快照读取中";
          if (source)
            description = source.description_snapshot ?? "订单原文未获审核开放";
          return (
            <article key={shipmentItem.id}>
              <span>{source?.order_number ?? "订单行"}</span>
              <strong>
                {source?.sku_snapshot ?? shipmentItem.sales_order_item_id}
              </strong>
              <small>{description}</small>
              <b>
                {shipmentItem.quantity} {source?.unit_snapshot ?? ""}
              </b>
            </article>
          );
        })}
        {sources.isError && (
          <div className="list-message" role="alert">
            <p>来源订单读取失败：{describeError(sources.error)}</p>
            <button
              type="button"
              className="secondary-button"
              disabled={sources.isFetching}
              onClick={() => void sources.refetch()}
            >
              {sources.isFetching ? "正在重试来源快照…" : "重试来源快照"}
            </button>
          </div>
        )}
      </div>
      <ShipmentDocuments shipment={shipment} connected={connected} />
    </section>
  );
}

export function ShipmentWorkspace({
  initialShipmentId,
}: {
  initialShipmentId?: string;
}) {
  const router = useRouter();
  const scope = useSessionScope();
  const [creatingShipment, setCreatingShipment] = useState(false);
  const sessionSnapshot = useSyncExternalStore(
    subscribeToSession,
    loadSessionSnapshot,
    () => "",
  );
  const connected = Boolean(sessionSnapshot);
  const member = useMemberContext(useSessionScope());
  const canCreate = member.data?.permissions.includes("shipment.write");
  const shipments = useShipments(connected);
  const disconnect = () => {
    window.localStorage.removeItem(sessionKeys.organizationId);
    window.localStorage.removeItem(sessionKeys.accessToken);
    window.dispatchEvent(new Event(sessionEvent));
  };

  if (!connected) return <ConnectionPanel />;
  return (
    <main id="main-content" className="workspace-shell">
      <header className="workspace-topbar">
        <Link className="brand" href="/">
          <CompassMark />
          <span>
            外贸工作台<small>Trade workbench</small>
          </span>
        </Link>
        <nav aria-label="主导航">
          <Link href="/leads">线索</Link>
          <Link href="/quotations">报价</Link>
          <Link href="/orders">订单</Link>
          <Link className="active" href="/shipments">
            出运
          </Link>
        </nav>
        <button className="quiet-button" onClick={disconnect}>
          切换空间
        </button>
      </header>
      <section className="workspace-intro shipment-intro">
        <div>
          <p className="section-kicker">Phase 5 · Shipment & documents</p>
          <h1>出运航控台</h1>
          <p>把订单行、装运节点和文件齐套状态放在同一条航线上。</p>
        </div>
        {canCreate && (
          <button
            className="primary-button"
            onClick={() => setCreatingShipment(true)}
          >
            创建出运计划
          </button>
        )}
      </section>
      {creatingShipment && canCreate && (
        <CreateShipmentPanel
          connected={connected}
          onClose={() => setCreatingShipment(false)}
          onCreated={(id) => {
            setCreatingShipment(false);
            router.push(`/shipments/${id}`);
          }}
        />
      )}
      <div className="shipment-console">
        <section
          className="shipment-manifest"
          aria-labelledby="shipment-list-title"
        >
          <div className="list-heading">
            <div>
              <p className="section-kicker">航次清单</p>
              <h2 id="shipment-list-title">装运任务</h2>
            </div>
            <span>已加载 {shipments.data?.count ?? 0} 票</span>
          </div>
          {shipments.isLoading && (
            <div className="lead-list-skeleton" aria-label="正在加载出运计划">
              <span />
              <span />
              <span />
            </div>
          )}
          {shipments.isError && !shipments.data && (
            <div className="list-message error-state" role="alert">
              <strong>出运清单暂时不可用</strong>
              <p>{describeError(shipments.error)}</p>
            </div>
          )}
          {shipments.data?.items.map((shipment) => (
            <Link
              className="shipment-row"
              href={`/shipments/${shipment.id}`}
              data-selected={shipment.id === initialShipmentId}
              aria-current={
                shipment.id === initialShipmentId ? "page" : undefined
              }
              key={shipment.id}
            >
              <span>
                <small>ETD {shipment.planned_departure_date ?? "待定"}</small>
                <strong>{shipment.shipment_number}</strong>
                <time dateTime={shipment.planned_arrival_date ?? undefined}>
                  ETA {shipment.planned_arrival_date ?? "待定"}
                </time>
              </span>
              <span>
                <span className="status-chip" data-status={shipment.status}>
                  {shipmentStatusLabels[shipment.status]}
                </span>
                <b>{shipment.items?.length ?? 0} 行货物</b>
              </span>
            </Link>
          ))}
          <CursorPageControls query={shipments} label="出运单" />
          {shipments.data?.count === 0 && (
            <p className="list-message">
              订单进入执行中后，可从这里编排首票装运。
            </p>
          )}
        </section>
        <ShipmentDetail
          key={`${scope}:${initialShipmentId}`}
          id={initialShipmentId}
          connected={connected}
        />
      </div>
    </main>
  );
}
