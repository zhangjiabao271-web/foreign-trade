import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CompanyForm, ContactForm } from "./forms";
import { CompanyWorkspace } from "./company-workspace";
import type { Company, Contact } from "./api";

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  pending: false,
  version: 2,
  permissions: ["company.read", "company.write"],
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("../overview/session", () => ({ useSessionScope: () => "fixture" }));
vi.mock("../overview/api", () => ({
  useMemberContext: () => ({ data: { permissions: mocks.permissions } }),
}));
vi.mock("./api", () => ({
  useArchiveCommand: () => ({ mutate: mocks.mutate, isPending: mocks.pending }),
  useCompany: () => ({
    data: {
      id: "company",
      name: "客商",
      version: mocks.version,
      roles: ["CUSTOMER"],
    },
  }),
  useCompanies: () => ({ data: { items: [], has_more: false } }),
  useContacts: () => ({ data: { items: [], has_more: false } }),
  useCompanyHistory: () => ({ data: { items: [], has_more: false } }),
}));
afterEach(() => {
  cleanup();
  mocks.mutate.mockReset();
  mocks.pending = false;
  mocks.version = 2;
  mocks.permissions = ["company.read", "company.write"];
});
const row = {
  id: "company",
  name: "客商",
  version: 2,
  roles: ["CUSTOMER"],
} as Company;
it("requires an initial role and sends a stable key for unchanged retry", async () => {
  render(<CompanyForm scope="fixture" onClose={vi.fn()} onSaved={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("公司名称"), {
    target: { value: " 新客商 " },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存档案" }));
  expect(await screen.findByText("至少选择一种业务角色")).toBeInTheDocument();
  expect(mocks.mutate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByLabelText("客户"));
  fireEvent.click(screen.getByLabelText("供应商"));
  fireEvent.click(screen.getByRole("button", { name: "保存档案" }));
  await vi.waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
  expect(mocks.mutate.mock.calls[0][0]).toMatchObject({
    kind: "create-company",
    body: {
      name: "新客商",
      country_code: null,
      website: null,
      roles: ["CUSTOMER", "SUPPLIER"],
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存档案" }));
  await vi.waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(2));
  expect(mocks.mutate.mock.calls[0][0].key).toBe(
    mocks.mutate.mock.calls[1][0].key,
  );
  fireEvent.change(screen.getByLabelText("公司名称"), {
    target: { value: "另一个名字" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存档案" }));
  await vi.waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(3));
  expect(mocks.mutate.mock.calls[2][0].key).not.toBe(
    mocks.mutate.mock.calls[0][0].key,
  );
});
it("requires update reason, preserves version, and excludes role mutation", async () => {
  render(
    <CompanyForm
      scope="fixture"
      row={row}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "保存档案" }));
  expect(await screen.findByText("请填写修改原因")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("修改原因"), {
    target: { value: "客户核对" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存档案" }));
  await vi.waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
  expect(mocks.mutate.mock.calls[0][0].body).toEqual({
    name: "客商",
    country_code: null,
    website: null,
    expected_version: 2,
    reason: "客户核对",
  });
});
it("keeps a contact under its parent and validates email", async () => {
  const contact = { id: "contact", full_name: "张女士", version: 4 } as Contact;
  render(
    <ContactForm
      scope="fixture"
      companyId="company"
      row={contact}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  fireEvent.change(screen.getByLabelText("邮箱（选填）"), {
    target: { value: "invalid" },
  });
  fireEvent.change(screen.getByLabelText("修改原因"), {
    target: { value: "更新联系方式" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存档案" }));
  expect(await screen.findByText("请填写有效邮箱")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("邮箱（选填）"), {
    target: { value: "sales@example.com" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存档案" }));
  await vi.waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
  expect(mocks.mutate.mock.calls[0][0]).toMatchObject({
    kind: "update-contact",
    id: "company",
    contactId: "contact",
    body: {
      full_name: "张女士",
      email: "sales@example.com",
      phone: null,
      job_title: null,
      expected_version: 4,
      reason: "更新联系方式",
    },
  });
});
it("disables inputs and cancellation while saving", () => {
  mocks.pending = true;
  render(
    <CompanyForm
      scope="fixture"
      row={row}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("公司名称")).toBeDisabled();
  expect(screen.getByRole("button", { name: "取消编辑" })).toBeDisabled();
});
it("keeps the opening version when a background refresh changes the company", async () => {
  const view = render(<CompanyWorkspace id="company" />);
  fireEvent.click(screen.getByRole("button", { name: "编辑公司资料" }));
  fireEvent.change(screen.getByLabelText("公司名称"), {
    target: { value: "待保存的修改" },
  });
  mocks.version = 3;
  view.rerender(<CompanyWorkspace id="company" />);
  expect(screen.getByLabelText("公司名称")).toHaveValue("待保存的修改");
  fireEvent.change(screen.getByLabelText("修改原因"), {
    target: { value: "核对" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存档案" }));
  await vi.waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
  expect(mocks.mutate.mock.calls[0][0].body.expected_version).toBe(2);
});
it("hides all write controls for readers and denies missing read permission", () => {
  mocks.permissions = ["company.read"];
  const view = render(<CompanyWorkspace id="company" />);
  expect(
    screen.queryByRole("button", { name: "编辑公司资料" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "新建联系人" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "确认增加角色" }),
  ).not.toBeInTheDocument();
  mocks.permissions = [];
  view.rerender(<CompanyWorkspace id="company" />);
  expect(screen.getByText("当前成员无档案查看权限。")).toBeInTheDocument();
});
