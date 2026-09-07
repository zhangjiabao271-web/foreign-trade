"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { parseApiError, type components } from "@trade-workbench/api-client";
import { sessionClient } from "../overview/session";
type Schema = components["schemas"];
export type Organization = Schema["OrganizationResponse"];
export type Member = Schema["MemberResponse"];
export type IdentityWrite =
  | { action: "settings"; body: Schema["OrganizationUpdate"]; key: string }
  | { action: "add"; body: Schema["MemberCreate"]; key: string }
  | {
      action: "role";
      id: string;
      body: Schema["MemberRoleChange"];
      key: string;
    }
  | {
      action: "disable" | "reactivate";
      id: string;
      body: Schema["IdentityVersionCommand"];
      key: string;
    };

export function useOrganization(scope: string) {
  return useQuery({
    queryKey: ["organization-settings", scope],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/organization");
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useMembers(scope: string, cursor?: string) {
  return useQuery({
    queryKey: ["organization-members", scope, cursor],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/organization/members", {
        params: { query: { limit: 20, cursor } },
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useIdentityWrite(scope: string) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: async (command: IdentityWrite) => {
      const client = sessionClient();
      const header = { "Idempotency-Key": command.key };
      let r;
      switch (command.action) {
        case "settings":
          r = await client.POST("/api/v1/organization/update", {
            params: { header },
            body: command.body,
          });
          break;
        case "add":
          r = await client.POST("/api/v1/organization/members", {
            params: { header },
            body: command.body,
          });
          break;
        case "role":
          r = await client.POST(
            "/api/v1/organization/members/{member_id}/change-role",
            {
              params: { header, path: { member_id: command.id } },
              body: command.body,
            },
          );
          break;
        case "disable":
          r = await client.POST(
            "/api/v1/organization/members/{member_id}/disable",
            {
              params: { header, path: { member_id: command.id } },
              body: command.body,
            },
          );
          break;
        case "reactivate":
          r = await client.POST(
            "/api/v1/organization/members/{member_id}/reactivate",
            {
              params: { header, path: { member_id: command.id } },
              body: command.body,
            },
          );
          break;
      }
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
    onSuccess: async () => {
      await Promise.all([
        cache.invalidateQueries({ queryKey: ["member-context", scope] }),
        cache.invalidateQueries({ queryKey: ["organization-settings", scope] }),
        cache.invalidateQueries({ queryKey: ["organization-members", scope] }),
      ]);
    },
  });
}
