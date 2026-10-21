# Planning Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在学习空间内提供持久 Chat，明确需求自动更新真实计划、展示前后差异，并保留原有学习证据。

**Architecture:** LLM 返回受限的需求补丁、阶段路线和自然语言回复；服务端校验后原子发布版本化需求与计划。短事务分别负责认领和发布，模型等待在事务外；动态推荐继续使用强制 BKT＋FSRS。Web 复用同一后端，CLI 现有计划／学习命令同步受益。

**Tech Stack:** 现有 Python 3.12／FastAPI／SQLAlchemy／Alembic、SQLite／PostgreSQL、Pydantic、BYOK Provider Adapter、React 19／Vite、原生 pyBKT 与 py-fsrs；不新增产品依赖。

**Spec:** [用户已确认的设计](../specs/2026-10-19-planning-chat-design.md)。设计于 2026-10-19 获用户确认；本实施计划已获确认并实现，验收见 docs/acceptance.md 的学习计划 Chat 章节。沿用本会话已选择的 Native 执行方式，逐项实现后进行一次独立整体验收审查。

## Global Constraints

- “需求明确时自动应用，并展示变更前后”，不再增加逐次“应用计划”按钮。
- “每个空间强制使用原生 pyBKT＋FSRS；复用所选 BYOK 模型与数据传输授权；PDF 继续使用现有原生模型接口”。
- “本次不清空学习数据，不恢复后台正式服务，不做真实付费模型测试。”临时演示服务器验证结束后关闭。
- “聊天记录本身不作为掌握或回忆证据。”既有事件／作答／卡片／日志不因聊天改写；新增概念为 unknown／unassessed。
- 用户消息 1–4000 字符，回复最多 8000；历史页默认30／最多100；模型上下文最多最近20个成功／澄清回合，总历史文本24000字符，剔除最旧完整回合。
- 路线最多12阶段，每阶段最多30个知识点，单回合最多新增12个节点；既有 key 不改名、不删除；图必须为 DAG。
- 每空间仅一个 processing 回合；认领租约180秒，发布核对随机 token；模型总时限90秒，沿用既有适配器重试和限流。
- 数据库 Session 只由其所属线程使用；模型等待期间不持有用户锁或 SQLite 应用写锁。
- 原工作区包含未提交 M2／M3 代码，禁止 reset／clean／覆盖。执行前使用 using-git-worktrees 核对隔离；可在当前 checkout 新建 `codex/planning-chat` 分支以保留全部改动。不可仅复制 HEAD 丢掉工作区依赖。
- 每项按 RED→GREEN 验证。提交仅限可明确归属于本任务的文件／改动；若与既存修改无法安全拆开，记录理由并保留完整 diff，不使用 `git add .`。

## Review Focus

1. 长模型等待、发布时用户行锁等待与同一事件循环的作答／教材任务并发，不得冻结健康检查或持有跨线程 Session；任务6、7用单 ASGI 循环及真实 PostgreSQL 验证。
2. 租约到期后旧调用迟到、相同内容不同键、重试同时到达：只有当前认领能发布，一个回合不能产生两次需求版本；任务6、7验证。
3. 模型等待期间教材新增节点、切换模型、其他计划更新：旧上下文不能覆盖新数据；同时期作答应保留并用最新能力调度；任务7验证。
4. 修改预算／讲解风格与修改当前内容需要不同课堂处理；暂存不能伪装完成，旧页面迟到作答仍须只计一次真实证据；任务3、5验证。
5. 用户登出、空间归档／删除发生在模型调用后：迟到响应不能重建聊天、计划、学习审计或其他用户页面；任务6–8验证。

---

## 文件分工与共享类型

