import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { components } from "@trade-workbench/api-client";
import { DocumentVersionHistory } from "./version-history";

afterEach(cleanup);

const document = {
  title: "商业发票",
  latest_version_number: 3,
  versions: [
    {
      id: "old",
      version_number: 1,
      file_name: "old.txt",
      status: "AVAILABLE",
      content_visible: true,
    },
    {
      id: "pending",
      version_number: 2,
      file_name: "pending.txt",
      status: "PENDING_UPLOAD",
    },
    {
      id: "latest",
      version_number: 3,
      file_name: "latest.txt",
      status: "AVAILABLE",
    },
  ],
} as components["schemas"]["DocumentResponse"];

describe("document version history", () => {
  it("exposes only historical versions and downloads the exact selected version", () => {
    const download = vi.fn();
    render(
      <DocumentVersionHistory
        document={document}
        pending={false}
        onDownload={download}
      />,
    );
    fireEvent.click(screen.getByText("历史版本 · 商业发票（2）"));
    expect(screen.queryByText(/latest.txt/)).not.toBeInTheDocument();
    expect(
      screen.getByText("尚未通过校验或开放审核，不可下载"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "下载第 1 版" }));
    expect(download).toHaveBeenCalledWith("old");
  });

  it("disables downloads while authorization is pending", () => {
    render(
      <DocumentVersionHistory
        document={document}
        pending
        onDownload={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("历史版本 · 商业发票（2）"));
    expect(screen.getByRole("button", { name: "正在授权…" })).toBeDisabled();
  });
});
