import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ContractForm } from "./forms";
import type { Contract } from "./api";

const contract = {
  id: "00000000-0000-4000-8000-000000000701",
  version: 7,
  external_reference: "OLD",
  notes: "Existing note",
} as Contract;
function panel(mode: "create" | "update" | "sign" | "void") {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { mutations: { retry: false } } })
      }
    >
      <ContractForm
        scope="test"
        orderId="00000000-0000-4000-8000-000000000702"
        mode={mode}
        contract={contract}
        documents={[]}
        onDone={vi.fn()}
        onCancel={vi.fn()}
      />
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  localStorage.setItem(
    "trade-workbench.organization-id",
    "00000000-0000-4000-8000-000000000001",
  );
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

it("requires reviewed evidence, date and explicit confirmation before signing", async () => {
  const fetch = vi.spyOn(globalThis, "fetch");
  panel("sign");
  fireEvent.click(screen.getByRole("button", { name: "确认登记已签署" }));
  expect(await screen.findByText("请选择已发生的签署日期")).toBeInTheDocument();
  expect(screen.getByText("请选择已验收的合同文件版本")).toBeInTheDocument();
  expect(screen.getByText("请确认操作含义")).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

it("preserves the opening version and retry key but gives changed requests a new key", async () => {
  const posts: Request[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    posts.push((input as Request).clone());
    return new Response(
      JSON.stringify({
        type: "about:blank",
        title: "Unavailable",
        status: 503,
        code: "TEMPORARY",
        detail: "请重试合同操作",
        request_id: "test",
        errors: [],
      }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
  });
  panel("update");
  expect(screen.getByLabelText("合同备注")).toBeDisabled();
  fireEvent.change(screen.getByLabelText("合同操作原因"), {
    target: { value: "Correct external reference" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存合同备注" }));
  await screen.findByText("请重试合同操作");
  fireEvent.click(screen.getByRole("button", { name: "保存合同备注" }));
  await waitFor(() => expect(posts).toHaveLength(2));
  expect(posts[0]!.headers.get("Idempotency-Key")).toBe(
    posts[1]!.headers.get("Idempotency-Key"),
  );
  const payload = await posts[0]!.json();
  expect(payload.expected_version).toBe(7);
  expect(payload).not.toHaveProperty("notes");
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "保存合同备注" })).toBeEnabled(),
  );
  fireEvent.change(screen.getByLabelText("外部合同编号"), {
    target: { value: "CHANGED" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存合同备注" }));
  await waitFor(() => expect(posts).toHaveLength(3));
  expect(posts[2]!.headers.get("Idempotency-Key")).not.toBe(
    posts[1]!.headers.get("Idempotency-Key"),
  );
});

it("requires a reason and confirmation before voiding a draft", async () => {
  const fetch = vi.spyOn(globalThis, "fetch");
  panel("void");
  fireEvent.click(screen.getByRole("button", { name: "确认作废草稿" }));
  expect(
    await screen.findByText("请填写至少三个字符的原因"),
  ).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});