| 文件 | 职责 |
|---|---|
| `backend/app/schemas/chat.py` | 请求、LLM 决策、公开回合／差异／历史响应与字段约束 |
| `backend/app/chat/contracts.py` | 不可变 ProviderSnapshot、PreparedTurn、ModelCallResult、TurnResult |
| `backend/app/chat/context.py` | 空间内有限上下文、脱敏、概念／配置指纹 |
| `backend/app/chat/turns.py` | 自有 Session 的短事务、认领／租约、历史和原子发布 |
| `backend/app/chat/service.py` | 异步三阶段编排，模型调用与短事务衔接 |
| `backend/app/chat/application.py` | 白名单需求应用、节点追加、版本／差异与计划快照 |
| `backend/app/planning/intent.py` | 默认意图、范围／前置闭包、重点、路线与计划投影 |
| `backend/app/providers/invocation.py` | 无 ORM 的结构化调用与统一错误／用量结果 |
| `backend/app/teaching/lifecycle.py` | 暂存、恢复、活动课堂冲突检查 |
| `backend/app/api/chat.py` | 分页历史、发送／重试、回合与计划修订查询 |
| `frontend/src/PlanningChat.jsx` | 对话、权威变更卡、当前路线与暂存课堂入口 |
| `frontend/src/planningChatState.js` | 回合恢复、幂等发送、账号／空间失效与键盘行为 |

`RequirementPatch` 只接受 goal、daily_minutes、target_date、expected_level、included_concept_ids、priority_concept_ids、deferred_concept_ids、teaching_preferences、learner_notes。现有空间字段沿用 SpaceCreate 范围；重点／范围列表最多60项，偏好与自述各最多2000字符。未提供表示保留；target_date 显式 null 表示清除；included_concept_ids=null 表示全部范围，显式空列表无效。

`ChatDecision`：kind=reply|clarify|update_plan、reply、patch、added_concepts、stages、interrupt_current=false、reason。reply／clarify 不允许携带写计划字段；update_plan 必须有 reason 与实际变化。`PlanStage` 包含 title、objective、concept_ids、suggested_sessions（1–60）。节点复用领域 KnowledgeConcept，合并后验证完整图，不强制将既存教材节点重新解析为仅模型生成节点。

`PreparedTurn` 为 frozen dataclass：turn_id、space_id、user_id、session_hash、lease_token、intent_version、concept_fingerprint、provider_snapshot、task。ProviderSnapshot 包含 id、user_id、provider_type、base_url、chat_model、embedding_model、encrypted_api_key、timeout_seconds、tested、capabilities 和 fingerprint；只在内存内供构造适配器，不能序列化至公开结果／上下文。`TurnResult` 含 http_status 与经 ChatTurnResponse 验证的响应。

`ChatTurnResponse` 至少包含 id、study_space_id、content、reply（未生成时null）、status、outcome（处理中null，否则 applied|not_changed|clarification_needed|failed|conflict|cancelled）、changes、revision_id、plan、retry_allowed、error_code、error_message、created_at。changes 的每项包含 field、before、after、reason；公开阶段路线／需求快照均由响应子模型校验。`ChatTurnPage`／`PlanRevisionPage` 统一返回 items、next_cursor；cursor 为经长度校验的 base64url 编码 `(created_at,id)`，不授予跨空间读取权限。

## Task 1：数据、请求／响应契约与非破坏迁移

**Files:** 新建 `schemas/chat.py`、`chat/{__init__,contracts}.py`、`migrations/versions/0005_planning_chat.py`、`tests/test_chat_contracts.py`；修改 `db/models.py`、`tests/test_migrations.py`。

**Interfaces:** ORM `ChatTurn`、`LearningIntent`、`PlanRevision`；Lesson.status 默认／server_default=active。ChatTurn 的 `(space_id,idempotency_key)` 唯一、nullable active_space_id 唯一、用户／空间复合外键；PlanRevision 唯一 `(space_id,version)` 和 turn_id，引用对应回合。LearningIntent 每空间唯一，version 默认0。ChatTurn 含可空 provider_id／agent_run_id 与纯结果 JSON，完成或失败释放 active_space_id。

