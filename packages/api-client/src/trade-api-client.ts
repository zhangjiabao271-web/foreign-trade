import createClient from "openapi-fetch";

import type { paths } from "./schema";

type MaybePromise<T> = T | Promise<T>;

export interface TradeApiClientOptions {
  baseUrl: string;
  getAccessToken: () => MaybePromise<string | undefined>;
  getOrganizationId: () => MaybePromise<string | undefined>;
}

export function createTradeApiClient(options: TradeApiClientOptions) {
  const client = createClient<paths>({ baseUrl: options.baseUrl });
  client.use({
    async onRequest({ request }) {
      const [accessToken, organizationId] = await Promise.all([
        options.getAccessToken(),
        options.getOrganizationId(),
      ]);
      if (accessToken) {
        request.headers.set("Authorization", `Bearer ${accessToken}`);
      }
      if (organizationId) {
        request.headers.set("X-Organization-ID", organizationId);
      }
      return request;
    },
  });
  return client;
}

export type TradeApiClient = ReturnType<typeof createTradeApiClient>;
