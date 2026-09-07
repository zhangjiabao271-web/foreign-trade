"use client";

import { useRef } from "react";
import { useSessionScope } from "../overview/session";
import type { UploadRetry } from "./transfer";

export function useUploadRetry(): () => UploadRetry {
  const scope = useSessionScope();
  const holder = useRef<{ scope: string; retry: UploadRetry }>({
    scope,
    retry: {},
  });
  return () => {
    if (holder.current.scope !== scope) holder.current = { scope, retry: {} };
    return holder.current.retry;
  };
}