- [x] 写 `test_chat_limits_and_patch_whitelist`、`test_reply_cannot_smuggle_plan_changes`、`test_chat_owner_and_active_turn_constraints`；断言长度边界、显式 null／缺省、extra=forbid、错误空间归属、重复认领／修订被拒绝。
  ```python
  assert ChatSend(content="每天15分钟", idempotency_key="one").retry is False
  with pytest.raises(ValidationError): ChatSend(content="x" * 4001, idempotency_key="one")
  ```
- [x] 运行 `.venv/bin/pytest backend/tests/test_chat_contracts.py -q`，确认缺少契约而失败；新增带既存0004账号／空间／课堂数据的升级测试，确认当前无0005而失败。
- [x] 实现上述模型和 Pydantic 契约；迁移只建表／加列，不触发模型、BKT 重放或数据删除；提供逆向依赖顺序。
- [x] 运行 `.venv/bin/pytest backend/tests/test_chat_contracts.py backend/tests/test_migrations.py -q`，预期全部通过；Alembic metadata check 无漂移，0004既存数据前后相同。
- [ ] 审阅迁移／约束和 diff，按 Global Constraints 提交或记录未拆提交理由。

## Task 2：持久需求进入推荐、计划与新课堂

**Files:** 新建 `planning/intent.py`、`tests/test_planning_intent.py`；修改 `planning/policy.py`、`core/orchestrator.py`、`api/spaces.py`、`teaching/lessons.py`、`reviews/sessions.py`、`tests/test_adaptive_policy.py`。

**Interfaces:** `read_intent(db, space) -> dict` 返回默认／持久意图；`effective_scope(concepts: list[dict], intent: dict) -> dict` 返回 included_ids、required_prerequisites、explanations；`plan_view(db, space, *, now=None) -> dict` 是 GET plan 与 save_plan 的共同投影。choose_action 增加可选 keyword `intent=None`，原调用兼容。

- [x] 写 `test_default_intent_preserves_existing_choices`、`test_focus_keeps_necessary_prerequisites`、`test_deferred_cards_keep_due_but_do_not_drive_next_task`、`test_answer_replan_preserves_roadmap_and_preferences`。断言新旧默认动作／概念选择相同、重点前置未掌握先补前置、既有 FSRS 卡片／日志字节不变、保存计划不丢阶段路线；新策略统一声明 policy_v3，更新旧测试中精确版本断言，不放宽行为断言。
- [x] 运行 `.venv/bin/pytest backend/tests/test_planning_intent.py -q`，预期缺少意图接口而失败。
- [x] 实现范围闭包与有界重点加分：按 priority_concept_ids 找到首个尚未掌握或到期的重点，它及尚需学习的前置闭包获得 score_breakdown.user_priority=40，其余0；保留原有能力／到期／重要性分项与先修硬过滤。超出当前范围的卡片仅在复习列表增加 in_current_scope=false，不改原生记忆状态。
- [x] 将需求版本、偏好和 LLM 路线投影至 plan；教学任务加入 intent、teaching_preferences、learner_notes，但不发送其他空间数据。实际顺序偏离路线时返回依据；空需求不改变既有请求语义。
- [ ] 运行 `.venv/bin/pytest backend/tests/test_planning_intent.py backend/tests/test_adaptive_policy.py backend/tests/test_learning_report.py backend/tests/test_cli.py -q`，预期全部通过；审阅并按约束提交。

## Task 3：课堂／复习的暂存与恢复

**Files:** 新建 `teaching/lifecycle.py`、`tests/test_lesson_pause.py`；修改 `teaching/{lessons,presentation,attempts}.py`、`api/learning.py`、`reviews/sessions.py`。

**Interfaces:** `pause_current_lesson(db, space, *, reason: str, turn_id: str) -> str | None`；`resume_lesson(db, space, lesson_id: str, request_key: str) -> dict`；`list_paused_lessons(db, space) -> list[dict]`。写入调用方已持有用户／空间锁；内部不提交。public_lesson 增加 status。

