# 技术与依赖基线核对

## 当前历史缺口判定（2026-09-09）

本轮完整重读0035迁移、共享Button实现/README/第三方通知及两个实际使用方；
只读查询当前验收 PostgreSQL，版本为20260908_0035，pg_trgm1.6存在，
ix_companies_name_trgm_active、ix_companies_normalized_trgm_active及
ix_companies_name_fts_active均 indisvalid=true、indisready=true，定义精确包含
GIN、相应trigram/全文表达式及deleted_at IS NULL条件。没有重建索引或修改业务表。
结合本记录既有查询计划/迁移证据，下方第1项“未找到pg_trgm”以及“仍0034未部署”
不再是当前缺口。本次索引存在性核验不是新的6001行基准或所有查询性能证明。

共享Button源于已记录的shadcn/ui适配，CursorPageControls和FundingEstimate完整代码
实际导入并渲染它，第三方通知保存MIT原文与修改说明；下方第2项“未找到接入”
不再是当前缺口。未要求或声称所有原生控件迁移为同一组件。
第4项中的全Web重复DTO问题由TASK005_ACCEPTANCE完整声明/边界审计另有证据；
跨模块写入由MODULE_OWNERSHIP和ADR030-034记录修正及运行证据，不以本次组件审阅
取代全部所有权审计。第3项需保留本机使用与未来镜像分发/公开托管的许可边界。
本次只更新证据导航，不豁免完整指南、远程CI或生产配置要求。

## 2026-09-09 服务端许可补充

实际本机版本Redis8.2.9、MinIO RELEASE.2025-09-07T16-13-09Z、PostgreSQL18.6已核对。
对应官方版本许可文本保存于docs/licenses，逐字符一致性和本机SHA-256验证通过。
Redis8是RSALv2/SSPLv1/AGPLv3三选一，MinIO服务端是AGPLv3，不得分别误作旧版BSD或
PythonSDK的Apache许可。已按AGPL运行/网络交互/修改/分发相关条款记录本机边界与
后续交付义务；未认定仅凭容器隔离就免除许可要求。详见docs/licenses/README.md。
这部分推进下方第3项服务端许可缺口，不是完整传递依赖SBOM、源码分发包或法律证书。

## 2026-09-08共享组件基线补充

已从官方registry核实并适配shadcn/ui Button，MIT原文和修改说明保存在packages/ui。
以CVA0.7.1（Apache-2.0）选择现有三种按钮CSS，保留React原生属性/ref；不引入未使用的
Slot、尺寸预设、CLI或整套主题。CursorPageControls与FundingEstimate真实使用共享包；
未批量替换其他控件，也不宣称全站已完成组件迁移。两个新增依赖的安装许可证已读取并
保留，Web容器显式携带这些通知。锁文件只增加共享引用及CVA/clsx，没有升级既有依赖。

全前端类型检查、ESLint、262项Vitest、Next生产构建通过。浏览器与容器验证另见最新
V1_STATUS。本机pnpm提示既有openapi-typescript7.13.0声明TypeScript ^5.x而本项目为6.0.3；
实际类型/生成契约检查不等于上游已承诺此组合兼容，此风险保留，不顺手升级或降级。
以下初次审计为历史快照，上述补充取代其中“未找到shadcn接入”的当前状态。

核对日期：2026-09-08。依据实施指南第6—8节及实际清单、锁文件和本机安装元数据。
本记录不是发布证书、完整软件物料清单或法律合规意见，未升级任何依赖。

## 已核对的版本

以下 Python 安装版本与 `uv.lock` 的对应包版本一致：

| 包                | 版本    | 安装包声明的许可证 |
| ----------------- | ------- | ------------------ |
| FastAPI           | 0.141.1 | MIT                |
| Pydantic          | 2.13.5  | MIT                |
| SQLAlchemy        | 2.0.52  | MIT                |
| Alembic           | 1.19.1  | MIT                |
| Celery            | 5.6.3   | BSD-3-Clause       |
| psycopg           | 3.3.5   | LGPL-3.0-only      |
| MinIO Python SDK  | 7.2.20  | Apache-2.0         |
| PyJWT             | 2.13.0  | MIT                |
| Uvicorn           | 0.52.4  | BSD-3-Clause       |
| pydantic-settings | 2.15.0  | MIT                |

