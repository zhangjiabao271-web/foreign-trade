"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { AuthGate } from "./auth-gate";
import { useSessionScope } from "../features/overview/session";

export function AppProviders({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const scope = useSessionScope();
  return (
    <AuthGate>
      <ScopedQueries key={scope}>{children}</ScopedQueries>
    </AuthGate>
  );
}

function ScopedQueries({ children }: Readonly<{ children: React.ReactNode }>) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: 1,
            staleTime: 30_000,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
