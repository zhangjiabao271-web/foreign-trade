# 外贸工作台实施指南

> Codex-ready Implementation Guide · Canonical Source · v0.1 · 2026-09-02

## 0. 文档地位与施工规则

本文件是外贸工作台仓库的实施基线，目标是让 Codex 或工程师在没有额外口头解释的情况下完成建仓、基础设施搭建和第一条端到端业务链。建议复制到目标仓库的 `docs/IMPLEMENTATION_GUIDE.md`，并在根目录 `AGENTS.md` 中要求每个实现任务先读取本文件。

执行优先级：本轮用户指令 > 已接受的 ADR > 本文件 > 模块内 README > 代码注释。发现冲突时不得静默选择；应记录冲突、给出最小决策建议，并停止受影响的不可逆实现。

施工时必须遵守以下原则：

1. 先打通一笔可盈利订单，再扩展功能面。
2. PostgreSQL 是业务事实的唯一来源；Redis、Celery、搜索索引、对象存储元数据缓存和 AI 都不是事实源。
3. 业务状态只能通过后端命令和领域服务变更，客户端不得直接写 `status`。
4. 所有业务数据必须绑定 `organization_id`；任何按主键读取也必须同时限定组织。
5. 金额、付款、报价接受、订单完成等动作必须在数据库事务内完成，并同步写审计与 outbox。
6. AI 只能通过受控工具调用应用服务，不得直连数据库，不得绕过权限、状态机或人工批准。
7. 每个纵向切片同时交付 migration、领域逻辑、API、前端、权限、审计和测试；不接受只做页面或只建表。
8. 不复制参考开源项目的受限代码。借鉴其对象、流程和交互设计，引入依赖前单独复核许可证。

### 0.1 完成的定义

“已完成”意味着：代码已格式化并通过静态检查；migration 可在空库执行；相关单元、集成、契约和端到端测试通过；组织隔离和权限已验证；OpenAPI 客户端已重新生成且无漂移；本地 Docker 环境可从零启动；变更、风险和未完成项有记录。仅“代码已写完”不算完成。

## 1. 产品目标、范围与非目标

### 1.1 产品使命

外贸工作台不是通用 ERP，也不是数据录入后台。它是一个以业务对象、状态流转、任务提醒和利润/现金可见性为中心的个人或小团队经营系统。

V1 的北极星目标是：

> 从发现一个潜在客户开始，在同一系统中完成一次真实或模拟的外贸订单，清楚看到报价毛利、采购承诺、出货文件、应收与回款，最终完成订单归档；适用时继续完成报关与退税案件的人工跟踪。

### 1.2 V1 必须覆盖

- 组织、用户成员关系与基础角色。
- 商业主体统一档案：客户、供应商、货代、代理等是同一个 `company` 的不同角色。
- 联系人、线索、商机、询盘和统一时间线。
- 产品、报价版本、成本、售价、币种、汇率快照、毛利和有效期。
- 报价审核、发送记录、接受/拒绝/过期/被新版本替代。
- 销售订单、采购订单、出货计划、文件元数据与关联。
- 应收、付款、付款核销、逾期判断和订单结清检查。
- 任务、活动、审计日志、可靠事件投递和异步任务状态。
- 人工维护的报关与退税案件状态（不对接政府系统）。
- AI 辅助查询、摘要、草稿和风险提示，所有高影响动作由人确认。

### 1.3 明确非目标

V1 不建设：

- 财务总账、会计凭证体系、自动报税或自动退税申报。
- 自动报关、海关/税务生产接口、信用证全流程。
- 完整库存、WMS、MRP、工厂排产和生产管理。
- 微服务、事件流平台、Elasticsearch/OpenSearch、数据湖。
- 原生移动 App、离线优先、多语言界面、复杂自定义 RBAC。
- 无人值守群发、自动谈判、自动改价、自动承诺交期或自动成交。
- 让 AI 执行任意 SQL、直接写核心业务表或持有无限制管理员令牌。
- 一开始就建设重型 CRM/ERP；没有服务首笔可盈利订单的模块不得优先。

## 2. 业务闭环与操作体验

### 2.1 主业务链

```text
Lead
  -> Company + Contact
  -> Opportunity
  -> Inquiry
  -> Quotation (versioned)
  -> Accepted Quotation
  -> Sales Order
  -> Purchase Order / Fulfillment
  -> Shipment + Documents
  -> Receivable
  -> Payment + Allocation
  -> Completed Order
  -> Customs Declaration / Tax Refund Case (when applicable)
```

最小可盈利闭环要求每笔订单都能回答：客户是谁、卖什么、预计收入、预计成本、毛利与毛利率、需要垫付多少、何时收款、当前卡点、下一动作和证据文件在哪里。

### 2.2 每日工作台

