# 阶段二：私人教材与知识库

阶段二沿用原有用户、学习空间、CLI 和 Web。新增资料私有存储、远端 PDF 理解、可恢复任务、教材检索与引用。资料理解和向量生成全部调用用户配置的远端 API，框架不提取 PDF 正文、不解包 DOCX/EPUB、不做 OCR，也不运行本地 Embedding。

## 1. 配置支持文件的模型

现有聊天配置可以继续使用。文件功能需要新建专门的文件配置；不会把“兼容聊天接口”推断成“原生文件支持”。

| 类型 | CLI 选项 | 实际行为 |
|---|---|---|
| `openai_compatible` | 默认 | `/chat/completions`，不开放文件或向量能力 |
| `openai_files` | `--files` | 聊天 + Files 上传 + Responses 文件输入，只实际探测 PDF |
| `fake` | `--demo` | 固定操作系统教学演示，不支持文件 |
| `fake_files` | `--demo-files` | 固定资料演示，不读取上传内容；所有结果明确标注演示 |

```bash
source .venv/bin/activate
# 先 auth login；Key 可通过隐藏输入提供，避免写进命令历史。
study-agent provider add --name '我的文件模型' \
  --files --model '填写文件理解模型ID' \
  --base-url 'https://你的服务商/v1' \
  --accept-data-transfer
study-agent provider test PROVIDER_ID
study-agent provider capabilities PROVIDER_ID
```

原生适配器要求所选端点实现 `/chat/completions`、`/files`、`/responses` 和远端文件删除；只实现其中一部分的兼容端点可能无法通过检测。模型名称由用户提供，框架不绑定某个付费模型。

检测会实际调用聊天、严格 JSON，以及上传一份框架生成的随机标识 PDF，再要求远端读出文件中的标识。标识不放进提问文本；只有读回完全匹配才开启 `application/pdf`。检测后尝试删除测试文件，失败会显示保留提示。文件探测失败仍可保留已通过的聊天能力。DOCX、EPUB 和图片没有经过本适配器验证，当前禁用。

需要向量检索时，新建配置可增加 `--embedding-model '服务商的向量模型ID'`，或使用：

```bash
study-agent provider update PROVIDER_ID --embedding-model '向量模型ID'
study-agent provider test PROVIDER_ID
# 移除可选向量模型后也需重新检测
study-agent provider update PROVIDER_ID --clear-embedding-model
```

Embedding 使用同一个 Base URL 与用户 Key，实际调用 `/embeddings` 检查批次数量、索引、维度和有限数值。未通过时禁用向量功能，关键词检索仍可用。

## 2. 选择空间并上传

```bash
# 已有空间可以切换到已检测的文件模型，学习证据不清空。
study-agent space switch-provider SPACE_ID --provider PROVIDER_ID
study-agent space use SPACE_ID

study-agent material upload '/绝对路径/教材.pdf' \
  --accept-file-transfer --request-id book-upload-001
```

每次上传必须带 `--accept-file-transfer`，Web 每次也必须勾选授权。它意味着同意所选模型服务商接收文件、理解内容并可能收取费用。远端保存时间和删除后的日志／备份机制遵循服务商政策，框架不能替其保证立即物理擦除。

默认单文件上限 **20 MiB**，管理员可调整 `MATERIAL_MAX_BYTES`（最高 48 MiB）。默认最多处理 **20 个章节**，`MATERIAL_MAX_SECTIONS` 最高 40。限制用于控制资源和调用规模；不承诺货币预算硬上限。

框架校验文件名、扩展名、MIME、大小、PDF 头尾标识与主动内容特征；拒绝 JavaScript、启动动作和嵌入文件等明显特征。它是保守的元数据／字节特征检查，不是完整杀毒、格式完整性验证或正文解析。原文仅作为附件下载，不在网页执行。

上传返回资料 ID 与任务 ID，响应成功前文件元数据和持久任务已提交数据库。默认后台自动处理，无需手动运行 `job run` 或执行 SQL；理解成功后在同一事务发布章节、概念、可选向量和更新后的学习计划。网页会自动刷新所选资料详情、知识地图与计划。上传本身不等待所有远端理解完成，也不增加掌握度。重复使用相同上传键和相同内容返回同一资料；相同键对应不同文件或选项返回 409。已删除的上传键不会复用，需要使用新键重新上传。

