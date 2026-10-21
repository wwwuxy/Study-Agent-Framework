# BKT + FSRS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 所有学习空间统一使用完整开源 BKT 与 FSRS，提供复习、推荐、报告和校准，验证后清空已授权的旧学习数据。

**Architecture:** pyBKT 和 py-fsrs 由薄适配层调用，知识状态与记忆状态分开保存，统一作答服务原子更新事件、状态和计划。FastAPI 是唯一业务入口，Web 和 CLI 复用；清空由独立的一次性管理命令执行。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy／Alembic、SQLite／PostgreSQL、pyBKT 1.4.3、fsrs 6.3.2、React、原有 argparse CLI；FSRS optimizer 使用独立校准环境。

**Spec:** [已确认设计](../specs/2026-10-19-m3-open-source-bkt-fsrs-design.md)。状态：用户已确认；已在当前会话实现并完成工程验收与一次性切换。结果见 docs/acceptance.md 的 M3 章节。工作区保留既存 M2 变更，未拆分提交／推送。

## Global Constraints

- “所有可用空间统一用 pyBKT 估计掌握情况、py-fsrs 安排复习，无逐空间开关、无旧规则回退。”
- “保留仓库、账号、认证、模型配置和密钥、Web／CLI、LLM 教学及原生 PDF 文件接口。”
- “不增加独立远端 PDF 解析、本地正文解析、OCR 或 Embedding 模型。”
- “不重复计分、依赖过滤、低置信保守处理继续保留为证据约束。”
- “清空通过独立一次性管理命令执行，不嵌入常规迁移或每次启动；再次启动／部署不得再次删除新学习记录。”
- 当前存在用户未提交的 M2 改动，禁止 reset、clean 或仅从 HEAD 开新工作树丢弃这些改动；实施前按 using-git-worktrees 技能核对隔离方案并保留完整工作区。
- 真实学习数据只在最后切换时清理；此前全部测试使用临时库、框架自有资料与演示／HTTP 替身，不调用真实付费生成接口。
- 只提交本任务明确修改的代码；不使用 `git add .` 将其他进行中的改动一并提交。Git 写入若不可用则保留可审阅 diff，不因此重置工作区。

## Review Focus

1. 异步路由中 pyBKT 的 CPU 推断不能阻塞主循环，也不能把可变训练模型或 ORM Session 共享给其他请求；任务 1、2 验证隔离和线程边界。
2. FSRS 的分钟级学习步骤与无证据新卡不能被当作“明天复习”或全部逾期；任务 1、4、5 固定时钟验证。
3. 通用答题与复习提交入口不能分别重复更新同一 FSRS 日志；任务 3、4 验证跨入口重试与冲突。
4. 永久删除与仍在返回的教材上传不能恢复学习数据或丢失清理句柄；任务 6 验证删除和迟到结果。
5. 清空命令失败后重跑不能删除切换后新建空间，不能清掉账号／密钥；任务 6、10 使用冻结目标和操作记录验证。

## 文件边界与公共契约

新增 `learner/evidence.py`（观测规范）、`learner/bkt.py`（仅库适配）、`learner/parameters.py`（验证／版本）、`learner/service.py`（状态编排）。新增 `reviews/fsrs_adapter.py`（纯算法）、`reviews/state.py`（卡片和日志持久化）、`reviews/sessions.py`（复习生成与恢复），避免把调度和 LLM 生成揉进同一模块。

新增 `teaching/attempts.py` 和 `teaching/lessons.py` 提取两端共用提交／课堂逻辑；新增 `learner/report.py`、`api/adaptive.py`、`api/reviews.py`、`schemas/adaptive.py`。维护清空放在 `maintenance/`，离线校准放在 `evaluation/`。旧 `learner/estimator.py` 删除，原 `planning/policy.py` 替换。

下文 `Session` 指 SQLAlchemy Session，`Request` 为 FastAPI Request，时间参数均为带 UTC 时区的 datetime；所有 `dict` 返回值必须由 `schemas/adaptive.py` 中对应 Pydantic 模型验证。

## Task 1：开源算法适配与证据规范

**Files:** 新建 `backend/app/learner/{evidence,parameters,bkt}.py`、`backend/app/reviews/{__init__,fsrs_adapter}.py`、`backend/tests/test_bkt.py`、`backend/tests/test_fsrs.py`；修改 `backend/pyproject.toml` 和两个 requirements 锁文件；新增 `backend/requirements-calibration.lock`、`THIRD_PARTY_NOTICES.md`。