首页不是图表陈列，而是行动队列。第一版至少显示：待跟进线索、等待客户回复的报价、待收定金订单、待采购/待备货订单、准备出货订单、今日到期与逾期应收、文件不完整的出货/退税案件。每一项必须可点击到业务对象并看到完整时间线。

### 2.3 统一时间线

`activities` 记录关键事实：线索创建、联系、询盘、报价版本、报价发送/接受、订单确认、收款、采购、验货、订舱、出运、交付、报关和退税状态。时间线是投影，不替代各领域表；写入必须与业务事务原子完成，或由可幂等的 outbox 消费者可靠生成。

## 3. 角色与权限基线

V1 固定六个组织角色，不建设可视化权限编辑器：

| 角色 | 主要能力 |
|---|---|
| `ADMIN` | 组织设置、成员、全部业务与审计读取 |
| `MANAGER` | 审核报价、确认订单、查看利润与经营数据 |
| `SALES` | 客户、线索、商机、询盘、报价草稿和跟进 |
| `OPERATIONS` | 采购、履约、出货、文件、报关/退税跟踪 |
| `FINANCE` | 应收、付款、核销、费用和财务视图 |
| `VIEWER` | 组织范围内只读，敏感字段按策略隐藏 |

权限在 API 层和应用服务层都要校验。角色只是权限集合；领域服务应检查明确权限，例如 `quotation.approve`、`order.confirm`、`payment.record`，不要在业务代码中到处硬编码角色名称。

## 4. 核心数据模型

### 4.1 所有业务表的共同字段

除纯枚举/连接表的合理例外，统一包含：

```text
id                UUID PRIMARY KEY
organization_id   UUID NOT NULL
created_at        TIMESTAMPTZ NOT NULL
updated_at        TIMESTAMPTZ NOT NULL
created_by        UUID NULL
updated_by        UUID NULL
deleted_at        TIMESTAMPTZ NULL
version           INTEGER NOT NULL DEFAULT 1
```

`version` 用于乐观并发控制。删除优先软删除，但付款、审计、已确认订单等事实记录不得通过普通接口删除，只能冲销、取消或归档。

### 4.2 基础规则

- 主键与关联使用 UUID；`QT-2026-000001` 等编号只用于人类阅读。
- 金额使用 `NUMERIC(18,4)`；数量使用 `NUMERIC(18,4)`；汇率使用 `NUMERIC(18,8)`；禁止 `float`。
- 币种使用 ISO 4217 三位代码。金额 API 序列化为十进制字符串。
- 所有时间以 UTC 存储，API 使用 ISO 8601；组织时区默认 `Asia/Shanghai`，仅负责展示和业务日边界。
- 名称、邮箱、电话、税号等原始值和规范化值分开保存；唯一性约束使用规范化值。
- 业务唯一约束必须带 `organization_id`，并对软删除使用 partial unique index。
- 关键跨表关系建议使用 `(organization_id, id)` 组合唯一键与组合外键，数据库层阻止跨租户关联。
- 使用 `document_sequences` 在事务内生成组织级、类型级、年度级业务编号；不得用 `count + 1`。

### 4.3 实体清单与所有权

| 模块 | 核心表 | 关键关系/说明 |
|---|---|---|
| Identity | `organizations`, `users`, `organization_memberships` | 用户可属于多个组织；业务请求必须选定一个组织上下文 |
| Companies | `companies`, `company_roles`, `contacts` | 同一公司可同时为 `CUSTOMER`、`SUPPLIER`、`FORWARDER` 等 |
| CRM | `leads`, `opportunities`, `inquiries` | 转换线索时关联或创建 company/contact/opportunity，保留来源 |
| Catalog | `products`, `product_supplier_links` | 产品归组织；供应商关系含供应商货号、报价和交期信息 |
| Sales | `quotations`, `quotation_versions`, `quotation_items`, `sales_contracts`, `sales_orders`, `sales_order_items` | 已发送版本不可原地修改；接受锁定的版本生成订单 |
| Procurement | `purchase_orders`, `purchase_order_items` | 采购行可追溯到销售订单行，但允许合并/拆分 |
| Fulfillment | `shipments`, `shipment_items` | 出货可覆盖一个或多个订单行，数量不得超出可出货量 |
| Documents | `documents`, `document_versions`, `document_links` | DB 存元数据；对象存储保存二进制；多态关联由受控类型实现 |
| Finance | `receivables`, `payments`, `payment_allocations`, `payables`, `expenses` | 付款和核销分离；余额由可靠计算得出，不接受客户端传入 |
| Export | `customs_declarations`, `tax_refund_cases` | V1 只做人工作业状态、金额和文件完整性跟踪 |
| Work | `tasks`, `activities` | 任务可分配；活动是可审计时间线 |
| Platform | `audit_logs`, `outbox_events`, `async_jobs`, `idempotency_keys` | 横切能力，不归前端直接写入 |
| AI | `ai_runs`, `ai_tool_calls`, `approval_requests` | 记录输入摘要、模型、工具、结果、批准者和最终执行状态 |

