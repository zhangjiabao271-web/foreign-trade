# Database

Task 002 使用 PostgreSQL 18、SQLAlchemy 2.0、Alembic 和 psycopg 3 建立数据库基线。PostgreSQL 是唯一业务事实源。

## Revisions

- `20260903_0001`：`users`、`organizations`、`organization_memberships`。
- `20260903_0002`：`document_sequences`、`audit_logs`、`outbox_events`、`async_jobs`、`idempotency_keys`。
- `20260903_0003`：`processed_events` 与 outbox 的组织级组合引用约束。
- `20260903_0004`：`companies`、`company_roles`、`contacts`、`leads`、`opportunities`、`activities`。
- `20260904_0005`：`products`、`inquiries`、`quotations`、`quotation_versions`、`quotation_items`。
- `20260904_0006`：`sales_orders`、`sales_order_items`、`purchase_orders`、`purchase_order_items`、采购准备任务字段。
- `20260904_0007`：`shipments`、`shipment_items`、`documents`、`document_versions`、`document_links`。
- `20260905_0008`：`receivables`、`payments`、`payment_allocations`；租户组合外键、正金额与冲销引用约束。
- `20260905_0009`：人工报关与退税案件、跟进和证据要求。
- `20260906_0010`：固定已校验对象的具体存储版本，保留历史证据。
- `20260906_0011`：AI runs、工具调用凭据和人工审批请求；组织组合关联及状态约束。

空库执行：

```bash
uv run alembic -c apps/api/alembic.ini upgrade head
```

Compose 会通过一次性 `migrate` 服务自动执行相同命令；migration 成功后 API 才启动。

## Schema invariants

- 主键与业务关联使用 UUID；时间字段使用 `TIMESTAMPTZ`。
- 金额、数量、汇率的标准 SQLAlchemy 类型分别为 `NUMERIC(18,4)`、`NUMERIC(18,4)`、`NUMERIC(18,8)`，禁止 `float`。
- 所有租户表包含 `organization_id`；成员关系提供 `(organization_id, user_id)` 组合唯一键。
- 平台表的 actor 通过 `(organization_id, user_id)` 组合外键指向 membership，数据库层拒绝跨组织 actor。
- `document_sequences` 对组织、单据类型和年度唯一；显示编号格式留待业务规则冻结，不在 schema 中硬编码。
- `audit_logs` 由数据库 trigger 强制 append-only。
- outbox 的待投递扫描、聚合对象追踪，异步任务状态，以及幂等键过期清理均有明确索引。
- consumer 以 `(organization_id, event_id, consumer_name)` 去重，幂等标记与副作用同事务提交。

## Migration verification

测试连接由 `TEST_DATABASE_ADMIN_URL` 指定，默认连接本机 Compose PostgreSQL。每个测试生成独立数据库，结束后强制断开并删除，不触碰 `trade_workbench` 主数据库。

```bash
docker compose up -d postgres
uv run pytest apps/api/tests/test_migrations.py
```

自动检查包括：空库升级至 head、从上一 revision 升级、表/约束/索引审计、时区类型、跨租户组合外键和审计 append-only。

## Forward and rollback strategy

`20260907_0033` adds organization-scoped `ai_disclosures`, explicit preserved candidate versions,
run/candidate digests, decisions and reviewer metadata. No run/output/history is backfilled,
rewritten or implicitly submitted. Empty schema downgrade is supported; any disclosure evidence
blocks downgrade so original/confidential content cannot be silently deleted or reopened.
Previous0032 commercial/AI snapshot upgrade and populated0033 rollback refusal are tested.

`20260907_0032` adds six partial active cursor indexes: shipments, quotations, inquiries
(with/without status), and purchase orders (with/without sales_order_id). Downgrade drops only
these indexes. Full persisted commercial snapshots are compared across0032→0031→head in the
navigation integration test; no schema backfill, record deletion or permission change occurs.

`20260907_0031` adds only the active sales-order `(organization_id, created_at, id)` paging
index. Existing rows and commercial/evidence values are unchanged. Downgrade removes only this
index; re-upgrade is supported. The commercial-copy migration test compares all persisted facts
before/after both directions and checks Alembic metadata. Main deployment remains a separate
authorized operation; current checks run on disposable/isolated databases.

涉及证据保留的后续 revisions 不支持破坏性 downgrade，必须核对具体迁移说明。采用 expand/migrate/contract：先加兼容字段或表，再回填并验证，最后在独立 revision 收紧约束；禁止 migration 静默删除业务数据。升级前生成一致性备份，并恢复到独立数据库验证升级和结构一致性。

## Dependency licenses

完整商业样例在0032的 PostgreSQL + 版本化 MinIO 恢复已于2026-09-07核验：45表、8个对象版本、
业务结清与隔离投影一致，Alembic无漂移。见 `docs/acceptance/COMMERCIAL_RECOVERY.md`；
初始化后的Logto恢复和生产身份/密钥/所有者恢复不在本次验收范围。

- SQLAlchemy：MIT。
- Alembic：MIT。
- psycopg：LGPL-3.0-only；binary wheel 仅作为 Python PostgreSQL 驱动使用，不复制或修改其源码。