**Interfaces:**
- `EvidenceBatch`：不可变观测序列及总／独立／辅助／不确定／综合证据计数；每条观测保存 `event_id,item_id,correct,assistance,difficulty,occurred_at`。
- `observations_for(concept_id: str, events: list[dict]) -> EvidenceBatch`：排序、可靠性筛选、题目去重、辅助识别。
- `BKTParameters`：设计规定的先验／学习率／两类猜对与失误／版本；`estimate_bkt(batch: EvidenceBatch, params: BKTParameters) -> dict`：库推断及业务标签。
- `FSRSUpdate`：`card: dict, log: dict, rating: int, reason: str`；`new_card(now: datetime) -> dict`；`review_card(card: dict, rating: int, now: datetime, duration_ms: int | None = None) -> FSRSUpdate`；`memory_view(card: dict, now: datetime) -> dict`。
- `algorithm_manifest() -> dict`：固定启用、库版本、配置／证据版本和未校准状态；无可关闭字段。

- [x] 写 `test_bkt_matches_pybkt_native_prediction`、`test_hint_class_differs_without_custom_weighting`、`test_unreliable_composite_and_solution_do_not_promote`、`test_parameter_objects_are_request_isolated`，分别断言原生结果近似相等、辅助提升更小、低证据不掌握、一次请求更改不污染另一请求。
- [x] 写 FSRS 原生对照参数测试：四评分、Learning／Review／Relearning、分钟步骤、长间隔、JSON 恢复、同 UTC 时间可重复、无证据新卡未逾期。运行 `.venv/bin/pytest backend/tests/test_bkt.py backend/tests/test_fsrs.py -q`，确认因适配层缺失而失败。
- [x] 在隔离依赖环境验证候选版本的 Python 3.12 安装与真实 API，锁定运行／开发／校准依赖。pyBKT 用其原生推断和观测类别，不手写后验；FSRS 使用 `Scheduler(enable_fuzzing=False, desired_retention=0.9)` 与原生序列化。记录失败／必要版本调整。
- [x] 实现上述纯适配接口与参数校验；不连接数据库或网络。用同一命令验证通过，检查无旧规则导入、无固定天数算法。运行 Ruff 检查新增文件。
- [ ] 审阅该任务 diff，单独提交算法适配、依赖锁和许可证声明；不得顺带提交既存 M2 修改。

## Task 2：双算法持久化、初始化和重放

**Files:** 新建 `backend/app/learner/service.py`、`backend/app/reviews/state.py`、`backend/app/schemas/adaptive.py`、`backend/migrations/versions/0004_adaptive_learning.py`、`backend/tests/test_adaptive_state.py`；修改 `db/models.py`、`core/orchestrator.py`、`api/spaces.py`、`jobs/materials.py`、`tests/test_domain.py`、`tests/test_migrations.py`；删除旧 `learner/estimator.py`。

**Interfaces:**
- 新 ORM `ReviewState`（用户／空间／概念复合归属、Card JSON、due、配置版本）、`ReviewSession`（会话、题目／课堂、幂等键、周期、状态）、`ReviewLogRecord`（事件唯一、原生日志及参数／前后状态）。两个复合外键保证跨空间题目／概念不能混用。
- `MaintenanceOperation`：操作 ID、冻结的目标空间／学习调用审计 ID、阶段、计数、完成状态；不保存学习正文／凭证。供任务 6 防重入，不提供公开 HTTP 管理入口。
- `ensure_memory_states(db: Session, space: StudySpace, now: datetime) -> None`；`apply_memory_event(db: Session, space: StudySpace, event: LearningEvent) -> dict | None`。
- 将 `rebuild_states(db, space)` 改为 `async def rebuild_states(db: Session, space: StudySpace) -> None`：主线程读取事件／概念，只把纯计算和不可变输入交线程池，回到当前请求线程写 ORM，不把 Session 传入工作线程。

