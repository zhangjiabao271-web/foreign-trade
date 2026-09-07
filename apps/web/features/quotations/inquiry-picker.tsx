"use client";

import { useState } from "react";
import { CursorPageControls } from "../../components/cursor-page-controls";
import { useMemberContext } from "../overview/api";
import { useSessionScope } from "../overview/session";
import { useInquiries } from "./api";

export function InquiryPicker({
  disabled,
  onSelect,
}: {
  disabled: boolean;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const member = useMemberContext(useSessionScope());
  const canRead = Boolean(member.data?.permissions.includes("inquiry.read"));
  const query = useInquiries(open && canRead);
  if (!canRead) return null;
  return (
    <section className="field-span-full" aria-label="选择已有询盘">
      <button
        type="button"
        className="secondary-button"
        disabled={disabled}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {open ? "收起询盘清单" : "从已有询盘选择"}
      </button>
      {open && (
        <>
          {query.isLoading && <p role="status">正在读取询盘…</p>}
          <p>
            已加载 {query.data?.count ?? 0}{" "}
            条未报价询盘。正文按独立审核规则保护。
          </p>
          <ul className="inquiry-picker-list">
            {query.data?.items.map((inquiry) => (
              <li key={inquiry.id}>
                <button
                  type="button"
                  className="quiet-button"
                  disabled={disabled}
                  onClick={() => {
                    onSelect(inquiry.id);
                    setOpen(false);
                  }}
                >
                  选择 {inquiry.customer_reference || inquiry.id}
                </button>
                <span>
                  {" "}
                  · {inquiry.received_at.slice(0, 10)} · {inquiry.id}
                </span>
              </li>
            ))}
          </ul>
          {query.data?.count === 0 && <p>暂无未报价询盘，可先登记询盘。</p>}
          <CursorPageControls query={query} label="询盘" disabled={disabled} />
        </>
      )}
    </section>
  );
}