- [x] 写 `test_pause_does_not_complete_or_grade`、`test_paused_review_releases_active_slot_without_rescheduling`、`test_resume_uses_original_questions_and_rejects_other_active_lesson`、`test_late_answer_to_paused_lesson_counts_once`。比较暂停前后事件／阅读／attempts／卡片，恢复题目 ID 不变、跨用户404、活动冲突409；真实晚到答案仍按原幂等服务只计一次。
- [x] 运行 `.venv/bin/pytest backend/tests/test_lesson_pause.py -q`，预期缺少生命周期行为而失败。
- [x] 实现 active／paused 过滤；暂存复习设置 status=paused、active_concept=null。恢复校验空间、未完成状态、现存活动课堂与同概念复习占位；已完成课堂不重新激活。新增 GET `/lessons/paused` 和 POST `/lessons/{id}/resume`（IdempotentRequest）；静态路由先于可能的动态捕获注册。
- [ ] 运行 `.venv/bin/pytest backend/tests/test_lesson_pause.py backend/tests/test_reviews.py backend/tests/test_adaptive_attempts.py -q`，预期全部通过；审阅并按约束提交。

## Task 4：可复用模型调用与受限聊天上下文

**Files:** 新建 `providers/invocation.py`、`chat/context.py`、`tests/{chat_helpers,test_chat_model}.py`；修改 `core/orchestrator.py`、`providers/fake.py`。

**Interfaces:** `async invoke_structured(adapter, schema, task: dict, *, system_prompt: str) -> ModelCallResult`；结果含 validated（Pydantic 或 null）、elapsed_ms、usage、error（ProviderError 或 null）。`build_context(db, space, message: str) -> dict`；`concept_fingerprint(concepts: list[dict]) -> str`；`snapshot_provider(config) -> ProviderSnapshot`。测试 helper 提供 `chat_space(client)` 与可控 StructuredChatAdapter，不依赖真实 Key。

- [x] 写 `test_invocation_preserves_existing_errors_and_usage`、`test_context_excludes_answer_keys_credentials_and_other_spaces`、`test_history_trims_oldest_whole_turns`。断言保留当前需求、最近20成功回合及24000字符预算；secret／answer／rubric不出现在模型 task。用现有 HTTP 替身分别验证 CompatibleAdapter 与 NativeFileAdapter 接收 ChatDecision schema、用户文本不进入 system 规则。
- [x] 运行 `.venv/bin/pytest backend/tests/test_chat_model.py -q`，预期缺少提取接口而失败。
- [x] 提取纯调用，保持原 call_model 的限流、失败审计、错误码和教学 system 文案契约；新增专用计划聊天 system 规则，模型只能返回 ChatDecision。仅通过当前 adapter 构造函数读取 ProviderSnapshot，不向模型传递其凭证字段。
- [x] FakeAdapter 按 ChatDecision 标题返回固定演示场景：预算／重点修改、偏好修改、含糊澄清、普通解释、添加新节点；明确标记演示，不伪装通用自然语言理解。
- [ ] 运行 `.venv/bin/pytest backend/tests/test_chat_model.py backend/tests/test_providers.py backend/tests/test_native_files.py backend/tests/test_e2e.py -q`，预期全部通过；审阅并按约束提交。

## Task 5：校验并原子应用计划修改

**Files:** 新建 `chat/application.py`、`tests/test_chat_application.py`；使用任务1–4接口，定向修改 `planning/intent.py`、`chat/contracts.py`。

**Interfaces:** `apply_decision(db, space, turn: ChatTurn, decision: ChatDecision) -> ApplicationResult`：调用方持锁、不内部提交；在 contracts.py 定义 frozen ApplicationResult，包含 outcome=applied|not_changed|clarification_needed、changes、before、after、revision_id、plan。reply／clarify 不创建需求修订；无实际差异不增加版本。新增概念初始化仅计算新节点的空证据状态，既有状态不重放覆盖。