### 4.4 关键关系不变量

- `company_roles` 对 `(organization_id, company_id, role)` 唯一；客户与供应商不得重复建两份公司档案。
- 一个 quotation 可有多个 version；同一时刻最多一个 current version；已发送版本内容不可变。
- quotation item 保存产品描述、数量、单位、单价、成本、税费/运费分摊和币种/汇率快照，历史报价不随产品主数据变化。
- quotation 只能接受一个有效版本；接受后其他活跃版本进入 `SUPERSEDED`。
- sales order 行必须复制接受版本的商业快照，不能只引用可变产品/报价数据。
- payment 可以核销多个 receivable，receivable 也可被多笔 payment 核销；分配金额均为正，累计不得超过付款可用额或应收未结余额。
- 订单完成前必须满足：发货/交付规则、必需文件规则、应收结清或经授权豁免、无阻断任务。
- 审计日志 append-only；不得通过普通业务接口修改或删除。

## 5. 状态机与命令

状态枚举只能由领域命令改变。每次转换必须校验当前状态、权限、前置条件和并发版本，并记录 `activity`、`audit_log` 与 `outbox_event`。

### 5.1 Lead

```text
NEW -> QUALIFIED -> CONTACTED -> RESPONDED -> CONVERTED
  \-> DISQUALIFIED
CONTACTED -> NO_RESPONSE
NO_RESPONSE -> CONTACTED
```

`convert` 必须幂等，创建或关联 company/contact/opportunity，并保存来源与转换时间。

### 5.2 Opportunity

```text
OPEN -> INQUIRY -> QUOTING -> NEGOTIATION -> WON
  \---------------------------------------> LOST
```

报价接受可在同一事务中把商机置为 `WON`；`LOST` 必须有原因。

### 5.3 Quotation Version

```text
DRAFT -> INTERNAL_REVIEW -> SENT -> CUSTOMER_REVIEW -> ACCEPTED
   \          \             \-> REJECTED
    \          \-------------> EXPIRED
     \------------------------> SUPERSEDED
```

允许命令：`submit_for_review`、`approve`、`send`、`mark_customer_review`、`accept`、`reject`、`expire`、`create_revision`。不得提供通用 `PATCH status`。

### 5.4 Sales Order

```text
DRAFT -> CONFIRMED -> DEPOSIT_PENDING -> EXECUTING
  -> READY_TO_SHIP -> SHIPPED -> COMPLETED
```

必要时允许从非终态进入 `CANCELLED`，但已发生付款、采购或出货时必须执行补偿/冲销规则，不得直接抹除事实。

### 5.5 Purchase Order

```text
DRAFT -> APPROVED -> SENT -> CONFIRMED
  -> PARTIALLY_RECEIVED -> RECEIVED -> CLOSED
```

`CANCELLED` 为受控旁路。已确认采购不得直接改价或改数量，应产生变更记录。

### 5.6 Shipment

```text
PLANNING -> BOOKED -> READY -> CUSTOMS -> DEPARTED
  -> IN_TRANSIT -> ARRIVED -> DELIVERED
```

出运命令必须检查数量、订单状态和必需文件清单。节点时间独立保存，不能仅由一个状态覆盖历史。

### 5.7 Receivable

```text
PENDING -> DUE -> PARTIALLY_PAID -> PAID
              \-> OVERDUE -> PARTIALLY_PAID / PAID
```

状态由到期日和 payment allocations 派生/受控更新，不接受前端直接写。付款撤销必须产生反向记录和审计。

### 5.8 Tax Refund Case

```text
NOT_READY -> DOCUMENTS_PENDING -> READY -> SUBMITTED
  -> PROCESSING -> REFUNDED
                         \-> REJECTED
```

V1 只记录人工申报事实、金额、日期、缺失文件与备注，不宣称系统已完成法定申报。

## 6. 架构决策

### ADR-001：Monorepo + Modular Monolith + 独立 Worker

采用单仓库、模块化单体 API 和独立 Celery Worker。业务模块在代码层清晰隔离，但共享 FastAPI 进程和 PostgreSQL。只有当吞吐、隔离或团队边界有实证需要时才拆服务。

### ADR-002：前后端职责分离

Next.js 负责页面、交互、表单、展示和客户端查询缓存。FastAPI 负责权限、业务规则、状态机、事务、数据库、AI 工具和外部集成。前端不得复制决定性业务规则。

### ADR-003：REST + OpenAPI

V1 不使用 GraphQL。FastAPI 生成 OpenAPI；TypeScript API client 自动生成。CI 必须检测 schema/client 漂移。

### ADR-004：PostgreSQL 为唯一事实源

