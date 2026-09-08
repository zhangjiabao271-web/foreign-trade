import { createRef } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Button } from "@trade-workbench/ui";
import { CursorPageControls } from "./cursor-page-controls";

afterEach(cleanup);

it("preserves native props, ref, classes and explicit submit semantics", () => {
  const ref = createRef<HTMLButtonElement>();
  const click = vi.fn();
  const ui = render(
    <Button ref={ref} variant="quiet" className="extra" onClick={click}>
      刷新
    </Button>,
  );
  const button = screen.getByRole("button", { name: "刷新" });
  expect(ref.current).toBe(button);
  expect(button).toHaveAttribute("type", "button");
  expect(button).toHaveAttribute("data-slot", "button");
  expect(button).toHaveClass("quiet-button", "extra");
  fireEvent.click(button);
  expect(click).toHaveBeenCalledTimes(1);
  ui.rerender(
    <Button type="submit" disabled onClick={click}>
      保存
    </Button>,
  );
  const submit = screen.getByRole("button", { name: "保存" });
  expect(submit).toHaveAttribute("type", "submit");
  expect(submit).toHaveClass("primary-button");
  fireEvent.click(submit);
  expect(click).toHaveBeenCalledTimes(1);
});

it("retains pagination, retry and loading behavior", () => {
  const query = {
    hasNextPage: true,
    isError: false,
    isFetching: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn().mockResolvedValue(undefined),
    restart: vi.fn().mockResolvedValue(undefined),
  };
  const ui = render(<CursorPageControls query={query} label="客户" />);
  const more = screen.getByRole("button", { name: "加载更多客户" });
  expect(more).toHaveClass("secondary-button");
  fireEvent.click(more);
  expect(query.fetchNextPage).toHaveBeenCalledTimes(1);
  ui.rerender(
    <CursorPageControls
      query={{ ...query, isFetching: true, isFetchingNextPage: true }}
      label="客户"
    />,
  );
  expect(screen.getByRole("button", { name: "正在加载客户…" })).toBeDisabled();
  ui.rerender(
    <CursorPageControls query={{ ...query, isError: true }} label="客户" />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("清单加载失败");
  fireEvent.click(screen.getByRole("button", { name: "重新加载客户清单" }));
  expect(query.restart).toHaveBeenCalledTimes(1);
  ui.rerender(
    <CursorPageControls
      query={{ ...query, hasNextPage: false }}
      label="客户"
    />,
  );
  expect(screen.queryByRole("button")).toBeNull();
});
