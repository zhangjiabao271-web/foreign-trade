"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { parseApiError, type components } from "@trade-workbench/api-client";
import { sessionClient } from "../overview/session";

export type Company = components["schemas"]["CompanyResponse"];
export type Contact = components["schemas"]["ContactResponse"];
export type CompanyRole = components["schemas"]["CompanyRoleType"];
export type CompanyCreate = components["schemas"]["CompanyCreate"];
export type CompanyUpdate = components["schemas"]["CompanyUpdate"];
export type ContactFields = components["schemas"]["ContactFields"];
export type ContactUpdate = components["schemas"]["ContactUpdate"];
export type ArchiveCommand =
  | { kind: "create-company"; body: CompanyCreate; key: string }
  | { kind: "update-company"; id: string; body: CompanyUpdate; key: string }
  | { kind: "create-contact"; id: string; body: ContactFields; key: string }
  | {
      kind: "update-contact";
      id: string;
      contactId: string;
      body: ContactUpdate;
      key: string;
    }
  | { kind: "add-role"; id: string; body: { role: CompanyRole } };

export function useCompanies(
  scope: string,
  query: string,
  role?: CompanyRole,
  cursor?: string,
) {
  return useQuery({
    queryKey: ["companies", scope, query, role, cursor],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/companies", {
        params: { query: { query, role, cursor, limit: 20 } },
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useCompany(scope: string, id: string) {
  return useQuery({
    queryKey: ["company", scope, id],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/companies/{company_id}", {
        params: { path: { company_id: id } },
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useContacts(scope: string, id: string, cursor?: string) {
  return useQuery({
    queryKey: ["contacts", scope, id, cursor],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET(
        "/api/v1/companies/{company_id}/contacts",
        { params: { path: { company_id: id }, query: { cursor, limit: 20 } } },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useCompanyHistory(scope: string, id: string, offset: number) {
  return useQuery({
    queryKey: ["company-history", scope, id, offset],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET(
        "/api/v1/companies/{company_id}/activities",
        { params: { path: { company_id: id }, query: { offset, limit: 10 } } },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export async function writeArchive(command: ArchiveCommand) {
  const client = sessionClient();
  switch (command.kind) {
    case "create-company": {
      const r = await client.POST("/api/v1/companies", {
        params: { header: { "Idempotency-Key": command.key } },
        body: command.body,
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    }
    case "update-company": {
      const r = await client.PUT("/api/v1/companies/{company_id}", {
        params: {
          path: { company_id: command.id },
          header: { "Idempotency-Key": command.key },
        },
        body: command.body,
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    }
    case "create-contact": {
      const r = await client.POST("/api/v1/companies/{company_id}/contacts", {
        params: {
          path: { company_id: command.id },
          header: { "Idempotency-Key": command.key },
        },
        body: command.body,
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    }
    case "update-contact": {
      const r = await client.PUT(
        "/api/v1/companies/{company_id}/contacts/{contact_id}",
        {
          params: {
            path: { company_id: command.id, contact_id: command.contactId },
            header: { "Idempotency-Key": command.key },
          },
          body: command.body,
        },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    }
    case "add-role": {
      const r = await client.POST("/api/v1/companies/{company_id}/roles", {
        params: { path: { company_id: command.id } },
        body: command.body,
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    }
  }
}
export function useArchiveCommand(scope: string) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: writeArchive,
    onSuccess: async () => {
      await Promise.all(
        ["companies", "company", "contacts", "company-history"].map((name) =>
          cache.invalidateQueries({ queryKey: [name, scope] }),
        ),
      );
    },
  });
}
