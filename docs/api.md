# API 参考

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
| GET /study-spaces?include_archived=true | 管理本账号保留的空间，包括旧版已移除空间；不返回永久删除标记 |
| DELETE /study-spaces/{id} | 永久删除学习记录、课程、答题、教材原文与索引；取消索引，异步清理远端文件；不可恢复 |
| GET /study-spaces/deletion-jobs | 本账号已删除空间的远端清理状态；失败任务通过 /jobs/{id}/retry 重试 |
| GET /study-spaces/{id}/concepts · /profile | 课程 DAG / 当前证据状态 |
| POST /study-spaces/{id}/profile/rebuild | 从不可变事件重算 BKT 状态和计划 |
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

## 教材与任务

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

来源返回 source_id、document_id、study_space_id、filename、heading、summary、locator、locator_verified 和 is_demo。题目及课堂新增 source_ids/citations/grounding，不改变参考答案保护；被删除资料的引用在读取时过滤。当前定位页码一律 null、未核实。详细行为见 [私人教材指南](materials.md)。

删除学习空间会清空目标及模型关联，并按外键顺序移除学习内容、不可变事件、调用记录和教材分节（含 pgvector 镜像）。保留不含目标、答案、教材内容的最小空间、资料和任务标记，用于幂等拒绝重建、登记在途上传返回的远端句柄及清理重试；不提供恢复接口。普通学习事件仍禁止 SQL 更新/删除，仅当所属空间进入永久删除状态时允许清除事件。在途上传结束和远端文件清理完成前，禁止删除所需模型凭证。远端删除不代表能绕过供应商的保留政策。

## 自适应学习与复习

路径以下均位于 `/api/v1/study-spaces/{space_id}`，需要本人登录；不同用户或已删除空间返回 404。

| 方法／路径 | 输入／行为 |
|---|---|
| GET /algorithms | 双算法固定启用、实际库与参数版本、证据版本与校准状态 |
| GET /q-matrix | 知识点、题目映射及用途；不含答案或 rubric |
| GET /reviews | due／upcoming／unassessed 三组卡片、状态、due 与 as_of |
| POST /reviews/start | concept_id、idempotency_key；创建或恢复活动复习，201 |
| GET /reviews/{review_id} | 本空间会话、课堂、新题及已提交结果 |
| POST /reviews/{review_id}/submit | 与 attempts 相同请求与结果；题目必须属于该复习 |
| GET /report?days=7 | 支持 7／30；事件重放、分布、错误、完成／保持率、下一步 |

普通 `/attempts` 与复习提交增加可选 `memory_rating=again|hard|good|easy`。使用服务端提示或答错只能 Again；独立正确可选 Hard／Good／Easy。结果 `memory` 为 null（无可靠单概念证据）或实际 rating／reason／due／state。两个入口复用同一幂等摘要与事件唯一日志，重复不二次调度。课堂响应有 review_id、题目 purpose=review；阅读完成与全题提交共同形成任务完成事件。

版本变更而派生状态未重建返回 409 `state_rebuild_required`；不一致评分返回 422 `invalid_memory_rating`；尚未到期返回 `review_not_due`。维护标记存在时写请求返回 503 `maintenance`。离线参数发布和一次性清空不是公开 HTTP 端点，见 [维护说明](adaptive-learning.md)。


## 学习计划 Chat

以下路径均位于 `/api/v1/study-spaces/{space_id}`，使用现有登录 Cookie，并检查空间归属。新接口的静态响应模型见 OpenAPI。

| 方法／路径 | 行为 |
|---|---|
| GET /chat/turns?before=CURSOR&limit=30 | 稳定分页，limit为1–100，返回items与next_cursor；含未完成回合 |
| POST /chat/turns | content（1–4000字符）、idempotency_key、retry=false；明确需求自动应用 |
| GET /chat/turns/{turn_id} | 权威处理状态、回复、差异和计划快照 |
| GET /plan/revisions?before=CURSOR&limit=30 | 只读需求修订、前后快照和变更原因 |
| GET /lessons/paused | 暂存课堂，原题与作答继续保留 |
| POST /lessons/{lesson_id}/resume | IdempotentRequest；恢复原课堂，活动冲突409 |