- [x] 写新空间／教材新概念双算法初始化、无观测为空估计、重复重建事件不变、同参数重放状态一致、模型调用失败后状态不变、不同用户隔离测试；运行对应新测试，确认失败。
- [x] 增加迁移及模型，空间统一元数据默认 BKT＋FSRS，不设开关；ReviewState 每概念唯一、ReviewLogRecord 每事件唯一、ReviewSession 每概念至多一个活动会话。迁移不清空历史、不做模型调用。
- [x] 实现状态编排；将 `create_space`、`rebuild_profile` 和资料发布链的重建调用改为 await，`sync_concepts` 相应异步化。profile 使用保存的实际库／参数版本；旧缓存不能伪装成 BKT 状态。删除旧规则文件并改领域测试为库结果和业务门槛断言。
- [x] 运行 `.venv/bin/pytest backend/tests/test_bkt.py backend/tests/test_fsrs.py backend/tests/test_adaptive_state.py backend/tests/test_domain.py backend/tests/test_migrations.py backend/tests/test_materials.py -q`，全部通过；临时旧库升级、metadata check 和无真实数据删除通过。
- [ ] 审阅迁移外键／唯一约束和异步线程边界，提交本任务变更；保留对真实用户库尚未运行的说明。

## Task 3：统一作答、FSRS 更新与幂等

**Files:** 新建 `backend/app/teaching/attempts.py`、`backend/tests/test_adaptive_attempts.py`；修改 `api/learning.py`、`schemas/api.py`、`core/orchestrator.py`、`reviews/state.py` 和原 e2e 测试。

**Interfaces:**
- `AttemptSubmit.memory_rating: Literal['again','hard','good','easy'] | None = None`。
- `async submit_attempt(request: Request, db: Session, space: StudySpace, body: AttemptSubmit, *, expected_review_id: str | None = None) -> dict`：统一服务，调用方负责事务，不内部提交成功事务。
- `maybe_complete_task(db: Session, lesson: Lesson) -> None`：课堂已读且题目均提交才写幂等完成事件，无掌握更新。
- `apply_memory_event` 使用观测发生时刻；错误／辅助映射 Again，可靠独立默认 Good，允许独立 Hard／Easy，低置信不更新。结果返回实际 rating、原因和 due。

- [x] 写独立正确／提示正确／错误／低置信差异测试，伪造 Easy 不可绕过辅助；两个入口重复键不产生第二条日志，相同题不同键仍拒绝；BKT／FSRS 故障时答案、事件、卡片、计划一起回滚。运行新测试确认失败。
- [x] 从原 submit 路由提取批改与提交服务。将 Q-Matrix、难度、题型、评分器和证据版本快照加入事件；请求摘要包含 memory_rating；将读完成逻辑接入 `maybe_complete_task`，无论先读还是先答都只完成一次。
- [x] 内部依次批改、append_event、await BKT 重建、FSRS 卡片／日志、计划、作答结果，保持同一数据库事务。复习会话锁与用户行锁按固定顺序获取；错误时不降级规则。
- [x] 运行 `.venv/bin/pytest backend/tests/test_adaptive_attempts.py backend/tests/test_e2e.py backend/tests/test_safety.py -q`；使用临时 PostgreSQL 补并发同题／不同题提交，断言不丢事件且只更新一次。保留原提示防隐瞒、幂等和权限回归。
- [ ] 审阅两条提交入口和任何显式 commit／rollback 的交互，提交本任务变更。

## Task 4：复习会话与完整教学流程

**Files:** 新建 `backend/app/reviews/sessions.py`、`backend/app/api/reviews.py`、`backend/app/teaching/lessons.py`、`backend/tests/test_reviews.py`；修改 `api/learning.py`、`main.py`、`schemas/adaptive.py`、`providers/fake.py`、`providers/fake_files.py`。

**Interfaces:**
- `ReviewStart`：`concept_id: str, idempotency_key: str`；`ReviewSubmit` 复用 AttemptSubmit。
- `async create_lesson(request, db, space, action: dict, request_key: str, *, review_id: str | None = None) -> dict`：已有讲解／来源校验的共享生成器。
- `async start_review(request, db, space, body: ReviewStart) -> dict`：到期校验、并发复用、生成新题并关联会话。
- `list_reviews(db: Session, space: StudySpace, now: datetime) -> dict`：返回 due／upcoming／unassessed 分类，GET 不生成内容；`get_review(db, space, review_id) -> dict`。

- [x] 写分钟级到期／未学新卡分类、不支持未知概念、不能跨空间访问、GET 零模型调用、重复开始恢复、已读未答课堂优先恢复、生成失败无孤儿会话，以及通用／复习入口交叉提交测试；运行新测试确认失败。
- [x] 增加 `/reviews`、`/reviews/start`、`/reviews/{rid}`、`/reviews/{rid}/submit`。直接复习提交调用任务 3 服务并传 expected_review_id，不复制批改代码。
- [x] 将原课堂生成提取到共享 helper。`POST /lessons` 遇 REVIEW 使用同一 start_review，已有未完成题目优先恢复；明确模式传入 LLM。演示适配器覆盖模式／复习，使用不同题干且不伪称真实解析。
- [x] 运行 `.venv/bin/pytest backend/tests/test_reviews.py backend/tests/test_adaptive_attempts.py backend/tests/test_e2e.py backend/tests/test_materials.py -q`；断言复习返回的题目映射、引用及答案隐藏正确；固定时钟推进，无长时间 sleep。
- [ ] 审阅会话／课堂／题目关联、恢复与唯一约束，提交本任务变更。

