import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RouteMap } from "./route-map";

describe("RouteMap", () => {
  it("renders the complete first-order route in sequence", () => {
    render(<RouteMap />);

    expect(screen.getAllByRole("listitem")).toHaveLength(5);
    for (const label of ["线索", "报价", "订单", "出货", "回款"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });
});
