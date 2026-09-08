# 本机运行组件许可复核

核对日期：2026-09-09。此记录针对本机 V1 验收，不是全部依赖的法律合规证书。
未更换软件、升级版本、购买许可、改动运行组件源码或发布镜像。

## 当前组件与官方依据

| 组件         | 实际运行版本                                                                 | 许可事实与官方文本                                                                                                                                              |
| ------------ | ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Redis        | 8.2.9                                                                        | [该版本 LICENSE.txt](https://github.com/redis/redis/blob/8.2.9/LICENSE.txt)：RSALv2、SSPLv1、AGPLv3 三选一；不能沿用 Redis 7.2 及以前的 BSD 结论                |
| MinIO 服务端 | RELEASE.2025-09-07T16-13-09Z，commit07c3a429bfed433e49018cb0f78a52145d4bedeb | [该版本 LICENSE](https://github.com/minio/minio/blob/RELEASE.2025-09-07T16-13-09Z/LICENSE)：AGPLv3，与运行程序版本输出一致；不是 MinIO Python SDK 的 Apache-2.0 |
| PostgreSQL   | 18.6，Debian18.6-1.pgdg12+2                                                  | [REL_18_6 COPYRIGHT](https://github.com/postgres/postgres/blob/REL_18_6/COPYRIGHT)：允许使用、复制、修改及分发，复制时保留规定版权和免责文本                    |

Redis/MinIO/PostgreSQL版本来自当前trade-fresh-acceptance容器中各程序的只读版本命令。
原Compose使用redis:8.2-alpine和postgres:18-bookworm浮动补丁标签；本记录不证明标签永久
解析到此版本，也不是对应镜像完整构建来源或供应链签名证明。

## 已审查的使用边界

读取Redis许可总说明、PostgreSQL完整版权文本及AGPLv3第0、2、4、5、6、13条相关内容。
AGPL第2条明确允许运行未修改程序；第0条区分网络交互与传递副本，第13条要求修改版本
向远程交互用户提供相应源码。第4—6条规定复制/修改/分发时的通知及相应源码义务；
第5条讨论独立聚合，不支持把所有相邻服务自动认定为同一派生作品，也不支持仅凭不同
容器就宣称一定无义务。

本机使用现成服务镜像，API通过协议访问，没有在本轮复制Redis/MinIO服务端代码到业务
应用。针对未修改本机运行，AGPL提供了明确的运行许可路径；本记录没有替用户选择商业
许可、承诺对外服务模式，或认定所有组合/分发情形均合规。Redis其他许可选项不能混用
来规避各自限制；如拟向第三方提供Redis本身的功能，需按实际所选许可重新审查。

在打包交付镜像、修改这些组件、提供公开服务或采用新部署模式前，必须另行落实完整
对应源码、版权/许可通知、适用的源码获取方式及所有传递依赖义务。此目录只有许可文本，
不是Corresponding Source，也不能单独满足对象代码分发要求。复杂分发边界应交法律
专业人员确认。未审查的系统库、全部传递依赖与完整软件物料清单仍不由本记录关闭。

## 保存的官方文本

三份文件通过官方仓库指定版本获取。写入后逐字符比较与获取文本完全一致，未修改许可
正文；下列SHA-256标识本机保存的文本，不是运行二进制摘要。

- REDIS-8.2.9-LICENSE.txt：4A0E416B9537688F30DFE69DDACEB2CA64D96B7DF02A0A6760D376890DDC4E40
- MINIO-2025-09-07-LICENSE.txt：0D96A4FF68AD6D4B6F1F30F713B18D5184912BA8DD389F86AA7710DB079ABCB0
- POSTGRESQL-18.6-COPYRIGHT.txt：3D6AF92FF8A4C2CDF69AFB1CF44EDEA727922F5CD0CF8B5F72B11CDECAC8FDFD

镜像常见许可目录检索未找到Redis许可文本，不等同于认定整个镜像不含通知；官方版本
文本现已独立保存。其他SDK、Logto及共享UI的已有核对见BASELINE_AUDIT和各模块记录。

## API镜像内Python依赖补充

API-PYTHON-INVENTORY-20260909.json记录本次实际API镜像的38个已安装distribution，
其中37个第三方包均有许可声明，元数据列出的通知文件实际存在。本项目自己的
trade-workbench-api未声明公开许可证；没有擅自为用户代码新增开源授权。
这份清单是安装元数据和文件存在性检查，不是逐文件法律审计或全部native库清单。

特别保留psycopg/psycopg-binary3.3.5的LGPL-3.0-only、certifi的MPL-2.0、greenlet的
MIT AND PSF-2.0及cryptography的Apache-2.0 OR BSD-3-Clause区别。已阅读psycopg随包
LGPL文本中的组合程序/通知/重新链接条款，不能把未修改库自动当作没有分发义务。
uvloop同时携带MIT/Apache文本；PyCryptodome文本区分原PyCrypto公共领域部分与新增
BSD-2-Clause贡献，不能仅依据一个简化的元数据字符串丢弃通知。未替换这些依赖。
镜像实际交付前，还需核对被打包native库、通知展示和适用源码/重新链接要求。
