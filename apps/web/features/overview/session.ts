"use client";
import { useSyncExternalStore } from "react";
import { createTradeApiClient } from "@trade-workbench/api-client";
import { sessionKeys } from "../leads/api";
const eventName = "trade-workbench-session-change";
let previousCredentials = "";
let generation = 0;
function snapshot() {
  const organization = localStorage.getItem(sessionKeys.organizationId) ?? "";
  const token = localStorage.getItem(sessionKeys.accessToken) ?? "";
  const marker = localStorage.getItem(sessionKeys.marker) ?? "";
  const credentials = JSON.stringify([organization, token, marker]);
  if (credentials !== previousCredentials) {
    previousCredentials = credentials;
    generation += 1;
  }
  return organization && (token || marker)
    ? `${generation}:${organization}`
    : "";
}
function subscribe(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener(eventName, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(eventName, callback);
  };
}
export function useSessionScope() {
  return useSyncExternalStore(subscribe, snapshot, () => "");
}
export function sessionClient() {
  const organization =
    localStorage.getItem(sessionKeys.organizationId) ?? undefined;
  const token = localStorage.getItem(sessionKeys.accessToken) ?? undefined;
  return createTradeApiClient({
    baseUrl: window.location.origin + "/api/backend",
    getOrganizationId: () => organization,
    getAccessToken: () => token,
  });
}
export function connectSession(organization: string, token: string) {
  localStorage.setItem(sessionKeys.organizationId, organization);
  localStorage.setItem(sessionKeys.accessToken, token);
  window.dispatchEvent(new Event(eventName));
}
export function disconnectSession() {
  localStorage.removeItem(sessionKeys.organizationId);
  localStorage.removeItem(sessionKeys.accessToken);
  window.dispatchEvent(new Event(eventName));
}
