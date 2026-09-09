# 外贸工作台

围绕“第一笔可盈利订单”建设的个人/小团队经营系统。当前进行 **V1 总验收**：模拟订单已完成收款、结案、人工清关与退税；真实 Logto 销售/经理登录、本机加密联合恢复，以及真实 DeepSeek 草稿的内容审核和独立任务执行审批已有验收证据。完整指南逐项审计和远程 CI 仍未关闭，尚未宣告 V1 全部完成。最新证据与边界见 [`docs/acceptance/V1_STATUS.md`](docs/acceptance/V1_STATUS.md)。

规范性实施基线见 [`docs/IMPLEMENTATION_GUIDE.md`](docs/IMPLEMENTATION_GUIDE.md)。

## 当前组成

- `apps/web`：Next.js 16 / React 19 的 Web 壳层与健康端点。
- `apps/api`：FastAPI 服务，提供健康检查、JWT 验证、请求上下文和 tenant-aware 查询边界。
- `apps/api/app/companies`：统一商业主体、可叠加公司角色和联系人。
- `apps/api/app/crm`：线索列表/详情、受控状态命令、幂等转换和商机来源追踪。
- `apps/api/app/catalog`：组织级产品档案与成本币种默认值。
- `apps/api/app/inquiries`：客户询盘与商机关联。
- `apps/api/app/sales`：版本化报价、商业快照、毛利核算和审核/接受状态机。
- `apps/api/app/sales/order_*`：从接受报价幂等建单、稳定订单快照、定金要求和经理确认命令。
- `apps/api/app/procurement`：供应商角色约束、采购行映射、采购承诺核算和采购状态命令。
- `apps/api/app/fulfillment`：部分/合并出运、数量占用、八节点出运状态机和订单出运汇总。
- `apps/api/app/documents`：组织隔离的文件元数据、预签名上传/下载、SHA-256 完整性校验和异步扫描框架。
- `apps/api/app/finance`：定金/尾款应收、幂等收款与核销、反向冲销事实、余额与组织业务日状态。
- `apps/api/app/work`：订单待办的版本校验完成命令与订单时间线。
- `apps/api/app/export`：人工报关／退税状态、证据清单、跟进日期与分页时间线。
- `apps/api/app/ai`：组织隔离的异步只读工具、草稿与人工批准任务；未配置模型时明确不可用。
- `apps/web/features/overview`：八类真实行动队列，按权限和组织隔离，支持独立分页。
- `apps/web/features/finance`：订单详情内的财务表单与结案检查。
- `apps/api/migrations`：Alembic revisions；Compose 启动时先执行 migration，再启动 API。
- `apps/worker`：Celery worker 与可验证的 `health.ping` 示例任务。
- `worker-beat`：定时扫描 PostgreSQL outbox；队列只负责投递，不保存业务事实。
- `packages/api-client`：由 FastAPI schema 生成的 TypeScript 类型与统一请求/错误边界。
- PostgreSQL 18：后续业务事实的唯一来源。
- Redis：Celery broker/cache，不保存用户可见任务事实。
- MinIO：本地对象存储；业务所有权、版本、校验和与可用状态仍由 PostgreSQL 持有。

## 前置条件

- Node.js 24、pnpm 11
- Python 3.12、uv
- Docker Desktop（含 Docker Compose v2）

## 从零启动

```bash
copy .env.example .env
pnpm install --frozen-lockfile
uv sync --frozen --all-packages
docker compose up --build
```

`migrate` 是一次性服务。它会在 PostgreSQL 健康后执行 `alembic upgrade head`；只有 migration 成功，API 才会启动。

启动完成后：

- Web：<http://localhost:3000>
- Web health：<http://localhost:3000/api/health>
- API liveness：<http://localhost:8000/health/live>
- API readiness：<http://localhost:8000/health/ready>
- MinIO Console：<http://localhost:9001>

验证 worker 示例任务：

```bash
docker compose exec worker celery -A worker.app call health.ping
docker compose exec worker celery -A worker.app inspect ping --timeout 5
```

受保护 API 使用 Bearer JWT 和 `X-Organization-ID`。生产运行时通过 Logto/OIDC JWKS
验证签名；测试使用独立的本地 issuer。认证和隔离约定见
[`apps/api/app/auth/README.md`](apps/api/app/auth/README.md)。

查看当前数据库 revision：

```bash
docker compose exec api alembic -c alembic.ini current
```

迁移测试使用真实 PostgreSQL，并为每个测试创建和销毁独立临时数据库；文件版本集成测试还使用真实 MinIO。运行测试前应启动专用本地测试服务：

```bash
docker compose up -d --wait postgres minio
pnpm test
```

## 日常质量门槛

首次运行浏览器验收前安装 Chromium：`pnpm --filter @trade-workbench/web exec playwright install chromium`。
Linux CI 使用 `playwright install --with-deps chromium` 同时准备系统依赖。
浏览器验收使用独立测试数据库和测试身份，不替代真实 Logto 登录；不要把测试连接指向业务数据库。
默认测试不需要模型密钥，真实付费模型测试必须另行显式启用和授权。

```bash
pnpm api-client:check
pnpm --filter @trade-workbench/api-client test:drift
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm --filter @trade-workbench/web test:e2e
pnpm build
docker compose config --quiet
```

也可以使用 `make check`。Windows 未安装 `make` 时直接运行上面的命令。

## 边界

- `.env.example` 只含本地示例值，禁止写入真实密钥。
- readiness 继续使用轻量 TCP 探测；数据库 schema 状态由一次性 `migrate` 服务和 migration 测试验证。
- Task 006 已交付 Company/CompanyRole/Contact/Lead/Opportunity/Activity、线索命令与幂等转换、审计/outbox 原子写入、tenant-aware API，以及线索列表/详情/表单和 Playwright 主链。
- Task 007 已交付 Product、Inquiry、Quotation/Version/Item，冻结 Decimal 舍入和三币种快照规则，并通过 V1 → V2 → 审核 → 发送 → 接受的 Playwright 主链。
- Phase 4 已交付 Sales Order、Sales Order Item、采购准备任务、Purchase Order/Item，冻结接受报价快照、定金计算、采购数量/金额和供应商承诺规则，并通过报价接受 → 建单 → 确认 → 采购批准/发送/确认的 Playwright 主链。
- Phase 5 已交付 Shipment/ShipmentItem、Document/DocumentVersion/DocumentLink，支持跨订单行部分/合并装运、累计数量约束、八节点命令、离港文件齐套检查、浏览器预签名直传、完整性校验、异步可用状态和授权下载，并通过真实 MinIO 的 Playwright 主链。
- Phase 6/7 业务主链已通过浏览器测试；剩余验收和 Phase 8 受控 AI 见 `docs/acceptance/V1_STATUS.md`。
- 生产部署、Logto 托管方式、对象存储供应商和订单完成文件清单仍是指南中的决策待办。
