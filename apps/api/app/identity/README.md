# Identity 与组织管理

遵循实施指南、ADR-012 和 ADR-018。User 是跨组织登录身份映射；OrganizationMembership 是组织内授权事实。

认证不自动创建用户或 membership。组织管理命令必须先锁当前 organization，再重新核验有效 ADMIN；查询和目标定位必须限定当前组织。不得开放全局用户列表、密码管理或修改已有全局 User。

成员写入保留历史数据，禁止移除最后一位有效管理员；所有管理命令原子记录 activity/audit/outbox 和幂等结果。组织名称及时区修改不能改变历史 UTC 时间。展示名只用于首次建立本地身份映射，不代表修改 Logto 资料。

接口位于 `/api/v1/organization`，提供设置查询/更新、成员游标列表/详情和添加、角色变更、停用、重新启用命令。所有写接口返回资源 ID，避免自我撤销授权后读取详情失败被误解为写入失败。管理界面在 `/admin/organization`，保存后刷新当前权限。

迁移 0021 仅增加分页索引，不回填用户或成员；降级只移除该索引、保留身份和授权事实。验证位于 `tests/test_identity_administration.py` 及前端对应单元/浏览器用例；真实 Logto 登录仍须独立验收。

`calendar.organization_timezone` 为领域服务提供当前组织的 IANA 时区，只读取指定且未删除组织。调用方仍负责权限和事务；组织不存在时明确失败，不回退到服务器时区。报价接受用此端口判断有效截止日，历史 UTC 事实不受后续时区配置更改影响。