Redis 可用于 broker、缓存、限流、临时状态和分布式锁，但清空 Redis 后系统仍可从 PostgreSQL 恢复。对象存储保存二进制，PostgreSQL 保存文件所有权、校验和、状态和关联。

### ADR-005：Transactional Outbox

业务写入和事件写入在同一数据库事务中提交。Worker 至少一次投递，消费者必须幂等。禁止在提交事务前把 Celery 调用当作可靠事实。

### ADR-006：外部服务全部经 Adapter

邮箱、AI、汇率、物流、爬取、对象存储和未来 n8n/WhatsApp 都通过明确接口接入。领域层不得依赖供应商 SDK，也不得把外部系统当唯一记录。

### ADR-007：搜索从 PostgreSQL 开始

V1 使用 PostgreSQL full-text search 和 `pg_trgm`。出现经测量的规模或检索能力瓶颈后再评估 OpenSearch/Elasticsearch。

## 7. 技术栈基线

以下是架构基线，不是鼓励追逐最新版本。建仓当天应选择对应稳定线的最新安全补丁并写入 lockfile；不得自动升级到 beta/RC。

| 层 | 选择 |
|---|---|
| Web | Next.js 16 Active LTS、React、TypeScript strict |
| UI | Tailwind CSS、shadcn/ui |
| Server state | TanStack Query |
| Forms | React Hook Form + Zod |
| API | FastAPI、Pydantic |
| Persistence | SQLAlchemy 2.0、Alembic |
| Database | PostgreSQL 18 stable line |
| Queue/cache | Redis |
| Worker | Celery 5.6 stable line |
| File storage | MinIO（本地）、S3-compatible（生产） |
| Auth | Logto、OIDC、JWT |
| AI | OpenAI Responses API / Agents SDK，经应用工具层调用 |
| Test | Pytest、Playwright、Vitest（前端单元测试） |
| Delivery | Docker Compose（开发）、Docker、GitHub Actions |
| Package managers | pnpm（JS/TS）、uv（Python，建议默认） |

## 8. Monorepo 结构

```text
trade-workbench/
├── AGENTS.md
├── README.md
├── docker-compose.yml
├── Makefile
├── .env.example
├── apps/
│   ├── web/
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   ├── lib/
│   │   └── tests/
│   ├── api/
│   │   ├── app/
│   │   │   ├── core/
│   │   │   ├── identity/
│   │   │   ├── companies/
│   │   │   ├── crm/
│   │   │   ├── catalog/
│   │   │   ├── sales/
│   │   │   ├── procurement/
│   │   │   ├── fulfillment/
│   │   │   ├── documents/
│   │   │   ├── finance/
│   │   │   ├── export/
│   │   │   ├── tasks/
│   │   │   ├── integrations/
│   │   │   ├── acquisition/
│   │   │   ├── ai/
│   │   │   └── audit/
│   │   ├── migrations/
│   │   └── tests/
│   └── worker/
│       ├── worker/
│       └── tests/
├── packages/
│   ├── api-client/
│   ├── shared-types/
│   ├── ui/
│   └── config/
├── infra/
│   ├── docker/
│   ├── nginx/
│   └── scripts/
└── docs/
    ├── IMPLEMENTATION_GUIDE.md
    ├── architecture/
    ├── database/
    ├── adr/
    └── product/
```

后端模块内部建议统一为：`models/`、`schemas/`、`repositories/`、`services/`、`routers/`、`permissions/`、`enums/`、`events/`、`tests/`。跨模块调用通过应用服务或公开端口，不得直接修改他模块拥有的 ORM 对象。

## 9. API 约定

### 9.1 资源与命令

基础路径为 `/api/v1`。资源读取/普通字段更新使用 REST；有业务含义的状态变化使用命令端点：

```text
GET  /api/v1/quotations/{id}
POST /api/v1/quotations/{id}/submit-for-review
POST /api/v1/quotations/{id}/send
POST /api/v1/quotations/{id}/accept
POST /api/v1/quotations/{id}/create-revision
POST /api/v1/sales-orders/{id}/confirm
POST /api/v1/payments/{id}/allocate
```

命令要返回更新后的资源或 `202 Accepted` + job resource。高风险或可重试的创建/命令支持 `Idempotency-Key`。并发修改使用 `If-Match`/版本字段；版本冲突返回 `409`。

### 9.2 数据格式

- JSON 字段使用 `snake_case`，生成客户端保持同名，不维护第二套手写类型。
- ID 为 UUID 字符串；日期时间为 ISO 8601 UTC；`date` 不附时区。
- 金额、数量和汇率为十进制字符串；同时返回币种，不返回裸金额。
- 列表优先 cursor pagination：`items`、`next_cursor`、`has_more`。
- 搜索、排序和过滤使用白名单字段；不得把 ORM 字段任意暴露为查询语言。
- 写请求应携带/返回 `request_id`；日志、审计、outbox 和 job 使用同一 correlation ID。

