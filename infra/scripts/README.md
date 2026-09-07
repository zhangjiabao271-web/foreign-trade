# Scripts

## Current-user encrypted joint recovery

用户已批准本机 DPAPI CurrentUser 保护，详见 `docs/acceptance/JOINT_LOCAL_RECOVERY.md`。
`user-encrypted-backup.ps1` 是二进制内存加密辅助；`test-user-encrypted-backup.ps1`
仅生成合成自检密文。`joint-local-recovery.ps1` 提供 Check/Backup/Restore/VerifyRoles/VerifySchema，
固定源与全新 v2 目标，拒绝覆盖；Backup 和 Restore **已经执行，不能重跑**。
`joint-runtime-rehearsal.ps1` 的 Capture 已执行；Start 临时使用原地址验收恢复副本，
ReturnToSource 用于切回原服务。当前地址归属和待验收项必须先读上述记录。
所有密钥只在内存和 `.dpapi` 包中传递，不输出真实 Compose config、子进程诊断或密码。
VerifySchema只读比较原加密备份和已有恢复库，不执行恢复 SQL。结构比较的有限等价转换
在 `backup-schema-normalization.ps1`，独立自检为 `test-backup-schema-normalization.ps1`。
不通过时定位实际差异，不扩大忽略规则或改写已有恢复对象。

真实身份样例初始化见 `apps/api/scripts/identity_acceptance_fixture.py` 与
`docs/acceptance/REAL_IDENTITY.md`。这是已执行的一次性本机验收 bootstrap，
不是生产 provisioning：要求固定配置与实际目标库核对、显式确认，并拒绝任何
已有用户/组织的数据库。不要重跑或清空数据库；后续授权走组织管理命令。

完整商业恢复演练另见 `docs/acceptance/COMMERCIAL_RECOVERY.md`。
`run-commercial-recovery-fixture.ps1` 仅在严格限定的隔离环境保留商业样例；
`rehearse-commercial-restore.ps1` 拒绝覆盖现有证据和恢复卷。当前演练已完成，勿重复执行或删除证据。

只存放可重复、非交互的开发与运维脚本。数据库迁移/备份脚本从 Task 002 开始加入，并必须附验证说明。

## Paired database/object-store recovery rehearsal

`rehearse-storage-restore.ps1` only targets the named `trade-recovery-acceptance` stack.
It is an acceptance probe, not an unattended production backup policy. It verifies container
project labels and empty restore targets, refuses evidence overwrite, stops source writers,
uses PostgreSQL custom-format dump plus a cold tar of the **entire MinIO volume**, then
restores into separate volumes. Keeping the MinIO volume metadata preserves storage version IDs;
ordinary S3 re-uploads would generate different IDs and break pinned document evidence.

Prerequisite: the queue-recovery fixture exists in the isolated database. Start minio-source
and postgres-restored using `infra/docker/recovery.compose.yml`. Copy
`apps/worker/scripts/storage_recovery_probe.py` to that worker's `/tmp/storage_recovery_probe.py`
and execute its `prepare` action once. The fixture creates two database document versions and
three actual object versions, including an unaccepted overwrite, plus full table fingerprints.
Run `./infra/scripts/rehearse-storage-restore.ps1` from the workspace. It retains backups under
`backups/20260906-storage-restore`, compares all 38 table fingerprints, verifies both pinned
versions by their original IDs/checksums and checks Alembic metadata on the restored database.

Source services restart in a finally block if backup fails. No existing target database or
object volume is overwritten; no automatic deletion is provided. Recovery data and hashes
are synthetic and local. Production backups additionally require an approved encrypted backup
destination, secret recovery process, retention policy and initialized Logto restore testing.
