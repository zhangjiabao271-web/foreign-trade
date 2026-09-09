# Docker

## Latest API image selection (Sep9 document/export correction)

Current stack requires ten files in order: docker-compose.yml, fresh, identity-acceptance,
acceptance-storage, deepseek-acceptance, release-0035, owner-ports, session-presence,
forwarder-boundary and document-export-boundary.compose.yml (all overlays under infra/docker).
The tenth image-only layer selects document-export-20260909 for API. Worker/beat and Web are
unchanged. The one-time guarded deployment has executed; older image-selection notes below
are historical, not instructions to omit newer layers. Preserve all existing volumes and secrets.

## Latest Web image selection (Sep9)

Append session-presence.compose.yml as the eighth image-only overlay after owner-ports and
all six earlier files. Web now uses session-presence-20260909; API/Worker retain owner-ports.
The guarded Web-only script has already run; exact old-image guards intentionally refuse reruns.

## Latest owner-port image selection (Sep9)

Append owner-ports.compose.yml AFTER release-0035.compose.yml and all five behavioral overlays
listed below. The seventh image-only overlay is now deployed for API/Worker/beat; Web remains
ui-baseline-20260908. Omitting it selects superseded images. Guarded deploy-owner-ports.ps1
has already run and refuses changed source images. Do not rerun old migration/deployment scripts.
Current exact image IDs, tests, environment/data preservation and health are in V1_STATUS.

## Current local acceptance images (0035)

After all five overlays below, release-0035.compose.yml selects the separately built and
verified API/Worker/Web images. This image-only sixth overlay changes no identity,provider,
storage or database settings. Applied2026-09-08 with the one-time guarded deployment script;
do not rerun the migration script. Future updates must retain all five behavioral overlays
and deliberately update image selection rather than reverting to an older default tag.
The Web image includes shared-ui source/dependency notices under /app/licenses/ui.
The latest image selection uses Worker queues-20260908 for both worker and beat; it reserves
the six guide queue names but continues consuming default only. Operational environment copying
must split KEY=value at the first equals sign (or use the verified prefix length helper),never
hardcode secret-prefix character offsets. Preserve exact credential equality before accepting
an update; current V1_STATUS records the caught-and-corrected transfer error and final health.

## DeepSeek synthetic acceptance (ADR-029)

After the four fresh/identity/storage files, append deepseek-acceptance.compose.yml to keep
API and worker on the explicitly selected deepseek-v4-pro. DEEPSEEK_API_KEY must already be
in the invoking environment; never echo it, write it to files, or dump interpolated config.
Use config --quiet. Check no PENDING/RUNNING AI runs before switching/restarting, and update
only api worker with --no-deps. Preserve all existing identity secrets and volumes.
No secret goes to Web/API. Variable peak/off-peak/cache pricing stays unknown in the static
estimate until separately configured. Future acceptance-stack updates must retain this fifth
overlay; dropping it would select the base default provider. This is not production deployment.

## Joint encrypted recovery targets

`joint-restore.compose.yml` 为独立项目 `trade-joint-restore-v2`，以原 rehearsal/logto
初始化角色恢复原授权语义，不开放数据库和 MinIO 主机端口。已有目标禁止重建覆盖。
追加 `joint-restore-runtime.compose.yml` 才启用原 localhost3300/3001/3002 地址，
必须通过 `infra/scripts/joint-runtime-rehearsal.ps1` 从加密文件注入配置并停用原端点。
不要直接调用缺少加密配置的 up。详见 `docs/acceptance/JOINT_LOCAL_RECOVERY.md`。

服务镜像入口位于各应用目录的 `Dockerfile`。此目录保留给后续通用 entrypoint、镜像加固与构建辅助文件。

## Local identity service

`docker compose -f docker-compose.yml -f infra/docker/logto.compose.yml up -d logto`
starts the pinned Logto 1.43.0 service and its own persisted PostgreSQL 17 database.
Identity ports are bound to host loopback only. This overlay does not select a production
provider and does not change the business database. Do not remove its named volume when
restarting. Full recovery must include this database as well as business DB and object data.

Local issuer uses `http://logto.localhost:3001/oidc`; admin console is on localhost:3002.
The overlay gives Web/API the same issuer hostname via the Docker host gateway. Configure
a Traditional Web application, callback `/api/auth/callback` at APP_BASE_URL, a post-logout
APP_BASE_URL, and the business API resource before enabling login. Pin
OIDC_SIGNING_ALGORITHM to the verified issuer algorithm: the current local issuer
advertises ES384 (EC P-384), as recorded in ADR-012. RS256 remains supported only
for an issuer explicitly configured and verified to use it; never infer trusted
algorithm policy from an unverified token.
Set all LOGTO/APP/OIDC environment variables consistently; the loopback HTTP exception
requires LOCAL_AUTH_ALLOW_HTTP=true. Production requires HTTPS and deployment secrets.