## Task 5：自适应推荐、Q-Matrix 和报告

**Files:** 替换 `backend/app/planning/policy.py`；新建 `learner/report.py`、`api/adaptive.py`、`tests/test_adaptive_policy.py`、`tests/test_learning_report.py`；修改 `core/orchestrator.py`、`api/spaces.py`、`main.py`、`schemas/adaptive.py`。

**Interfaces:**
- `choose_action(concepts: list[dict], states: dict, review_states: dict, evidence: list[dict], available_minutes: int, *, now: datetime, target_date: str | None = None) -> dict`。
- 评分明确为目标权重 `importance*2`、薄弱程度 `2*(1-p)`（无观测 p 取 0 用于排序，不展示能力）、低／中／高证据奖励 `2/1/0`、逾期奖励 `3+min(overdue_days,7)`，只对已学习到期卡片计逾期。前置过滤先于评分；同分按知识点 key 稳定排序。总时长不超过 daily_minutes。
- `async build_report(db: Session, space: StudySpace, days: Literal[7,30], now: datetime) -> dict`：当前线程读取 ORM，纯历史重放在线程池完成，返回阶段分布、证据、误区、复习／任务统计、窗口前后状态及当前理由。
- `GET /q-matrix` 无答案；`GET /algorithms` 固定双启用；`GET /report?days=7`，不允许任意天数扩大查询。

- [x] 写多级前置硬约束、未知诊断预算不循环、FSRS 到期影响排序但 BKT 不清零、稳定同分、目标期不绕过前置、未完成任务优先测试；写空报告、无分母为 null、7／30 天重放、待核实评分分组测试，运行确认失败。
- [x] 实现 policy_v2，教学模式为首次／误区／定向／迁移／阶段／复习；关键未知仍有限预算诊断。已有误区仅在最近可靠证据支持时优先，不让历史一次错误永久阻断。
- [x] 实现当前计划视图，与 next-action 共享 now 和候选计算；持久快照带 as_of，GET 不写事件。报告历史估计通过纯重放在线程池计算，禁止 ORM 跨线程。
- [x] 运行 `.venv/bin/pytest backend/tests/test_adaptive_policy.py backend/tests/test_learning_report.py backend/tests/test_reviews.py -q`，断言报告与当前推荐一致、读取零模型调用、Q-Matrix 不泄露标准答案。
- [ ] 审阅评分理由和报告分母，提交本任务变更。

## Task 6：共用删除服务和一次性清空机制

**Files:** 新建 `backend/app/maintenance/{__init__,__main__,reset_learning}.py`、`backend/app/services/{__init__,space_deletion}.py`、`backend/tests/test_reset_learning.py`；修改 `api/spaces.py`、`jobs/materials.py`、`tests/test_space_management.py`、`db/models.py`。

**Interfaces:**
- `erase_space_content(db: Session, space: StudySpace, storage: MaterialStorage) -> dict`：从原删除路由提取，扩展新表，保留远端最小句柄。
- `freeze_reset_targets(db: Session, operation_id: str) -> MaintenanceOperation`：首次冻结所有既有空间和学习调用审计 ID，含空 space_id 的旧教学调用；后续只处理同一清单，不能清理其后新增的调用。
- `async reset_learning(settings: Settings, operation_id: str, *, apply: bool, expected_target: str | None) -> dict`：只输出计数／进度／失败清理数，不输出学习正文或密钥。
- 管理入口：`python -m app.maintenance reset-learning --operation-id m3-2026-10-19` 默认只读预览；加 `--apply --expected-target <预览指纹>` 才应用。此显式执行参数由代理按既有授权使用，不重新请求删除授权。