回合status为processing／completed／failed／conflict／cancelled；outcome区分applied／not_changed／clarification_needed等权威结果。新回合完成201，已有结果200，处理中202。每空间一个活动回合，租约180秒；重试使用相同idempotency_key／content并设置retry=true。公开结果返回该幂等标识，以支持刷新后重试；不返回模型凭证和提示词。

GET plan增加intent_version、intent和stages；version为policy_v3。策略版本与需求版本分别管理。LLM路线与偏好持久保存，动态next_action在作答／查询时结合最新BKT、FSRS与先修关系计算。

可能错误包括chat_busy、chat_interrupted、chat_context_changed、invalid_plan_change、invalid_cursor和原有unauthenticated／not_found／maintenance。失败结果不代表计划已生效，客户端应读取status／outcome／error_message，而非仅根据HTTP200判断应用成功。

## 每日任务、周报与 AI 分析

新接口均有明确响应模型，归属由会话推导，不接受客户端user_id；跨账号404，未登录401。写接口使用 `idempotency_key`。空间前缀 `S=/study-spaces/{space_id}`。

| 方法／路径 | 行为 |
|---|---|
| GET S/daily-plans/today | 只读今日计划；未生成返回plan=null与原因 |
| POST S/daily-plans/refresh | 用现有数据协调今天，无模型调用 |
| GET S/tasks | 列表，支持status过滤，最多100项 |
| POST S/tasks/{id}/start | 恢复同一课堂／诊断，返回TaskStartResponse及关联题ID |
| POST S/tasks/{id}/complete | 核对真实阅读／答题条件，不伪造完成 |
| POST S/tasks/{id}/skip · /postpone | 仅修改待办；改期日期由服务端计算 |
| GET S/suggestions | 读取偏离建议 |
| POST S/suggestions/{id}/accept · /skip | 重验来源版本后处理 |
| GET /inbox · /inbox/unread-count | 本账号分页消息／总未读数 |
| POST /inbox/{id}/read | 幂等标记已读 |
| GET S/weekly-summaries | 持久自然周报分页 |
| GET S/weekly-summaries/current | 当前周即时预览，无写入和模型调用 |
| GET S/weekly-summaries/{id} | 读取持久快照 |
| POST S/weekly-summaries/refresh | 生成／读取上一完整自然周，无模型调用 |
| GET /activity-jobs | 本账号周期作业分页，不返回内部租约 |
| POST /activity-jobs/{id}/retry | 仅死信作业可手动重试，非付费任务 |
| POST S/analyses | 明确申请AI分析，201结果／202处理中 |
| GET S/analyses · /analyses | 空间／账号的分析分页 |
| GET S/analyses/{id} | 状态／结果／保留及实际Token／retry_allowed |
| GET /analysis-usage | 账号UTC日跨空间共享的手动 AI 分析配额；不含其他模型任务费用 |

分页接口支持 `cursor`／`limit`（默认30，最大100），返回 `{items,next_cursor}`。分析请求包含 `source_kind=daily_plan|weekly_summary`、`source_id`、`idempotency_key`、可选 `retry_of`。同键内容不同409，来源不属于当前空间404，达到分析配额429。未知模型消耗保守占用，不按零退款；失败只有用户新发起尝试才重试。独立SPA页面 `/login`、`/register` 支持直达刷新，未知 API 路径仍404。

## 已批改试卷诊断

前缀 `/api/v1/study-spaces/{space_id}/exam-diagnostics`，全部接口要求账号与空间归属。GET `/capabilities` 返回当前已验证格式和限制；POST 根路径创建附件清单草稿；PUT `/{id}/attachments/{attachment_id}` 流式上传原文件；POST `/{id}/start` 携带本次传输授权并返回 202。GET 根路径支持 before／limit 分页，GET `/{id}` 读取状态与报告，GET `/{id}/attachments/{attachment_id}/download` 下载原卷。POST `/{id}/retry` 恢复失败阶段或重试远端清理，POST `/{id}/cancel` 取消未发布任务；PATCH `/{id}/questions/{question_id}` 携带 expected_version 和幂等键核对未入库题；DELETE `/{id}/draft` 仅丢弃未开始草稿。

相同键不同内容 409，越权 404，格式／分值／授权错误 422；文件超限 413。实际 schema 见 OpenAPI。报告含独立的有效证据数和 before／after，在线学习报告另含 external_imports，导入不计为在线答题或复习。详见[使用说明](exam-diagnostics.md)。
