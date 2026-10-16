# M1 / M2 API

前缀 `/api/v1`。运行服务后访问 `/docs`、`/redoc`、`/openapi.json`；静态快照 `docs/openapi.json`。会话采用 HttpOnly Cookie，所有学习对象需要登录。写接口校验 Origin。

| 方法 / 路径 | 行为 |
|---|---|
| POST /auth/register · /auth/login | 创建账号 / 建立会话，username + password |
| POST /auth/logout · GET /auth/me | 撤销当前会话 / 当前用户 |
| GET /config | 是否允许显式离线演示 |
| GET /providers · POST /providers | 模型列表 / 新配置，响应永不含 API Key |
| PATCH /providers/{id} · DELETE /providers/{id} | 更新密钥 / 模型等，更新后重新检测；删除未使用配置 |
| POST /providers/{id}/test | 用户授权的真实聊天与结构化输出检测，记录 run_id |
| GET /providers/{id}/capabilities | 检测结果，未验证功能均关闭 |
| POST /study-spaces · GET /study-spaces | 原子初始化候选课程 / 空间列表 |
| GET /study-spaces/{id} · PATCH /study-spaces/{id} | 查看目标 / 切换已检测模型，不删除历史 |
| GET /study-spaces/{id}/concepts · /profile | 课程 DAG / 当前证据状态 |
| POST /study-spaces/{id}/profile/rebuild | 从不可变事件重算 rules_v1 和计划 |
| POST /study-spaces/{id}/diagnostics | 生成并持久化 5–10 题；重复调用返回原题及作答状态 |
| GET /study-spaces/{id}/next-action · /plan | 确定性下一动作与持久化计划，包含依据事件 ID |
| POST /study-spaces/{id}/lessons | 按下一动作生成课堂 / 恢复未完成课堂 |
| GET /study-spaces/{id}/lessons/current | 最新课堂与作答状态，页面重载可继续 |
| POST /study-spaces/{id}/lessons/{lesson_id}/complete | 记录阅读，不增加掌握度 |
| POST /study-spaces/{id}/items/{item_id}/hint | 生成引导提示，记录服务端辅助事件 |
| POST /study-spaces/{id}/attempts | 判分、追加证据、重算状态和计划，原子提交 |
| GET /study-spaces/{id}/events · /runs | 本空间事件 / 最近 100 条脱敏模型调用记录 |

初始化、课堂生成、阅读完成、提示和作答使用请求体 `idempotency_key`（1–100 位字母数字、下划线、短横线）。作答还需 `item_id`、`answer`，可传 `assistance_level`、`duration_seconds`。同题首次有效提交固定，不能用新键刷掌握；每个空间中的事件键不可复用。诊断生成以空间唯一批次幂等，不需要额外键。

题目在作答前不返回答案或判分 rubric；本人已作答后，响应可包含参考答案与反馈。评分参考答案是模型生成的，不代表外部权威核验。

统一领域错误：`{"error":{"code":"...","message":"..."},"request_id":"..."}`。输入验证响应仅包含字段位置与类型，不回显密码、Key 或敏感原文。常见状态码：401 未登录、404 无权访问或不存在、409 幂等冲突 / 已作答、422 配置和输入问题、429 限流、502 模型失败。

模型错误代码包括 `invalid_api_key`、`provider_timeout`、`rate_limited`、`provider_unavailable`、`invalid_structured_output`、`invalid_question_mapping`、`duplicate_question`、`capability_not_supported`。有限重试失败后由用户再次发起，历史数据不清空。

review 与 notifications 端点未注册，属于 M3 / M4。


## M2 资料与任务

| 方法 / 路径 | 行为 |
|---|---|
| POST /study-spaces/{id}/materials | PDF 原始二进制上传，202 返回资料与任务 ID |
| GET /study-spaces/{id}/materials | 资料与待清理墓碑列表 |
| GET /study-spaces/{id}/materials/{asset_id} | 资料状态、章节、关键词和概念 |
| GET /study-spaces/{id}/materials/{asset_id}/download | 本人鉴权后的原始附件 |
| POST /study-spaces/{id}/materials/{asset_id}/reindex | 重新授权，使用当前空间模型重新索引 |
| DELETE /study-spaces/{id}/materials/{asset_id} | 立即移除本地原文与索引，返回远端清理任务 |
| POST /study-spaces/{id}/materials/search | query、mode=auto/keyword/embedding、limit（1–10） |
| GET /jobs/{job_id} | 本人的任务状态、阶段、进度、错误 |
| POST /jobs/{job_id}/run | 手动处理 queued／过期 leased 任务 |
| POST /jobs/{job_id}/cancel | 取消索引（清理不可取消） |
| POST /jobs/{job_id}/retry | 对失败任务创建保留检查点的新任务，需 idempotency_key |

上传使用原始 PDF 请求体，`Content-Type: application/pdf`；请求头 `X-Filename` 为 URL 编码文件名，`Idempotency-Key` 为幂等键，`X-File-Consent: true` 表示本次文件处理授权，可选 `X-Use-Embeddings: true` 同意远端向量生成。不是 multipart。重索引请求体为 `{"idempotency_key":"...","consent":true,"use_embeddings":false}`。

ProviderCreate 新增 provider_type=`openai_files` / `fake_files` 和可选 embedding_model。改动后重新检测；文件与向量分别返回实际能力。空间 PATCH 可更新 `allow_general_knowledge`（默认 false），也可仅切换 provider_id。

任务状态为 queued/running/succeeded/failed/cancelled。202 仅表示已接受，处理结果查 job；常见错误包括 file_consent_required、file_too_large（413）、unsupported_file_type、unsafe_file、invalid_idempotency_key、provider_config_changed、insufficient_material_evidence、invalid_citation、remote_cleanup_required。失败任务可能返回 HTTP 200 查询成功且 status=failed，调用方须检查状态字段。

来源返回 source_id、document_id、study_space_id、filename、heading、summary、locator、locator_verified 和 is_demo。题目及课堂新增 source_ids/citations/grounding，不改变参考答案保护；被删除资料的引用在读取时过滤。当前定位页码一律 null、未核实。详细行为见 [M2 文档](m2-materials.md)。
