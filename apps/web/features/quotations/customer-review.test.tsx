import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CustomerReview } from "./customer-review";
const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  pending: false,
  permissions: ["quotation.send"],
}));
vi.mock("../overview/session", () => ({ useSessionScope: () => "fixture" }));
vi.mock("../overview/api", () => ({
  useMemberContext: () => ({ data: { permissions: mocks.permissions } }),
}));
vi.mock("./api", () => ({
  useCustomerReview: () => ({ mutate: mocks.mutate, isPending: mocks.pending }),
}));
afterEach(() => {
  cleanup();
  mocks.mutate.mockReset();
  mocks.pending = false;
  mocks.permissions = ["quotation.send"];
});
it("requires evidence, preserves version and reuses the unchanged retry key", async () => {
  render(<CustomerReview id="quote" versionId="version" />);
  fireEvent.click(screen.getByRole("button", { name: "记录客户审阅" }));
  expect(await screen.findByText("请填写客户审阅依据")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("客户审阅依据"), {
    target: { value: "Confirmed email" },
  });
  fireEvent.click(screen.getByRole("button", { name: "记录客户审阅" }));
  await waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
  expect(mocks.mutate.mock.calls[0][0].body).toEqual({
    expected_version_id: "version",
    reason: "Confirmed email",
  });
  fireEvent.click(screen.getByRole("button", { name: "记录客户审阅" }));
  await waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(2));
  expect(mocks.mutate.mock.calls[1][0].key).toBe(
    mocks.mutate.mock.calls[0][0].key,
  );
});
it("disables pending edits and hides the operation from unauthorized members", () => {
  mocks.pending = true;
  const view = render(<CustomerReview id="quote" versionId="version" />);
  expect(screen.getByLabelText("客户审阅依据")).toBeDisabled();
  expect(screen.getByRole("button", { name: "正在记录…" })).toBeDisabled();
  mocks.permissions = [];
  view.rerender(<CustomerReview id="quote" versionId="version" />);
  expect(screen.queryByLabelText("客户审阅依据")).not.toBeInTheDocument();
});