License review (2026-09-06): Logto server is MPL-2.0; the official Next.js SDK is MIT.
We run the unmodified server image separately and import no Logto server source code.
Redistribution or server modifications require a fresh license-obligation review.
Reference: https://github.com/logto-io/logto/blob/v1.43.0/LICENSE and the matching
official docker-compose.yml. Image bootstrap follows that version's documented seed command.

## Isolated queue-recovery acceptance

`recovery.compose.yml` is a separate `trade-recovery-acceptance` project, not an overlay.
Always invoke it with `docker compose --project-directory . -f infra/docker/recovery.compose.yml`.
Its database/broker have no published host ports and never share the main stack's volumes.
Build worker; start postgres/redis/migrate; run `worker python scripts/recovery_probe.py prepare restart`
with `run --rm --no-deps` while the worker is stopped. Restart its Redis, start worker, then
execute the probe's `check restart` and `duplicate restart` actions in the running worker.

For the `broker-loss` scenario, stop worker before preparation. Only after verifying the Redis
container's Compose project label is `trade-recovery-acceptance`, clear that test broker's DB,
restart worker and run `recover broker-loss`, `check broker-loss`, `duplicate broker-loss`.
Never flush the main Redis. The probe refuses any database not explicitly named
`trade_recovery_acceptance` with acceptance-mode opt-in. Prepare refuses to overwrite existing
scenario evidence; retain volumes after the run. No automatic destructive cleanup is provided.

## Fresh complete startup

`docker compose -p trade-fresh-acceptance -f docker-compose.yml -f infra/docker/fresh.compose.yml up -d --build`
builds all application images and starts a separately named stack with new project volumes.
The overlay requires modern Docker Compose support for `!reset`/`!override` ports. Infrastructure
has no published ports; Web binds localhost:3300. It intentionally leaves real login and model
providers unconfigured, so readiness is not real-login acceptance. Use `ps`, API Alembic
current/check, Worker inspect ping and Web health/platform-health to verify startup. Preserve
the named volumes as evidence; no main-stack volumes are reused and no cleanup is automatic.

## Real login in the isolated acceptance stack

After the user configures the local Logto application and test accounts, append
`identity-acceptance.compose.yml` after the fresh overlay. It connects the existing
local issuer to the isolated business stack; it does not create another Logto,
grant memberships, change the main stack or configure a production provider.

Supply `ACCEPTANCE_LOGTO_APP_SECRET` and a separate random
`ACCEPTANCE_LOGTO_COOKIE_SECRET` (at least32 characters) through the invoking
process environment. Do not put values in source, command history, reports or chat.
Keep the session secret stable for a session/recovery exercise and arrange its
secure retention separately. Missing credentials fail Compose interpolation.
Use `config --quiet`, not an unredacted configuration dump with real credentials.

```bash
docker compose -p trade-fresh-acceptance -f docker-compose.yml -f infra/docker/fresh.compose.yml -f infra/docker/identity-acceptance.compose.yml config --quiet
docker compose -p trade-fresh-acceptance -f docker-compose.yml -f infra/docker/fresh.compose.yml -f infra/docker/identity-acceptance.compose.yml up -d
```

The registered application is `3h8workreqipkalzznnnq`; callback is
`http://localhost:3300/api/auth/callback`, post-logout is `http://localhost:3300`.
Issuer/JWKS use the verified ES384 policy. Only Web port3300 is exposed on loopback;
the inherited fresh overlay keeps API/database/broker/object-store ports private.
This overlay prepares login validation, not an attachment-upload or full recovery
certificate. Test users still require explicit organization-scoped membership and
real login/logout/denial verification. Password changes must be completed by the user.

## Browser uploads in the isolated acceptance stack

Append `acceptance-storage.compose.yml` after the identity overlay when testing
browser attachments. It publishes only the acceptance MinIO S3 endpoint on
`127.0.0.1:9300` and sets the API signing endpoint to `localhost:9300`.
The internal endpoint remains `minio:9000`; no console or database port is opened.
The smoke-only fresh overlay intentionally keeps infrastructure private; without
this upload overlay the inherited localhost:9000 signing address may point to the
main stack, not the acceptance bucket. Do not upload through that mismatched address.

Verify port9300 is free, validate the combined configuration with `config --quiet`,
then apply only `up -d --no-deps api minio` to `trade-fresh-acceptance`.
Supply the existing identity secrets only in process memory as above; preserve
Web sessions and all named volumes. This local HTTP endpoint is not a production
storage deployment or malware-scanning certificate.
