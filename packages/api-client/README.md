# API client

FastAPI 是契约的唯一来源。`pnpm api-client:generate` 导出稳定 OpenAPI snapshot，并用
`openapi-typescript` 生成 `src/schema.d.ts`。`openapi-fetch` 在这些生成类型之上提供运行时
client；Web 不得手写镜像 DTO。

`pnpm api-client:check` 在临时目录重新生成并逐字节比较两个产物。Pydantic response、路由
或生成器变化后未重新生成会使 CI 失败。

依赖许可证：`openapi-typescript` 与 `openapi-fetch` 均为 MIT。