## 3. 查看进度、失败恢复与重新索引

```bash
study-agent material list
study-agent material show MATERIAL_ID
study-agent job show JOB_ID
study-agent job wait JOB_ID --seconds 180
```

默认后台 worker 随服务启动，按持久任务队列依次执行：

```text
排队 → 远端上传 → 目录理解 → 按章节提取摘要、关键词与概念
     → 可选远端 Embedding → 校验并原子发布索引
```

每完成一步保存进度。服务重启后，未过期租约等待到期；过期任务从检查点恢复，已完成的章节不重复理解。每个远端步骤总时限 90 秒，租约 120 秒；自动恢复最多 `MATERIAL_JOB_ATTEMPTS` 次（默认 3）。普通模型错误会停止并等待手动重试，不会无界产生费用。

```bash
# 失败任务：沿用原版本、原授权和已保存的检查点
study-agent job retry FAILED_JOB_ID --request-id retry-001
# 返回新的任务 ID，可继续 job wait

# 取消排队／运行中的索引；已在途的远端请求可能仍完成
study-agent job cancel JOB_ID

# 取消后、换模型后或需要重新理解时，使用当前空间模型重新授权
study-agent material reindex MATERIAL_ID \
  --accept-file-transfer --request-id reindex-001
```

`reindex` 隐藏旧索引，全部成功后再替换，避免新旧结果混用；历史作答和掌握证据继续保留。模型输出不合法时不会发布半成品。任务的租约与资料代次检查会阻止已取消／已删除任务重新发布。

管理员可设置 `MATERIAL_WORKER_ENABLED=false`，通过 `study-agent job run JOB_ID` 手动运行一个任务。该命令同步等待，长文档可能超过 CLI HTTP 超时；超时后先 `job show` 确认状态，默认部署建议使用 worker + `job wait`。`job wait` 只查询状态，不主动开始远端任务。

## 4. 检索与引用教学

```bash
# 无向量也可用
study-agent material search '进程调度是什么' --mode keyword

# 上传时明确启用已检测的远端 Embedding
study-agent material upload '/绝对路径/教材.pdf' \
  --accept-file-transfer --embeddings --request-id vector-book-001
# 处理完成后
study-agent material search '内存管理' --mode embedding
```

- `keyword`：对远端生成的标题、摘要、关键词匹配，再由用户模型从候选中选择证据。返回 `keyword_llm_rerank`，明确属于非向量检索。
- `embedding`：远端生成查询向量，与同一配置指纹的已授权向量比较，再由用户模型精排。返回 `remote_embedding`。没有可用向量或能力时明确报错。
- `auto`：有匹配配置的远端向量时使用向量，否则使用关键词方式。不会调用本地模型。

每条结果包含真实资料 ID、文件名、章节、摘要、来源 ID 和定位可信状态。摘要由远端模型提取，仍可能有错。当前适配器无法验证页锚，服务器一律丢弃模型返回的页码，`locator_verified=false`；界面显示“页码未核实”，提供原文附件下载核对。

上传资料后，新的诊断和课堂先检索资料。讲解与每题的 `source_ids` 必须属于本次检索候选，服务端拒绝伪造、跨空间或已删除来源。网页与 CLI 均显示教材出处；阅览和索引只补充知识来源，掌握状态仍由原有 `rules_v1` 作答证据更新。

资料仍在处理、失败或查询没有相关证据时，默认停止新教学并提示补充资料。允许通用知识补充需要用户明确选择：

```bash
study-agent space knowledge-policy SPACE_ID --allow-general-knowledge
# 恢复严格教材策略
study-agent space knowledge-policy SPACE_ID --no-allow-general-knowledge
```

没有上传任何有效资料的空间继续使用 M1 的通用模型教学。通用内容保持未核实标记；已有课堂和诊断按历史保存，不自动重写。

## 5. 下载与删除