- [x] 写 `test_budget_and_priority_change_real_next_action`、`test_new_subject_adds_unknown_nodes_without_erasing_old_evidence`、`test_style_change_keeps_lesson_content_but_changes_next_prompt`、`test_explicit_switch_pauses_old_lesson`、`test_bad_graph_or_scope_rolls_back_every_change`。
  ```python
  assert result.after["daily_minutes"] == 15
  assert result.plan["intent_version"] == result.before["version"] + 1
  assert snapshots_of_existing_bkt_and_fsrs(db) == before_algorithms
  ```
- [x] 运行 `.venv/bin/pytest backend/tests/test_chat_application.py -q`，预期缺少应用服务而失败。
- [x] 校验白名单字段、日期、节点key碰撞、完整 DAG、范围／重点／路线引用；追加节点和前置边，写对应 unknown 状态与新卡。合并 RequirementPatch 时使用 model_fields_set 区分显式 null／缺省，范围取有效前置闭包；拒绝 scope 无可执行节点。
- [x] 原子写意图、PlanRevision、脱敏需求变更事件、计划快照。仅 interrupt_current=true 且当前课堂的知识点不在本次重点／目标安排时暂存；只改预算／偏好保持课堂。变更卡差异从持久前后值计算，不从模型自由文本推断是否成功。
- [ ] 运行 `.venv/bin/pytest backend/tests/test_chat_application.py backend/tests/test_planning_intent.py backend/tests/test_lesson_pause.py -q`，预期全部通过；故障注入后新增节点／卡片／意图／修订／事件全部回滚。审阅并按约束提交。

## Task 6：回合三阶段生命周期、历史与 HTTP API

**Files:** 新建 `chat/{turns,service}.py`、`api/chat.py`、`tests/test_chat_api.py`；修改 `api/deps.py`、`main.py`，必要时给 contracts 补齐实现确定的返回字段。

**Interfaces:** `async send_turn(app, session_hash: str, space_id: str, body: ChatSend) -> TurnResult`；`prepare_turn(session_factory, session_hash, space_id, body) -> PreparedTurn | TurnResult`；`publish_turn(session_factory, prepared: PreparedTurn, call: ModelCallResult) -> TurnResult`；`fail_turn(session_factory, prepared: PreparedTurn, error: ProviderError) -> TurnResult`；`async db_phase(app, operation, *args)` 在短 SQLite 应用锁内运行自有 Session 的同步函数。新增读函数返回经对应 Pydantic 响应模型验证的分页／单回合／修订结果。

- [x] 写 `test_clear_request_applies_once_and_survives_restart`、`test_reply_and_clarify_do_not_increment_intent`、`test_same_key_pending_completed_and_conflicting_payload`、`test_failed_or_expired_turn_requires_explicit_retry`、`test_chat_history_and_cursor_are_owner_scoped`、`test_turn_lease_loser_cannot_publish`。同内容不同键在前一回合仍处理中返回409，完成后正常新回合但 no-op 不增版本。
- [x] 运行 `.venv/bin/pytest backend/tests/test_chat_api.py -q`，预期端点／服务不存在而失败。
- [x] 实现 cookie 哈希鉴权的可复用纯 DB helper，现有 current_user 继续保持原锁契约。新 chat POST 不使用将写锁包住整个请求的旧 get_db；每个短阶段在线程内创建 Session、按 User→StudySpace→ChatTurn 顺序锁定并提交／回滚。模型阶段只拿不可变 snapshot，无 Session。
- [x] prepare 认领后释放事务；已有相同回合不重复调用模型。publish 校验 session、空间状态、维护标记、token、租约与意图／课程／配置基线，调用任务5并与助手结果、审计在同一事务保存。模型错误直接产生 failed；应用服务抛错则整体回滚，由新的受保护短事务 fail_turn 仅在原回合仍是 processing 且 token 当前时保存脱敏错误／审计。已经 completed、被撤销或删除的回合不可被失败处理覆盖或重建。终态释放 active_space_id；已撤销会话不能发布助手正文或新计划。
- [x] 注册设计中的4个 chat／revision端点；历史按 `(created_at,id)` 倒序 keyset 分页，cursor 仅定位本空间，按时间正序向前端展示单页。同一秒记录与非法cursor有验证；GET 不生成事件或模型调用。发送／重试的 201／202／409 行为遵循设计。
- [ ] 运行 `.venv/bin/pytest backend/tests/test_chat_api.py backend/tests/test_chat_application.py backend/tests/test_safety.py -q`，预期全部通过；审阅公开响应不含 prompt／密钥／未答题参考答案，按约束提交。