本机 Web 直接依赖/开发依赖元数据共检查22包。Next16.3.4、React/ReactDOM19.2.8、
TanStack Query5.102.8、Logto Next4.2.10、React Hook Form7.87.0、Zod4.5.4、
Tailwind4.3.3、TypeScript6.0.3、Playwright1.62.1、Vitest4.1.11均位于清单声明范围内。
这22包中TypeScript/Playwright声明Apache-2.0，其余声明MIT。此项为安装元数据检查，
不是对所有传递依赖许可证文本、分发通知或供应链签名的全面核验。

根清单锁定pnpm11.19.0；Python要求3.12稳定线。API/Worker Dockerfile用uv0.12.3，
从锁文件执行frozen安装；Web从pnpm锁文件frozen安装并使用Node24.19.0镜像。
上述抽查包没有预发布版本后缀；尚未据此证明整个依赖图不存在预发布或安全公告。

## 服务边界与部署事实

Compose声明业务PostgreSQL18、Redis8.2和带发布时间标签的MinIO；Logto独立使用
1.43.0及其PostgreSQL17，不是业务数据库降级。API/Worker共享后端包但独立进程；
Web使用生成客户端，Worker数据库事实及事务端口的具体证明见功能验收记录。
Web容器采用非root用户；API/Worker Dockerfile未声明非root用户。

部分镜像采用稳定线标签而非digest，因此标签可能随时间变化，不能称为完全字节级可复现。
本机已验收镜像身份另见V1_STATUS；本次未拉取镜像、重建、改动卷或重跑恢复演练。
CI声明frozen安装、格式/lint/typecheck/测试、MinIO准备、Playwright、构建及独立容器冒烟；
尚未在GitHub执行，不能宣称托管CI已绿。

## 明确尚未满足或待证明的事项

1. 指南ADR007明确使用PostgreSQL全文检索和pg_trgm。现有CompanyAssistantQueries使用
   `icontains(autoescape=True)`与`to_tsvector/simple + plainto_tsquery`；当前应用和迁移
   搜索未找到pg_trgm、trigram索引或similarity实现。不能把全文检索已有等同两者均完成。
   后续需落实相应检索能力、组织过滤、索引/查询计划及迁移验证，不自动改用外部搜索引擎。
2. 指南第7节指定Tailwind和shadcn/ui。当前Web清单/组件及packages/ui未找到shadcn/Radix
   接入，packages/ui目前仅有TypeScript基础包。需要核对并落实这一交付要求；不以现有
   自建CSS组件默认为已接受架构偏离，不为补名称而无意义安装未使用依赖。
3. 本次许可证证据来自包元数据及已有Logto/数据库文档。MinIO SDK许可证不能代替MinIO
   服务端许可证；Redis镜像、运行时/系统库、其他传递依赖和源码分发义务尚需逐项核对。
   未验证的许可证义务不能用“不修改源码”一概豁免。
4. 此记录没有证明全部跨模块写入都经所有者端口，或全Web没有手写重复DTO。需要独立
   源码审计；目录名、依赖清单或现有测试总数都不是这两项的完整证据。

本次只补充核对记录，不修改施工目标、接受新架构例外、删除原始证据或改变业务规则。

## pg_trgm后续实施补记

0035已在源码增加pg_trgm及三个活跃公司GIN索引，分别服务公司名、规范化公司名的
字面子串查询和simple全文查询。移除非空name上的多余coalesce以匹配索引，不改搜索
语义、租户条件或数量上限。临时数据库空库/带商业记录0034副本升级、两轮回退再升级、
全表值保留及Alembic无漂移均已验证；索引回退不删除可能共享的扩展。

6001行合成公司基准在批量插入后仅ANALYZE时曾选择顺序扫描；正常VACUUM ANALYZE
清理GIN待整理数据后，真实应用查询计划选用两个名称搜索索引及全文索引。
没有关闭顺序扫描或强制索引。该证据仅涵盖选择性查询和此维护状态，不是整体p95认证。
实际验收环境仍0034；最新实际备份副本演练、部署/启动和部署后验收尚未完成。

同日后续：新的CurrentUser加密备份已恢复到独立trade_migration_0035_acceptance，
原库/副本45表指纹一致，副本升级0035后45表指纹仍一致、Alembic无漂移、pg_trgm1.6
及三索引存在。这关闭上述实际备份副本迁移演练待办，不替代实际源库部署及启动验收。
