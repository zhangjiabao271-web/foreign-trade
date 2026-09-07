# 完整商业样例恢复验收

2026-09-07（核验时间 UTC 2026-09-06 20:20:01）。此项通过不代表 V1 总验收或生产恢复通过。

## 实际结果

- 隔离环境浏览器完整回归 31 项通过（3.0 分钟），保留真实 PostgreSQL/MinIO 商业样例。
- 从线索转换、报价 V1/V2、赢单、采购、出货、文件、定金/尾款核销到订单完成及人工报关退税的持久化数据恢复成功。
- 45 张表逐行排序后的 SHA-256 和行数一致；索引、触发器、已验证约束一致，恢复库 Alembic check 无漂移，版本 0032。
- 8 个对象版本（包括未验收覆盖版本）保留原版本 ID 和字节校验和；数据库 AVAILABLE 指针、大小和校验和逐一对应。
- 应用服务读取恢复后的完成订单和结清应收；经理可读成本，运营不可读成本，另一组织读取返回 404。
- 37 个 CHECK 的文本被 PostgreSQL 恢复解析改写为等价数组/元素类型转换。仅同表、同名、同类型、同验证状态的差异进入临时表重新解析比对；未忽略约束。临时 DDL 回滚，不改变持久化结构或原始清单。
- 最终专项测试 13 项通过（1.27 秒），含错误目标拒绝、真实 PostgreSQL 约束等价/不等价、临时表清理、真实数据变化拒绝和原清单不变。Ruff 及 Python 类型检查通过（210 文件）。

## 保留证据与边界

证据目录：`backups/20260907-commercial-recovery`。文件不可覆盖，源及恢复卷均保留。

| 文件                 | SHA-256                                                          |
| -------------------- | ---------------------------------------------------------------- |
| business.dump        | 0CEAB19B26452A4D5B5DC84523175C6D218A6CD51281D055EF7F7D95FDA5EF6A |
| minio.tgz            | 42587ACCB2D0D8440FD0D0FE02DC37BA88AB89554BA3885ED45D574D52ECD1B6 |
| source-manifest.json | A2B7AC855E9AC9554C60D94F9C36C2A9C7606FBF4A5857069B90C0E698FDE5DA |

`verification.json` 保存实际通过时间、覆盖和 37 个等价约束名称。首次核验因约束文本差异失败；备份和目标未重做，仅修正核验器后执行 verify。没有删除或覆盖业务数据。

浏览器仍使用测试身份签发器；第二组织 witness 仅是明确的合成隔离样例，不代表真实用户开户。恢复验证通过应用服务只读，不是恢复后真实 Logto 浏览器登录。初始化后的 Logto 数据、生产权限/所有者/密钥恢复、异地备份、生产扫描器和真实 AI 服务均不在本次证明范围。

## 演练流程与防误操作

仅用于 `trade-fresh-acceptance`，组合根 Compose、`infra/docker/fresh.compose.yml` 和 `infra/docker/commercial-recovery.compose.yml`。固定源端口 25432/29000，恢复端口 25433/29001，均为本机回环。主环境不参与。

1. 停止隔离 API/Web/worker/beat，启动指定源数据库和 MinIO。
2. 仅在尚无恢复样例库时执行 `infra/scripts/run-commercial-recovery-fixture.ps1`；它启用严格限定端点的保留模式，并在 finally 恢复进程环境变量。已有样例库必须拒绝，不能重建覆盖。
3. 浏览器/API 退出后，用 `apps/api/scripts/commercial_recovery_probe.py prepare-isolation` 一次性建立第二组织 witness，再用 `snapshot` 一次性生成源清单。
4. `infra/scripts/rehearse-commercial-restore.ps1` 检查项目标签、源卷、停写和全新空目标，执行 PostgreSQL custom dump 与停止 MinIO 后的整卷冷备，再恢复至独立新卷。整个 MinIO 卷用于保留版本元数据，不以重新上传替代。
5. 核验失败时保留全部证据；诊断后仅执行 probe 的 `verify`，不要重跑备份、样例建立或恢复脚本。成功报告也拒绝覆盖。
6. 最后用上述三个 Compose 文件执行 `stop`，保留所有卷和备份；禁止 `down -v`。

本次步骤已经执行，已有文件和卷是保护性拒绝条件，不应为了重跑而删除。另一次演练需另行指定并审查新的隔离目标与证据目录。