## Task 7：教材／作答并发、删除与维护整合

**Files:** 新建 `tests/test_chat_concurrency.py`；修改 `services/space_deletion.py`、`api/providers.py`、`tests/{test_space_management,test_reset_learning}.py`。

**Interfaces:** 任务6 publish 使用相同 `concept_fingerprint`、配置 fingerprint 和意图 version，普通作答不作为冲突条件。删除顺序先 PlanRevision→ChatTurn→LearningIntent，再沿用现有学习实体顺序；模型配置删除检查尚未过期的活动聊天引用，返回已有 provider_in_use 风格错误。过期 token 始终不能恢复被删除实体。

- [x] 写 `test_answer_during_chat_is_not_blocked_and_keeps_latest_state`、`test_material_publish_and_provider_switch_make_chat_stale`、`test_logout_archive_and_delete_prevent_late_publish`、`test_expired_claim_and_retry_publish_only_current_token`；用 threading.Event 控制 remote 与 CPU，单 httpx ASGITransport 事件循环，DB锁超时限定失败而非挂死。
- [x] 运行 `.venv/bin/pytest backend/tests/test_chat_concurrency.py backend/tests/test_space_management.py backend/tests/test_reset_learning.py -q`，预期缺少保护而失败。部分真实行锁测试显式 skipif 无 TEST_DATABASE_URL。
- [x] 实现并核查并发保护；真实作答之后只从当前 BKT／FSRS 读最新计划；课程／配置改变返回 conflict，不自动增加付费重试。删除后的迟到调用只返回404，不创建 ChatTurn／AgentRun。已归档／已撤销会话的结果取消，不恢复计划。
- [x] 扩展临时维护测试：清空包含 chat／revision，新建空间不被已完成 reset 重跑删除；账号与配置不变。禁止在此任务调用真实 reset 命令。
- [ ] 全套临时 SQLite 回归通过后，在自动销毁的临时原生 PostgreSQL 运行完整套件，预期全部通过。现有临时 PG helper 可复用／复制至本计划 scratch，必须验证其 URL 指向临时实例，绝不将正式 DATABASE_URL 设为 TEST_DATABASE_URL。审阅并按约束提交。

## Task 8：Web 学习对话、变更卡与暂存课堂

**Files:** 新建 `frontend/src/{PlanningChat.jsx,planningChatState.js,planningChatState.test.js}`；修改 `main.jsx`、`styles.css`、必要的 api helper／测试。

**Interfaces:** `PlanningChat({root,onPlanChanged,onLessonResumed})` 按 user_id＋space_id 设 key；`onPlanChanged()` 统一刷新列表和空间详情。`createPlanningChatState()` 提供 runSend、recover、invalidate，重试同一消息沿用 key 和 content；与 latestRequest／scopedAction 协作，不在前端计算推荐或拼造生效差异。