### 9.3 错误模型

采用稳定错误码，而不是让客户端解析自然语言：

```json
{
  "type": "https://trade-workbench.local/problems/invalid-state-transition",
  "title": "Invalid state transition",
  "status": 409,
  "code": "INVALID_STATE_TRANSITION",
  "detail": "Quotation must be SENT before it can be accepted.",
  "request_id": "uuid",
  "errors": []
}
```

常用状态：`400` 输入语义错误，`401` 未认证，`403` 无权限，`404` 不存在或不属于当前组织，`409` 状态/并发/幂等冲突，`422` 字段验证，`429` 限流。

## 10. 多租户与认证

### 10.1 认证流程

Logto 负责登录、密码、MFA、会话和 OIDC。FastAPI 验证 JWT 的签名、issuer、audience、expiry 和组织上下文，将其转换为 `RequestContext(user_id, organization_id, permissions, request_id)`。本地 `users` 与 `organization_memberships` 保存业务所需的用户映射、状态和角色。

### 10.2 强制隔离

Repository 方法签名必须显式带组织：

```python
get_sales_order(organization_id: UUID, order_id: UUID)
```

禁止：

```python
get_sales_order(order_id: UUID)
```

所有列表、计数、搜索、导出、后台任务、对象存储签名 URL 和 AI tool 都必须传播组织上下文。对其他组织的 ID 返回 `404`，避免泄露存在性。管理员角色只在本组织内有效；跨组织平台运维能力不在 V1 业务 API 中实现。

可以在后续使用 PostgreSQL RLS 作为纵深防御，但不能用它替代应用层条件和测试。连接池使用 RLS 时必须证明事务结束后上下文不会泄漏。

## 11. 事务、Outbox 与异步任务

### 11.1 事务边界

一个业务命令是一个事务。例如记录收款：创建 payment、创建 allocations、更新 receivable 状态、检查 order 状态、写 activity、audit log 和 outbox event，任一步失败则全部回滚。外部 HTTP 调用不得放在持锁数据库事务内。

### 11.2 Outbox 表与投递

`outbox_events` 至少包含：`id`、`organization_id`、`event_type`、`aggregate_type`、`aggregate_id`、`payload JSONB`、`status`、`attempt_count`、`available_at`、`locked_at`、`last_error`、`published_at`、`created_at`、`correlation_id`。

Relay 使用 `FOR UPDATE SKIP LOCKED` 批量领取，短事务标记后投递 Celery。投递语义是 at-least-once：event ID 是幂等键，消费者通过 `processed_events` 或领域唯一约束去重。失败采用指数退避加抖动；超过阈值进入 `DEAD`，必须能在管理界面查看并人工重放。

事件命名使用过去式：`quotation.accepted.v1`、`sales_order.confirmed.v1`、`payment.allocated.v1`。payload 只含处理所需快照和 ID，不把整张敏感记录复制进队列。

### 11.3 异步任务

满足“慢、可能失败、依赖外部服务、可重试”任一条件的工作进入队列。预留 queue：`default`、`email`、`documents`、`ai`、`acquisition`、`exports`。

API 对长任务创建 `async_jobs`，返回 `202` 和 `/api/v1/jobs/{id}`。job 状态为 `PENDING/RUNNING/SUCCEEDED/FAILED/CANCELLED`，保存进度、重试次数、错误码和结果引用。Celery result backend 不是用户可见任务事实源。

所有任务必须设置超时、有限重试、幂等键、结构化日志和组织上下文；网络重试不得重复发邮件、重复付款记录或重复生成业务单据。

## 12. 文件存储

文件二进制不进入 PostgreSQL。标准流程：

1. 客户端请求上传会话，API 创建 `document`/`document_version` 的 `PENDING_UPLOAD` 记录。
2. API 返回短时效预签名上传 URL 和随机化 object key；key 不包含客户名、邮箱等敏感信息。
3. 客户端直传 MinIO/S3 后调用 complete；服务校验 size、MIME、SHA-256 和对象存在性。
4. 异步执行恶意文件扫描/解析；状态依次为 `UPLOADED`、`SCANNING`、`AVAILABLE` 或 `REJECTED`。
5. 下载通过授权后的短时效预签名 URL；API 永不把永久公开 URL 当文件地址。

`documents` 保存业务归属、类型和最新版本；`document_versions` 保存不可变存储键、校验和、大小、MIME 和上传者；`document_links` 把文件关联到 order/shipment/customs/tax-refund 等受控对象。替换文件创建新版本，不覆盖旧对象。生产环境配置加密、生命周期、备份、跨租户 key 前缀和最小权限 bucket policy。

## 13. AI 权限边界

