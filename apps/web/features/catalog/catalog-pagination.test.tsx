import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CatalogWorkspace } from "./catalog-workspace";

const mocks = vi.hoisted(() => ({
  products: vi.fn(),
  fetching: false,
  error: false,
}));
vi.mock("../overview/session", () => ({ useSessionScope: () => "fixture" }));
vi.mock("../overview/api", () => ({
  useMemberContext: () => ({
    data: {
      permissions: ["product.read", "product_supplier.read", "profit.read"],
    },
  }),
}));
vi.mock("./api", () => ({ useProducts: mocks.products }));
afterEach(() => {
  cleanup();
  mocks.products.mockReset();
  mocks.fetching = false;
  mocks.error = false;
});

function setup() {
  mocks.products.mockImplementation((_scope, _query, cursor) => ({
    data: {
      items: [
        {
          id: cursor || "first",
          name: cursor ? "Older product" : "First product",
          sku: "SKU",
          unit: "set",
        },
      ],
      has_more: !cursor,
      next_cursor: cursor ? null : "older",
    },
    isFetching: mocks.fetching,
    isError: mocks.error,
    error: new Error("Unavailable"),
    refetch: vi.fn(),
  }));
  return render(<CatalogWorkspace />);
}
it("navigates product cursors and restarts at page one after a submitted search", async () => {
  setup();
  expect(screen.getByRole("button", { name: "上一页产品" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "下一页产品" }));
  expect(screen.getByText("第 2 页")).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: /Older product/ }),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "下一页产品" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "上一页产品" }));
  expect(screen.getByText("第 1 页")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "下一页产品" }));
  fireEvent.change(screen.getByLabelText("产品名称或 SKU"), {
    target: { value: "pump" },
  });
  fireEvent.click(screen.getByRole("button", { name: "检索产品" }));
  await waitFor(() =>
    expect(mocks.products).toHaveBeenLastCalledWith(
      "fixture",
      "pump",
      undefined,
    ),
  );
  expect(screen.getByText("第 1 页")).toBeInTheDocument();
});
it("blocks forward navigation while fetching or after an error", () => {
  mocks.fetching = true;
  const view = setup();
  expect(screen.getByRole("button", { name: "下一页产品" })).toBeDisabled();
  mocks.fetching = false;
  mocks.error = true;
  view.rerender(<CatalogWorkspace />);
  expect(screen.getByRole("button", { name: "下一页产品" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
});