```bash
study-agent material download MATERIAL_ID --output '/新的本地路径/教材.pdf'
study-agent material remove MATERIAL_ID
# 删除返回远端清理任务；继续检查直到成功
study-agent job wait CLEANUP_JOB_ID --seconds 180
```

下载始终需要本人会话；CLI 以 0600 创建文件，不覆盖已有路径。删除立即移除本地原文、章节与向量，终止索引版本，新检索不再返回该资料。旧课堂和题目保留学习历史，但动态去掉已删除教材的可回查引用。

远端文件删除由独立持久任务执行；遇到服务商故障可重试，失败提示保留在资料列表。上传请求在删除后才返回的远端文件也会记录，并建立补充清理任务。清理任务不能取消。只有确认远端句柄已清理才隐藏删除墓碑；无法确认时会提示到服务商控制台核对。

跨模型重索引保留旧版本远端文件句柄，最终删除时一并清理；旧凭证仍被这些句柄使用时禁止删除。建议更换服务商时新建配置，保留旧配置直到清理完成。直接轮换原 Key／模型／地址会使旧指纹失效，框架不复制旧密钥；原文件可能需要在服务商控制台手动清理。

## 6. 可选 PostgreSQL pgvector

默认把远端向量保存为 JSON，并在候选集合上计算余弦相似度，适合个人规模，不需要额外依赖。pgvector 仅作为存储／距离计算扩展，不负责生成向量。

如需数据库向量检索：先在 PostgreSQL 主机安装 pgvector 扩展包，执行正式迁移，再初始化向量表，最后开启配置并重新索引资料：

```bash
.venv/bin/alembic -c backend/alembic.ini upgrade head
psql "$DATABASE_URL_FOR_PSQL" -f scripts/pgvector.sql
# .env 设置 PGVECTOR_ENABLED=true，重启服务
# 然后对需要向量检索的资料使用 reindex --embeddings
```

`DATABASE_URL_FOR_PSQL` 使用 `postgresql://...` libpq URL，不是 SQLAlchemy 的 `postgresql+psycopg://...`。初始化需要相应扩展权限；默认 Compose 的 PostgreSQL 镜像未包含 pgvector，需管理员选择已安装扩展的镜像（可通过 `POSTGRES_IMAGE` 替换）。设置开启但缺扩展／初始化表时任务失败，不能把降级伪装成 pgvector 成功。

开启后 JSON 仍保存远端向量，同时写入 `material_vectors` 的 `vector` 列；搜索在数据库按用户、空间、配置指纹与维度过滤后做余弦排序；删除章节通过外键级联删除向量。暂未建立 ANN 索引，不适合大规模语料吞吐声明。

## 7. 部署与验证边界

- Alembic `0002` 新增资料、章节、任务表，以及可选 Embedding 模型和通用知识授权；已有空间默认不授权通用补充。
- 原文位于 `MATERIAL_STORAGE_DIR/用户ID/空间ID/资料ID.bin`，文件名不会参与存储路径，原文文件权限 0600。备份需包含数据库、资料目录和独立保管的加密主密钥。
- Compose 新增 `material_data` 命名卷；多副本必须提供共享资料目录／对象存储方案和共享限流。SQLite 仅支持单进程开发。
- 源文件和模型摘要不进入调用日志。AgentRun 只记录模型、步骤、耗时、token／可得费用、错误码。
- 自动化测试使用独立 Fake 文件适配器和 HTTP 传输替身；真实 HTTP 联调仍使用明确标注的演示数据。未使用真实 BYOK 付费服务处理用户教材，不宣称真实服务商内容质量或账单验收通过。
- pgvector 初始化／查询代码已提供；本次未实际运行 vector 扩展，原生 pgvector 路径仍需部署环境验证。

原生接口依据：[官方文件输入文档](https://developers.openai.com/api/docs/guides/file-inputs)、[文件删除](https://developers.openai.com/api/reference/resources/files/methods/delete)、[Embedding API](https://developers.openai.com/api/reference/resources/embeddings/methods/create)。兼容服务商须自行满足并通过实际检测。

界面检查截图：[教材章节与检索出处（明确标注演示资料）](assets/m2-library.png)。