### 13.1 允许自动执行

- 在当前组织、当前用户权限范围内搜索和读取允许的数据。
- 摘要客户时间线、订单、文件解析结果和风险信号。
- 生成邮件、报价说明、跟进建议和任务建议的草稿。
- 计算基于只读快照的毛利情景，并标明假设与来源。

### 13.2 必须人工批准

- 实际发送邮件/消息或向外部系统提交数据。
- 新建或修改会影响同事工作的任务、客户资料和业务单据（纯个人草稿除外）。
- 改价、折扣、汇率、付款条件、交期、供应商承诺。
- 提交报价、接受/拒绝报价、确认/取消订单、确认出运。
- 记录/撤销付款、核销应收、提交报关/退税状态。
- 批量导出、批量更新或任何不可逆操作。

### 13.3 永远禁止

- 任意 SQL、数据库凭据、绕过应用服务的写入。
- 绕过组织隔离、权限检查、状态机、审计或 approval。
- 自动谈判、自动成交、自动承诺价格/交期、自动资金动作。
- 把密钥、完整 prompt、无关个人数据或整库数据发送给模型供应商。

AI 调用链必须是 `AI -> Tool -> Application Service -> Permission -> Business Rule -> Database`。每次 run 记录 model、prompt/version、用户、组织、数据引用、tool 参数摘要、结果、批准过程、token/成本和错误。敏感内容按日志策略脱敏；用户看到 AI 建议时必须能区分“事实”“推断”“草稿”。

## 14. 可观测性、安全与运营基线

- 全链路使用 `request_id`/`correlation_id`；结构化 JSON 日志禁止记录 token、密码、预签名 URL 和完整敏感正文。
- 指标至少包括 API latency/error、DB pool、outbox backlog/dead、queue age、job failure、上传/扫描失败、AI 成本与批准率。
- 健康检查分 liveness/readiness；readiness 检查必要依赖但不得执行昂贵查询。
- 秘钥只来自环境/secret manager；`.env.example` 只能给变量名和安全示例，绝不提交真实密钥。
- 数据库、对象存储和 Logto 配置纳入备份/恢复演练；备份成功日志不等于恢复成功。
- 所有生产 migration 先在最新备份副本演练；采用向前兼容的 expand/migrate/contract 策略。

## 15. 测试不变量

以下测试是发布门槛，不因“界面能用”而省略：

1. **租户隔离**：每个 repository/API/job/tool 对另一组织 ID 返回空或 `404`；列表、搜索、计数和导出同样隔离。
2. **状态机**：允许转换成功；所有非法转换返回稳定错误码且没有部分写入。
3. **事务原子性**：在 activity/audit/outbox 任一步注入失败，核心业务写入全部回滚。
4. **Outbox 可靠性**：事务提交才出现事件；重复投递不重复产生副作用；并发 relay 不重复领取。
5. **报价版本**：已发送版本不可变；revision 复制快照；只有一个版本可被接受；旧版本正确 supersede。
6. **金额精度**：Decimal 舍入策略固定；行合计、税费、运费、总额和毛利在多币种样例下可复算。
7. **付款核销**：分配总额不超付款或应收余额；并发核销使用锁/版本避免超额；撤销产生反向事实。
8. **编号**：并发生成不重复；按组织/类型/年度隔离；回滚不导致错误复用承诺。
9. **文件**：校验和、MIME、大小、组织授权和版本不可变；拒绝跨租户预签名访问。
10. **审计**：关键命令记录 actor、before/after 摘要、理由、request ID；普通接口不能修改审计。
11. **API 契约**：OpenAPI snapshot、生成客户端和实际路由一致；破坏性变化必须显式版本化。
12. **迁移**：空库升级成功；上一发布版数据副本升级成功；外键、唯一约束和必要索引存在。

测试层级：纯领域规则使用快速单元测试；repository/事务/outbox 使用真实 PostgreSQL 集成测试；Redis/MinIO/worker 使用容器集成测试；关键用户旅程使用 Playwright。不要用 SQLite 代替 PostgreSQL 验证生产语义。

## 16. 分阶段纵向切片计划

### Phase 0：仓库与开发底座

交付 monorepo、版本锁定、Docker Compose、环境示例、lint/typecheck/test 命令、CI、健康检查和本指南入库。验收：全新机器按 README 可启动 web/api/worker/PostgreSQL/Redis/MinIO。

### Phase 1：Identity、组织隔离与平台横切能力

交付 Logto JWT 验证、组织上下文、memberships、权限框架、审计、outbox、async job、编号服务。验收：两组织 fixture 的所有 API 隔离测试通过，示例命令可原子写入业务记录/审计/outbox。

### Phase 2：Company、Contact、Lead

交付统一 company roles、联系人、线索列表/详情/状态命令、线索转换和时间线。验收：Lead 从 `NEW` 转换为 customer company + contact + opportunity，重复命令不重复创建。