- [x] 写两个用户／多个空间／教材／卡片／日志的临时清空测试；断言账号、密码哈希、模型配置和密文完全不变，原内容为零，远端失败仍有清理句柄。写中途失败后重跑、新建空间不在冻结清单、指纹错误不写、日常启动不清空测试；确认失败。
- [x] 提取空间删除服务，维持 append-only 删除仅在已删空间允许的保护；按复习日志→会话→状态→学习实体顺序删除。清理文件暂存和 M2 索引检查点，失败清理不隐藏，不创建新理解任务。
- [x] 实现维护命令与任务状态：停写和 worker 之前不执行真实清空；按已授权全用户范围处理冻结目标，明确区分本地删除和远端未确认。完成墓碑可移除，活动上传或待清理句柄仍持久保存。
- [x] 运行 `.venv/bin/pytest backend/tests/test_reset_learning.py backend/tests/test_space_management.py backend/tests/test_materials.py backend/tests/test_reviews.py -q`；在临时 PostgreSQL 重跑，验证外键／租约／迟到上传不恢复已删除学习正文。此任务不得操作真实 data/study.db。
- [ ] 审阅冻结范围、重试和凭证保护，提交机制；真实执行只在任务 10。

## Task 7：原生拟合、FSRS 优化和版本化评测

**Files:** 新建 `backend/app/evaluation/{__init__,__main__,dataset,metrics,calibration}.py`、`backend/app/maintenance/rebuild_algorithms.py`、`backend/tests/test_adaptive_evaluation.py`、`backend/tests/fixtures/m3/{manifest,sequences}.json`、`docs/m3-evaluation.md`；修改 `learner/parameters.py`、`core/settings.py`、`maintenance/__main__.py`。

**Interfaces:**
- `fit_bkt(dataset: dict, seed: int) -> dict` 调用 pyBKT EM；`optimize_fsrs(logs: list[dict], *, optimize_retention: bool) -> dict` 调用官方 Optimizer；不写生产配置。
- `evaluate(dataset: dict, parameters: dict) -> dict`：按学生划分、观测前预测、Brier／log loss／混淆矩阵、独立与辅助分组、无分母解释。
- `validate_parameter_artifact(artifact: dict) -> dict`：严格版本／数值／配置校验；`LEARNER_PARAMETERS_PATH` 仅接受服务端部署配置，不能由普通用户上传模型 pickle 或代码。
- 命令 `python -m app.evaluation evaluate|fit-bkt|optimize-fsrs --dataset PATH --output PATH`，优化另加 `--optimize-retention`。产物默认为候选，发布需先验证，并在停写维护期间按新版本重建派生状态。
- `async rebuild_algorithms(settings: Settings, artifact: dict, operation_id: str) -> dict`：由 `python -m app.maintenance rebuild-algorithms --artifact PATH --operation-id KEY` 调用。停写期间按新参数重放 BKT、用原生 FSRS reschedule 接口重调度卡片并更新计划；保留原事件／原生日志及其版本，不把重调度写成新学习。逐空间事务和版本化进度支持失败恢复，重启服务后统一读取同一已验证配置。

- [x] 写拟合／验证／测试 learner 不重叠、当前答案不可影响当前预测、单类别／不足数据明确报错、空分母、坏参数及哈希不匹配测试；写参数重建不新增原事件／日志、失败后可恢复且缓存版本一致测试；确认失败。
- [x] 创建有来源说明和固定种子的自有数据，包含独立、辅助、错误和延迟复习，manifest 保存 split 与哈希；不取真实用户数据，不下载他人学习记录。
- [x] 实现库原生 EM、Optimizer 参数／目标保持率优化和原生日志重调度入口，结果记录库／数据／参数版本。校准环境实际安装官方 extra；在线服务不因此加载训练依赖或训练模型。
- [x] 运行 `.venv/bin/pytest backend/tests/test_adaptive_evaluation.py -q`；在独立校准环境实际运行三个命令，保存初始／拟合参数与真实评测结果到忽略目录，脱敏结果写入 docs。不得用 mock 假装优化已验证，不以合成改善声称真实学习提升。
- [ ] 审阅数据泄漏、参数发布和依赖范围，提交自有评测数据、代码与说明。

## Task 8：CLI 完整入口

**Files:** 修改 `backend/app/cli/{main,interactive,render}.py`；新增 `backend/tests/test_cli_adaptive.py`；更新 `docs/cli.md`、`docs/usage.zh-CN.md`。

**Interfaces:** `review list`；`review start --concept ID [--request-id KEY]`；`review submit ID --item ITEM --answer TEXT [--rating again|hard|good|easy] [--request-id KEY]`；`report --days 7|30`；`algorithms`。统一支持原有 `--space`、`--json`。