- [x] 写 `duplicate_send_uses_same_turn_key`、`old_account_or_space_result_is_discarded`、`committed_reply_survives_refresh_failure`、`retry_preserves_content_and_key`、`composition_does_not_submit_and_ctrl_enter_does` 行为测试，包含 completed／failed／processing202／clarification_needed 分支。
- [x] 运行 `npm --prefix frontend test`，预期新增 helper 行为尚未实现而失败。
- [x] 实现聊天页、分页加载更早消息、待处理回合恢复轮询（仅 processing 时每2秒）、可编辑示例、发送／重试与错误反馈；输入法组合和 Ctrl/Cmd＋Enter 规则，用户消息仅文本渲染。
- [x] 双栏展示聊天与路线／当前需求，移动端改为纵向；真实应用结果显示前后字段、阶段／新节点、当前下一步与说明，普通回复不显示已应用。暂存课堂显示继续入口，恢复成功后进入同一专属课堂；增加学习记录中文事件标签。
- [x] 在导航、概览和专属课堂加入入口，保留所有已有页面和账号／空间隔离。成功发布后调用 onPlanChanged，刷新失败明确显示“修改已生效，页面刷新失败”，下次读取恢复既有结果，不重复发送。
- [ ] 运行 `npm --prefix frontend test` 与 `npm --prefix frontend run build`，预期全部通过；在隔离演示账号验证1440／390px、实际发送／重载／切换／暂存恢复、无横向页面溢出；审阅并按约束提交。

## Task 9：端到端、文档与一次独立整体验收

**Files:** 更新 `README.md`、`README.en.md`、`docs/{api,architecture,usage.zh-CN,acceptance}.md` 与 `docs/openapi.json`；新增 `docs/planning-chat.md`、`docs/assets/planning-chat.jpg`。验证脚本与截图只使用本项目临时演示数据。

- [x] 执行 `./scripts/check.sh`，预期 Ruff／格式／Shell语法、所有后端测试、前端行为测试和生产构建通过；执行临时 PostgreSQL 全套，预期全部通过。失败按 systematic-debugging 修复，不修改测试以掩盖错误。
- [x] 用临时 localhost 后端和独立 CLI 进程验证：Web Chat 改为15分钟并改变重点 → CLI plan／next／learn 看到同一需求版本与新安排；作答后路线不丢；退出重登仍保留。模型只使用明确 Fake／HTTP替身，无真实付费调用。
- [x] 更新双语说明，明确自动应用、澄清／失败状态、暂存恢复、历史保留、当前模型费用与非逐token发布。生成静态 OpenAPI 使用内存／临时配置并比较相等；`uv build backend --out-dir data/planning-chat-build --offline` 预期 wheel／sdist 成功。
- [x] 按 requesting-code-review／executing-plans 安排一次 fresh-context、read-only 整体审查，提供本 spec／plan、当前完整 diff 与既存 M2／M3 边界、Review Focus、验证记录；不委托实现任务、不审查真实数据。修复已确认 Critical／Important，先复现 RED→GREEN，再完成必要完整回归。
- [x] 停止并关闭本次创建的临时服务／浏览器页；确认没有恢复正式8000端口后台。记录工程验收、真实模型质量未验收边界和工作区状态，不执行再次学习清空、不推送／合并。按实际验证结果勾选计划。

## 计划自审

设计1–3对应任务4–6、8；设计4对应任务2、3、5；设计5对应任务1、6、7；设计6对应任务4、6、7；设计7–8对应任务1–9。五个 Review Focus 都有归属测试。

共享字段使用 intent_version 区分策略 version；生命周期统一使用 paused，完成仍由真实证据决定；模型调用仅传 PreparedTurn 中的纯快照；apply_decision 在 publish 的同一个自有 Session 内执行，不跨线程借用 ORM。所有阶段仍复用现有算法，不再建立第二套调度。

这是单一计划聊天功能的端到端实施计划，九项有依赖的任务不拆成独立产品。已移除占位步骤和未定义的跨任务接口；实施时新增具体类型字段只能细化契约，不能扩展到自由工具执行或新增外部解析服务。

执行备注：带提交文字的步骤保留未勾选，相关实现／审阅／测试已完成；仅提交部分按保护既存未提交改动的取舍保留为工作区diff。全掌握时重点规则按独立审查补充，见验收记录。