### Phase 3：Inquiry 与 Quotation

交付产品最小档案、询盘、报价版本/行项目、成本与毛利、审核/发送/接受命令。验收：创建 V1、生成 V2、旧版 supersede、接受 V2，并自动把 opportunity 置 `WON`。

### Phase 4：Sales Order 与 Procurement

交付从接受报价生成销售订单、确认、定金要求、采购订单与行映射。验收：报价商业快照稳定；订单确认触发采购任务；采购数量/金额和权限约束通过。

### Phase 5：Shipment 与 Documents

交付出货状态机、数量校验、预签名上传、文件版本、清单完整性和异步扫描/解析框架。验收：订单行可部分/合并出货，缺必要文件时不能执行受限出运命令。

### Phase 6：Receivable、Payment 与订单完成

交付应收、到期/逾期、付款、核销、余额和完成订单命令。验收：定金 + 尾款场景可精确核销；超额/并发核销失败且无部分写入；订单满足规则后归档完成。

### Phase 7：Export/Tax Refund 人工跟踪与经营首页

交付报关/退税案件状态、文件清单、提醒和行动型 Overview。验收：一笔订单从 Lead 到收款/完成并可继续走到 refund，首页显示真实待办而非硬编码统计。

### Phase 8：受控 AI Copilot

只在核心链稳定后交付。先做只读搜索、时间线摘要、毛利解释、邮件/跟进草稿，再接 approval workflow。验收：跨租户/越权 tool 调用失败；所有 tool call 可审计；AI 不能直接改变核心状态。

## 17. 编码标准

### 17.1 Python/FastAPI

- Python 类型检查采用严格模式；Pydantic schema 与 ORM model 分离。
- Router 只做 HTTP 映射；业务规则在 application/domain service；repository 只做持久化查询。
- Session/transaction 生命周期显式；禁止在 repository 内隐式 commit。
- ORM 查询必须包含组织条件；禁止返回未限定组织的可继续组合 query 给上层。
- 枚举、错误码和事件契约集中定义；禁止散落魔法字符串。

### 17.2 TypeScript/Next.js

- `strict: true`；API 类型来自生成客户端，不手写镜像 DTO。
- Server state 使用 TanStack Query；表单使用 React Hook Form + Zod，Zod 用于前端体验而非替代后端校验。
- 功能按 `features/<domain>` 组织；页面组件不得直接拼 URL 或决定状态转换。
- 可访问性、键盘操作、加载/空/错误/无权限状态是组件验收的一部分。

### 17.3 数据库与 Migration

- 每个 schema 变化都有 Alembic migration、约束/索引说明和回滚/前滚策略。
- 先加 nullable/兼容字段，再回填，再收紧约束；大表操作避免长锁。
- migration 不依赖在线外部服务，不把业务数据静默删除。
- 索引服务于已知查询；新增列表/搜索 API 同时提交 `EXPLAIN` 或基准证据（达到规模阈值时）。

### 17.4 Git 与变更纪律

- 一个任务一个可审查的纵向切片；不顺手重构无关模块。
- 不覆盖用户未提交修改；不使用破坏性 reset/checkout/clean。
- Commit/PR 说明包含业务结果、schema/API 变化、验证命令、风险和后续项。
- 对本指南的架构性偏离先写 ADR；不得让实现事实反向偷偷改写架构。

## 18. V1 总验收标准

使用两个组织、至少两个用户角色、三种币种和包含定金/尾款的 fixture，完成以下演示：

1. 组织 A 创建 Lead，转换为 company/contact/opportunity；组织 B 完全不可见。
2. 创建询盘和报价 V1；修改形成 V2，V1 被替代；销售提交、经理批准并发送。
3. 接受 V2 后商机 `WON`，从接受版本生成稳定销售订单快照。
4. 确认订单，生成采购任务/采购单，记录供应商承诺与预计成本。
5. 创建 shipment，上传并关联文件，完成出运和交付节点。
6. 生成定金和尾款应收，记录两笔付款并准确核销；逾期/余额逻辑可验证。
7. 满足前置条件后完成订单；时间线、审计和 outbox 可追溯全部关键动作。
8. 适用时创建报关/退税案件，显示缺失文件和下一动作。
9. 重启 Redis/worker 后 outbox 事件不丢；重复消费无重复副作用。
10. 从空环境启动、migration、测试、OpenAPI 生成、Playwright 主链和备份恢复冒烟全部通过。

性能初始目标：普通读 API 在本地基准数据集下 p95 < 500 ms；普通命令 p95 < 800 ms（不含外部服务）；长任务在 1 秒内返回 job；首页不使用 N+1 查询。实际生产 SLO 在获得真实负载后单独冻结。

## 19. 第一批可直接执行的 Codex 任务