- [x] 写独立 CLI 调用建空间、双算法状态、学习、到期复习、评分、报告、退出重登和 JSON 输出测试；写提示后 Easy 不可绕过、切换空间不串数据、命令无旧规则开关测试；运行确认失败。
- [x] 增加 argparse 与 API 映射、中文人工输出和复习课堂交互，显示服务端实际评分／到期；保留终端控制字符过滤、隐藏凭证输入和现有会话权限。CLI 不计算概率或日期。
- [x] `learn` 遇到 REVIEW 或未完成复习走后端同一会话，不在本地创建第二套题；更新命令帮助和使用说明。
- [x] 运行 `.venv/bin/pytest backend/tests/test_cli.py backend/tests/test_cli_adaptive.py backend/tests/test_cli_streaming.py -q`，再以临时 localhost 服务和独立 CLI 进程验证真实 HTTP 恢复。
- [ ] 审阅端点、幂等键与输出，提交 CLI 变更。

## Task 9：Web 复习、报告与算法状态

**Files:** 新建 `frontend/src/{Reviews,LearningReport,AlgorithmStatus}.jsx` 和必要的状态 helper／测试；修改 `frontend/src/main.jsx`、`styles.css`、动作／事件中文标签；更新 README 中文／英文说明。

- [x] 为晚到空间响应、登出失效、复习提交重复点击和空报告展示写有行为意义的测试，运行 `npm --prefix frontend test` 确认新增行为测试先失败。
- [x] 增加到期／未来／未学习列表，开始／恢复、四级回忆难度与服务端校验反馈、下次复习时间；报告提供 7／30 天能力与证据变化；算法页只读显示统一启用及未校准状态，无开关或切回规则入口。
- [x] 概览和课堂接入 REVIEW 及各教学模式、返回依据。复用已有异步隔离，不能让旧账号／空间结果覆盖新页面；不展示未经校准的高精度能力百分比。
- [x] 运行前端测试与生产构建；用独立演示账号检查桌面／390px 移动端的学习→复习→报告、重载恢复、删除空间与清理状态，不使用真实付费模型或真实学习记录做 UI 试验。
- [ ] 审阅界面可用性和跨端数据一致性，提交前端及文档变更。

## Task 10：全量验收、独立审查与真实切换

**Files:** 更新 `README.md`、`README.en.md`、`docs/{api,architecture,development-roadmap,acceptance,m3-adaptive-learning}.md`、`docs/openapi.json`、`backend/pyproject.toml` 的当前阶段描述；必要时更新 Docker 构建依赖说明。

- [x] 执行 `./scripts/check.sh`、独立临时真实 PostgreSQL 全套、带既有内容的迁移／清空测试、wheel／sdist 构建和静态 OpenAPI 一致性检查；校准与 Web／CLI 检查记录齐全。失败按 systematic-debugging 处理，不删测试换取通过。
- [x] 对整套变更安排一次独立代码审查，重点算法原生对照、事务／并发、权限／清空、所有空间统一启用；解决已证实关键问题后仅重跑受影响检查及必要完整回归。扫描运行代码确认无 rules_v1 估计、无简化阶梯调度。
- [x] 核对本项目实际进程和配置目标，停止其写入与 worker，运行任务 6 默认预览；只记录指纹／计数。使用既有删除授权执行同一 operation_id 的 apply，驱动清理任务，失败远端句柄如实留待重试，不输出密钥或学习正文。
- [x] 对真实切换做只读验证：账号／配置仍在；旧可用空间、学习事件、答案、课堂、章节和本地教材内容为零；远端待清理计数明确。启动新版本并确认新空间初始化双算法，重复启动不会再次清空。若需创建验证空间，使用独立标注的临时演示账号并在验证后清理。
- [x] 按实际结果更新阶段三验收：哪些为原生算法／合成数据验证、哪些真实教育效果未评估、是否仍有远端清理未确认、Docker／pgvector 的历史未验收范围。总结变更、测试及数据清空计数，不把候选参数称作已验证教育模型。

## 自审与交付边界

设计九项功能对应任务 1–9；五项原验收对应算法重放、作答差异、前置约束、复习分离、版本化评测测试，最终由任务 10 汇总。完整算法通过原生库结果对照，清空通过真实执行及计数验证；两者不能相互替代。

功能与验证已完成。带“提交”的审阅步骤仍未勾选，仅因与既存未提交 M2 改动重叠，采用保留完整工作区 diff 的既定取舍；不表示有未完成的功能。验收与取舍记录见 docs/acceptance.md。
