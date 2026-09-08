import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { components } from "@trade-workbench/api-client";
import { DocumentReview } from "./review";

const mocks = vi.hoisted(() => ({
  permissions: ["document.read", "profit.read"],
  scope: "organization:1",
  get: vi.fn(),
  post: vi.fn(),
}));
vi.mock("../overview/api", () => ({
  useMemberContext: () => ({ data: { permissions: mocks.permissions } }),
}));
vi.mock("../overview/session", () => ({
  useSessionScope: () => mocks.scope,
  sessionClient: () => ({ GET: mocks.get, POST: mocks.post }),
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  mocks.permissions = ["document.read", "profit.read"];
  mocks.scope = "organization:1";
});
const document = {
  id: "doc-1",
  title: "Evidence",
  versions: [{ id: "version-1", version_number: 1, released: false }],
} as components["schemas"]["DocumentResponse"];
const snapshot = {
  version_id: "version-1",
  version: 4,
  content_digest: "a".repeat(64),
  released: false,
};

function setup(evidence = document) {
  mocks.get.mockResolvedValue({ data: snapshot });
  const changed = vi.fn().mockResolvedValue(undefined);
  const view = render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <DocumentReview document={evidence} onChanged={changed} />
    </QueryClientProvider>,
  );
  return { ...view, changed };
}

it("does not fetch review facts or expose approval controls without cost authority", () => {
  mocks.permissions = ["document.read"];
  setup();
  expect(screen.queryByText("审核文件开放范围")).toBeNull();
  expect(mocks.get).not.toHaveBeenCalled();
  expect(screen.getByText(/未经审核的附件/)).toBeInTheDocument();
});

it.each([true, false])(
  "describes current version visibility %s without granting review access",
  (visible) => {
    mocks.permissions = ["document.read"];
    setup({
      ...document,
      latest_version_number: 2,
      versions: [
        {
          ...document.versions![0]!,
          version_number: 1,
          content_visible: !visible,
          released: !visible,
        },
        {
          ...document.versions![0]!,
          id: "version-2",
          version_number: 2,
          content_visible: visible,
          released: visible,
        },
      ],
    });
    expect(Boolean(screen.queryByText(/当前版本已按审核范围开放/))).toBe(
      visible,
    );
    expect(Boolean(screen.queryByText(/未经审核的附件/))).toBe(!visible);
    expect(screen.queryByText("审核文件开放范围")).toBeNull();
    expect(mocks.get).not.toHaveBeenCalled();
    expect(mocks.post).not.toHaveBeenCalled();
  },
);

it("requires an explicit decision and preserves the exact request key after a failed submission", async () => {
  const { changed } = setup();
  fireEvent.click(screen.getByText("审核文件开放范围"));
  fireEvent.click(screen.getByRole("button", { name: "审核第 1 版 · 保密" }));
  fireEvent.click(await screen.findByRole("button", { name: "确认审核决定" }));
  await screen.findByText("请选择开放或保密。");
  expect(mocks.post).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("审核决定"), {
    target: { value: "release" },
  });
  fireEvent.change(screen.getByLabelText("审核说明"), {
    target: { value: "已核对文件不含内部成本" },
  });
  fireEvent.click(screen.getByRole("checkbox"));
  mocks.post
    .mockRejectedValueOnce(new Error("lost response"))
    .mockResolvedValueOnce({ data: { ...snapshot, released: true } });
  fireEvent.click(screen.getByRole("button", { name: "确认审核决定" }));
  await screen.findByText(/审核未确认完成/);
  fireEvent.click(screen.getByRole("button", { name: "确认审核决定" }));
  await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
  expect(mocks.post).toHaveBeenCalledTimes(2);
  expect(mocks.post.mock.calls[0]).toEqual(mocks.post.mock.calls[1]);
  expect(mocks.post.mock.calls[0][1].body).toMatchObject({
    expected_version: 4,
    content_digest: snapshot.content_digest,
    release: true,
    confirmed: true,
  });
});

it("disables decision controls while a review is being recorded", async () => {
  setup();
  fireEvent.click(screen.getByText("审核文件开放范围"));
  fireEvent.click(screen.getByRole("button", { name: "审核第 1 版 · 保密" }));
  await screen.findByRole("button", { name: "确认审核决定" });
  fireEvent.change(screen.getByLabelText("审核决定"), {
    target: { value: "restrict" },
  });
  fireEvent.change(screen.getByLabelText("审核说明"), {
    target: { value: "需要保留内部资料" },
  });
  fireEvent.click(screen.getByRole("checkbox"));
  let finish!: () => void;
  mocks.post.mockReturnValue(
    new Promise((resolve) => {
      finish = () => resolve({ data: snapshot });
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "确认审核决定" }));
  await waitFor(() => expect(screen.getByLabelText("审核决定")).toBeDisabled());
  expect(screen.getByLabelText("审核说明")).toBeDisabled();
  finish();
  await waitFor(() => expect(screen.getByLabelText("审核决定")).toBeEnabled());
});