### Task 001：初始化仓库

**目标**：创建上述 monorepo 骨架和根级开发体验。

**必须交付**：`AGENTS.md`、`README.md`、`docs/IMPLEMENTATION_GUIDE.md`、pnpm workspace、Python workspace、基础 web/api/worker、统一 lint/typecheck/test、`.env.example`、Dockerfiles、Docker Compose。

**验收**：一条文档化命令启动全部本地服务；web 和 API health 可访问；worker 能执行示例任务；CI 在空业务骨架上全绿。

### Task 002：建立数据库与迁移基线

**目标**：配置 SQLAlchemy/Alembic、UUID/timestamp mixin、命名约定和测试数据库。

**必须交付**：organizations、users、memberships、document_sequences、audit_logs、outbox_events、async_jobs、idempotency_keys 的首批 migration；组合租户约束示例；migration 测试。

**验收**：空库 upgrade head；上一 revision upgrade head；约束/索引审计通过；金额/时间类型符合本指南。

### Task 003：实现请求上下文与租户隔离

**目标**：接入可替换的 OIDC/JWT verifier，构造 RequestContext 和权限依赖。

**必须交付**：Logto adapter 接口、本地测试 issuer、membership 检查、组织选择、tenant-aware repository 基类/规范、跨租户测试矩阵。

**验收**：无组织/无成员/禁用用户/错误 audience 均失败；组织 B ID 对组织 A 返回 `404`；后台 job 也必须显式带组织。

### Task 004：实现事务、审计与 Outbox

**目标**：提供可复用 Unit of Work、领域事件和 relay。

**必须交付**：同事务写审计/outbox；`SKIP LOCKED` relay；Celery 投递；幂等 consumer 示例；dead-letter/replay 管理命令；故障注入测试。

**验收**：提交前 worker 不可见；回滚无事件；重复消费一次副作用；两个 relay 并发不重复领取。

### Task 005：生成 OpenAPI TypeScript Client

**目标**：建立 FastAPI schema 到 `packages/api-client` 的单向生成链。

**必须交付**：生成脚本、稳定命名、CI drift check、Next.js 示例 query、统一错误解析。

**验收**：修改 Pydantic response 后未重新生成会使 CI 失败；web 不存在手写重复 DTO。

### Task 006：第一个业务纵向切片——Company + Lead Conversion

**目标**：从页面创建/筛选 Lead，执行状态转换并转换成统一 company/contact/opportunity。

**必须交付**：migration、ORM、schema、repository、service、command API、权限、审计/outbox/activity、列表/详情/表单、单元/集成/Playwright 测试。

**验收**：完整走通 `NEW -> QUALIFIED -> CONTACTED -> RESPONDED -> CONVERTED`；重复 conversion 幂等；公司可同时添加 CUSTOMER/SUPPLIER 角色；跨租户全路径隔离。

## 20. Codex 首次施工提示词

将本文件放入目标仓库后，可直接给 Codex 以下任务：

```text
先完整阅读 AGENTS.md、docs/IMPLEMENTATION_GUIDE.md 和现有仓库，不要假设仓库为空，也不要覆盖未提交修改。

执行“Task 001：初始化仓库”。只完成 Task 001，不提前实现业务模块。

开始前：
1. 列出当前仓库事实、已有文件和可能冲突。
2. 将实施指南中的技术基线解析为明确的稳定版本和 lockfile；不要使用 beta/RC。
3. 给出本任务会新增/修改的文件清单。

实施时：
- 保持 Monorepo + Modular Monolith + 独立 Worker。
- PostgreSQL 是事实源；Redis 只做 broker/cache。
- 不写真实密钥，不引入与 Task 001 无关的产品功能。
- 每次变更保持可运行，并保留用户已有修改。

完成前必须运行并报告：格式化、lint、TypeScript/Python 类型检查、单元测试、Docker Compose 配置检查、web/API/worker/PostgreSQL/Redis/MinIO 启动冒烟。

最终报告：实际改动、验证结果、未验证项、架构决策、风险和下一步。不要只说“已完成”。
```

## 21. 决策待办（不阻塞 Task 001）

以下事项在相应纵向切片开始前冻结：生产部署平台与备份目标；Logto 自托管或云托管；生产对象存储供应商；组织级业务编号格式；报价税费/运费/汇率和舍入规则；销售订单完成的文件清单与财务豁免权限；首个邮件渠道；法定报关/退税流程的地区性字段。

在这些选择未完成前，使用 adapter、配置项和占位策略，不把供应商或地区规则硬编码进领域模型。

---

**维护要求**：任何改变事实源、服务边界、租户模型、状态机、资金不变量、AI 权限或外部副作用语义的变更，必须新增 ADR 并同步更新本指南。普通字段和 UI 细节不应让本文件膨胀为任务日志。
