"use client";

import {
  parseApiError,
  type TradeApiClient,
} from "@trade-workbench/api-client";
import { useQuery } from "@tanstack/react-query";

export function useJobs(apiClient: TradeApiClient) {
  return useQuery({
    queryKey: ["jobs"],
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET("/api/v1/jobs");
      if (!data) {
        throw await parseApiError(response, error);
      }
      return data;
    },
  });
}
