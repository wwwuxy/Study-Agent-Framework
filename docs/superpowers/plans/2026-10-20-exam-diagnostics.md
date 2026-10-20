# 已批改试卷成绩诊断 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户上传已批改 PDF 或多页照片后，由其配置的模型识别并生成诊断，可靠作答自动更新当前空间的知识学习状态和下一步。

**Architecture:** 独立的 `exam_diagnostics` 模块管理草稿、附件、识别检查点、报告及逐题证据。原生用户模型适配器增加独立图片探测和试卷多输入接口，服务端执行严格校验；持久 worker 在短事务之间调用模型，同事务发布报告、BKT 状态和计划，外部试卷不更新 FSRS 回忆时间。

**Tech Stack:** 现有 Python 3.12+、FastAPI、SQLAlchemy／Alembic、Pydantic、httpx、pyBKT 1.4.3、fsrs 6.3.2；React 19、Vite、Node 内置测试。新增 Pillow 只用于图片格式校验及框架自制能力探测图，不做 OCR。

**Spec:** [已确认设计](../specs/2026-10-20-exam-diagnostics-design.md)。执行前同时阅读设计和本计划。

## Global Constraints

- 识别完全交给用户配置的模型；沿用已有 BYOK 凭证、能力检测和传输授权；不增加本地 OCR 或本地试卷正文解析。
- 支持一个多页 PDF，或一组可调整顺序的 JPG／PNG；同一份试卷不混用 PDF 和图片，不支持 HEIC、WebP、压缩包及外部图片 URL。
- 默认单文件不超过现有 `material_max_bytes`（当前 20 MiB）；图片最多 20 张，总字节不超过单文件限制的两倍；单边不超过 8192 像素、单张不超过 3200 万像素；最多 200 个叶子题目。
- 分值必须为有限数值且 `0 <= 得分 <= 满分`；缺少分值不补成 0；父题和子题只统计叶子作答。
- 仅老师批改清晰、识别和映射均为高置信度、完整正确或错误、关联单个已有知识点的题目更新 BKT。部分得分、模糊批改和多知识归因不明不产生二元观测。
- 外部证据固定 `assistance_level="unknown"`、`difficulty=1`；不增加独立答对资格。既有 `llm_rubric:` 排除规则继续有效。
- 考试日期按用户时区当天中午转 UTC，最大为导入时刻；未知日期按导入顺序并明确标注。所有导入均不改变已有 FSRS due、不生成回忆日志、不代替在线任务完成。
- 同空间相同文件内容多重集去重；改文件名／重排照片不重复入库。必须核对实际接收文件，不能把客户端声明哈希直接作为已验证内容。
- 新增迁移接在当前 head 后，不修改历史迁移；使用隔离测试库，不访问真实付费模型；本任务不清空既有学习数据。
- 当前工作区包含大量已有未提交实现。执行时先按 using-git-worktrees 技能判断隔离方式，保留包含这些实现的工作树基线；不能直接从旧 HEAD 新建空白分支而丢失实际依赖，不暂存或提交其他任务的改动。每个任务提交仅包含本任务增量；无法分离的已有文件不整文件提交。

## Review Focus

1. 客户端伪报旧文件哈希、实际上传不同字节：不能绕过核验复用已有报告；任务 2 加断言。
2. 同一天多次导入、跨页叶子题、分页时间戳相同：顺序和 cursor 必须稳定，不漏题、不重复读或重放；任务 1、4、5、8 加断言。
3. 核对过程中只有知识映射被修正：允许补入原本批改清晰的题目；只改对错不能把模糊批改升级为有效证据；任务 8 加断言。
4. 用户传入 NaN、Infinity、布尔分值或极长题干／批注，模型返回半截 JSON：应明确拒绝并保留可恢复任务，不发布部分成功；任务 1、4、7 加断言。
5. 上传过程中登录过期或空间归档，及模型配置在阶段检查点后变化：不能继续发布，原服务商清理仍能恢复；任务 2、7、8 加断言。

## 文件和职责

`backend/app/exam_diagnostics/` 新建 `__init__.py`、`models.py`（四张表）、`contracts.py`（跨阶段不可变数据）、`storage.py`（格式／流式文件）、`drafts.py`（草稿和附件）、`recognition.py`（模型任务／业务规范化）、`report.py`（确定性统计）、`evidence.py`（资格／时间／事件）、`publication.py`（原子发布）、`queue.py`（认领／阶段检查点）、`worker.py`（远端阶段编排）、`cleanup.py`（远端清理与删除）、`queries.py`（有归属的公开读取）、`review.py`（待核对修订）。公开模型在 `backend/app/schemas/exams.py`，路由在 `backend/app/api/exams.py`。

适配器修改 `backend/app/providers/base.py`、`native.py`、`fake_files.py`，新增 `probe_image.py`；保持 `analyze_file()` 与教材调用兼容。集成只修改 `main.py`、`core/settings.py`、`learner/evidence.py`、`learner/bkt.py`、`learner/report.py`、`reviews/state.py`、`services/space_deletion.py`、`maintenance/reset_learning.py`、迁移 env 和新迁移；`core/orchestrator.py` 仅在共享状态计算确有必要时作最小提取。

前端新增 `ExamDiagnostics.jsx`、`ExamUpload.jsx`、`ExamReport.jsx`、`examDiagnosticState.js`、`examDiagnosticState.test.js`；只在 `main.jsx` 加入口和刷新回调，在 `styles.css` 加局部样式，在 `LearningReport.jsx` 展示分开的外部证据统计。

测试集中在 `backend/tests/exams/`，以下任务定义其具体文件；迁移、原生协议及既有学习回归留在原测试模块。项目测试配置会发现子目录。每个任务依次执行 RED → GREEN → 定向回归，完成后只提交该任务明确拥有的增量。

---

### Task 1: 诊断契约与持久化约束

**Files:** Create `backend/app/exam_diagnostics/{__init__,models,contracts}.py`, `backend/app/schemas/exams.py`, `backend/migrations/versions/0007_exam_diagnostics.py`, `backend/tests/exams/{conftest,test_contracts,test_models}.py`; Modify `backend/migrations/env.py`, `backend/tests/test_migrations.py`, `backend/app/core/settings.py`, `.env.example`.

**Interfaces:** `ExamCreate(name, exam_date, attachments, idempotency_key)`、`AttachmentManifest(client_id, filename, mime_type, size_bytes, sha256)`、`ExamStart(consent, idempotency_key)`、`ExamRetry(consent, idempotency_key)`、`ExamQuestionPatch(expected_version, result, score, max_score, concept_ids, idempotency_key)`；所有请求继承 `StrictModel`。公开 `ExamCapabilities`、`ExamDetail`、`ExamPage`、`ExamQuestionView`；识别输出 `ExamRecognition`、`RecognizedQuestion`、建议 `ExamAdvice`。`contracts.py` 定义冻结数据类 `ExamClaim(job_id, diagnostic_id, user_id, space_id, token, generation)` 和 `ExamCheckpoint(recognition, advice, provider_fingerprint, concept_fingerprint)`；后两项 payload 为对应 Pydantic 对象或 None。

- [ ] **Step 1:** 在 `test_contracts.py` 写 `test_manifest_and_scores_are_bounded`：20 张合法照片通过、21 张拒绝；混合 PDF／图像拒绝；201 叶子题拒绝；NaN／Infinity／bool 分值拒绝；题干最长 12000 字、答案／批注最长 8000 字，超出拒绝；题 ID 限 80 字。在 `test_models.py` 写同空间文件集合摘要唯一、逐题 event ID 唯一、跨空间外键失败、一个活动识别占位唯一的测试。

最小断言示例（变量由上述具名测试的场景准备）：

```python
assert {"exam_diagnostics", "exam_attachments", "exam_questions", "exam_jobs"} <= set(inspect(engine).get_table_names())
assert old_space.goal == "old goal"  # 从 0006 升级后仍保留
```

- [ ] **Step 2:** Run `.venv/bin/pytest backend/tests/exams/test_contracts.py backend/tests/exams/test_models.py -q`，确认缺少新契约／实体导致失败。
- [ ] **Step 3:** 实现四表及契约。`ExamDiagnostic` 使用 nullable `verified_files_digest`，仅实际附件核验后填写，唯一 `(space_id, verified_files_digest)`；请求键唯一，验证摘要前允许不同请求创建草稿。诊断状态为 draft／queued／running／completed／failed／cancelled／duplicate；duplicate 保留 `canonical_id` 及原请求身份，清除重复文件，后续请求返回 canonical 诊断。`ExamJob` 状态为 queued／running／succeeded／failed／cancelled，`active_space_id` 可空唯一，只为未结束的识别任务占用；清理任务不占用。`ExamQuestion.event_id` 可空唯一；模型／题目／任务均保存版本及复合归属外键。`ExamDetail` 含当前任务、结果、有效证据数、前后快照及版本，不暴露凭证／远端引用。增加 `exam_worker_enabled=True`、`exam_max_images=20`、`exam_max_questions=200`、`exam_job_attempts=3`、`exam_max_output_tokens=32000`、`exam_call_timeout_seconds=120`；字节／像素限制按 Global Constraints。迁移 env 显式加载独立模型 metadata；新迁移 head 先用 Alembic ScriptDirectory 核实。
- [ ] **Step 4:** 在 `backend/tests/exams/conftest.py` 提供 `exam_env` fixture：复用原 `client/settings`、注册隔离账号和 fake_files 空间，暴露 `client, app, space_id, root`；提供 `recognition_payload`、`image_bytes`、`pdf_bytes` 固定合法样例，均明确为协议替身。增加从 0006 升级保留已有空间、降级／重升及 `command.check()` 测试。
- [ ] **Step 5:** Run `.venv/bin/pytest backend/tests/exams/test_contracts.py backend/tests/exams/test_models.py backend/tests/test_migrations.py -q`，全部通过后提交 `feat: add exam diagnostic contracts and persistence`。

### Task 2: 文件校验、草稿、附件与受控下载

**Files:** Create `backend/app/exam_diagnostics/{storage,drafts,queries}.py`, `backend/app/api/exams.py`, `backend/tests/exams/{test_uploads,test_queries}.py`; Modify `backend/app/main.py`, `backend/pyproject.toml`, `backend/requirements.lock`, `backend/requirements-dev.lock`。

**Interfaces:** `ExamStorage(root)` 的 `stage(user_id, space_id, attachment_id, manifest, max_bytes)` 返回可流式接收的 staged object；`drafts.create_draft(db, user, space, body) -> ExamDetail`；`async drafts.receive_attachment(app, session_hash, space_id, diagnostic_id, attachment_id, chunks) -> ExamDetail`；`queries.detail(db, user_id, space_id, diagnostic_id) -> ExamDetail`、`queries.page(db, user_id, space_id, before, limit) -> ExamPage`。所有存储路径置于现有 storage root 的 `exams/` 子目录，删除空间时 Task 8 显式清理。

- [ ] **Step 1:** 在 `test_uploads.py` 写 `test_forged_manifest_hash_never_reuses_report`、`test_partial_upload_never_becomes_ready`、`test_format_size_and_image_pixel_limits`、`test_login_expired_during_stream_discards_staged_file`；相同文件名不同字节不能合并，相同附件重复 PUT 相同字节幂等、不同字节 409。`test_queries.py` 覆盖跨归属全部 404、相同创建时间用 ID 分页不重不漏、原文件返回安全 attachment 下载头。

最小断言示例（变量由上述具名测试的场景准备）：

```python
assert forged_upload.status_code == 422
assert diagnostic.status == "draft"
assert not staged_path.exists()  # 登录失效的流式上传不得发布文件
```

- [ ] **Step 2:** Run `.venv/bin/pytest backend/tests/exams/test_uploads.py backend/tests/exams/test_queries.py -q`，确认尚无路由／流式实现时失败。
- [ ] **Step 3:** 新增 Pillow 运行依赖，使用 `uv pip compile backend/pyproject.toml -o backend/requirements.lock` 和带 `--extra dev` 的对应命令更新 dev lock；不执行全量依赖升级。PNG／JPEG 使用签名和 Pillow `verify()`／尺寸检查，限定解码格式并将 decompression-bomb 当作拒绝。PDF 复用现有 `PDFStreamValidator`。草稿只保存有界 manifest，不通过未验证哈希提前返回成功报告。流式接收采用短事务预检和发布，中间不持有 get_db 的 SQLite 锁；发布前重新核验 session、空间和草稿版本，失败清除 staging 文件。上传原始数据保持 64 KiB 有界写入，不接受客户端本地路径。
- [ ] **Step 4:** 实现 capabilities、create、PUT、list、detail、download、DELETE draft 路由并注册；capabilities 不调用模型。总字节、附件顺序／数量和 hashes 服务端重新计算；`verified_files_digest` 仅在完整接收后的 Task 7 start 内发布，唯一冲突返回真实已存在诊断并丢弃重复草稿文件。分页默认 20、最大 100，cursor 严格校验并绑定空间。
- [ ] **Step 5:** Run `.venv/bin/pytest backend/tests/exams/test_uploads.py backend/tests/exams/test_queries.py backend/tests/test_upload_limits.py backend/tests/test_materials.py -q`，通过后提交 `feat: add bounded exam uploads and private file access`。

### Task 3: 用户模型图片能力及多输入试卷协议

**Files:** Modify `backend/app/providers/{base,native,fake_files}.py`, `backend/tests/test_native_files.py`; Create `backend/app/providers/probe_image.py`, `backend/tests/exams/test_provider.py`。

**Interfaces:** `base.py` 定义 `ExamInput(attachment_id: str, mime_type: str, file_ref: str | None = None, data_url: str | None = None)`；适配器新增 `async analyze_exam(inputs: list[ExamInput], task: dict, *, max_output_tokens: int) -> dict`。TextOnlyAdapter 默认抛 CapabilityNotSupported，原 `analyze_file()` 保持兼容。图片 caps 为 `image_input`、`supported_image_mime_types`，现有 `supported_mime_types` 仍只表达已测文件 MIME。

- [ ] **Step 1:** 在 `test_provider.py` 写 `test_exam_uses_configured_model_and_ordered_original_inputs`，断言 user model、`store=False`、附件 ID／顺序、图片真实 MIME、PDF file ref；`test_image_probe_requires_actual_random_marker` 由替身解码框架生成图验证 marker 只在图中、未直接写进提示词；分别覆盖 JPEG／PNG 探测通过／失败。原 `test_native_files.py` 替身按输入类型分支，保留原 PDF 内容与清理断言。

最小断言示例（变量由上述具名测试的场景准备）：

```python
assert body["model"] == "user-model"
assert body["store"] is False
assert caps["image_input"] is False  # 返回错误随机标识时
assert caps["file_input"] is True    # 独立通过的 PDF 能力保持可用
```

- [ ] **Step 2:** Run `.venv/bin/pytest backend/tests/exams/test_provider.py backend/tests/test_native_files.py -q`，确认新能力／接口缺失导致失败。
- [ ] **Step 3:** 用 Pillow 生成框架拥有的随机标识探测图，不读取用户正文；每种图片 MIME 读回正确才开放。`analyze_exam()` 复用当前钉住地址的 `_http()` 与 schema 校验，PDF 用 input_file，图片用原生 input_image data URL；只接收框架生成的 data URL，不允许远端 URL。保持原 PDF 6000 token 默认值；试卷用显式有上限输出。为真实响应拒绝 incomplete、半截 JSON、无 output 或错 schema；每次记录 usage。fake_files 增加明确固定试卷场景和 `is_demo=True` 提示，不静默回退。
- [ ] **Step 4:** Run `.venv/bin/pytest backend/tests/exams/test_provider.py backend/tests/test_native_files.py backend/tests/test_providers.py backend/tests/test_materials.py -q`，通过后提交 `feat: support user-model exam vision and capability probes`。

### Task 4: 逐题识别、诊断建议与确定性报告

**Files:** Create `backend/app/exam_diagnostics/{recognition,report}.py`, `backend/tests/exams/{test_recognition,test_report}.py`。

**Interfaces:** `recognition.build_task(attachment_ids: list[str], concepts: list[dict], max_questions: int) -> dict`；`recognition.normalize(raw: ExamRecognition, attachment_ids: set[str], concept_ids: set[str]) -> ExamRecognition`；`async recognition.recognize(adapter, inputs, task, limits) -> ExamRecognition`；`async recognition.advise(adapter, recognition: ExamRecognition, concepts: list[dict], limits) -> ExamAdvice`；`report.summarize(recognition: ExamRecognition) -> dict`。limits 使用现有 `ModelCallLimits`，耗时由 worker 的阶段超时管理。

- [ ] **Step 1:** `test_recognition.py` 写 `test_teacher_marks_take_precedence_and_conflicts_stay_uncertain`，同时覆盖勾叉／数值冲突、缺批改、订正、未知来源 ID 和外空间 key；`test_duplicate_labels_need_section_or_source_disambiguation` 保留跨页明确小问，无法消歧的同题号标记待核对。`test_report.py` 写部分分值另计、父题不重复、缺分为 None、总分冲突并列、覆盖不完整无整卷正确率；`test_truncated_or_nonfinite_output_never_becomes_report` 拒绝半截 JSON 和非有限值。

最小断言示例（变量由上述具名测试的场景准备）：

```python
assert normalized.questions[0].result == "uncertain"  # 勾叉与分数冲突
assert normalized.questions[0].score is None          # 未提供分值
assert summary["correctness_rate"] is None            # 覆盖不完整
```

- [ ] **Step 2:** Run `.venv/bin/pytest backend/tests/exams/test_recognition.py backend/tests/exams/test_report.py -q`，确认缺少规范化／汇总实现导致失败。
- [ ] **Step 3:** 第一阶段只提取老师批改；`normalize()` 对可恢复矛盾降低资格并附原因，对非法来源／越权 key 拒绝整个结构。生成稳定叶子 ID 和 `leaf_order`，不使用题号作为唯一键；不生成综合题的虚构拆分。第二阶段仅接收校验后的数据及现有知识目录，最多 12 条优先建议、每条最多 2000 字；建议只能引用真实叶子 ID／concept key，不可改变得分或状态。单阶段输出最多配置的 32000 tokens，识别持久 JSON 上限 2 MiB、建议上下文上限 512 KiB，超限明确失败；不截断后宣称完整。后端从叶子结果计算 counters、可核实分值合计及正确率：仅完整正确／错误为可判定分母，部分得分另列，不完整覆盖返回 None。
- [ ] **Step 4:** Run `.venv/bin/pytest backend/tests/exams/test_recognition.py backend/tests/exams/test_report.py backend/tests/exams/test_contracts.py -q`，通过后提交 `feat: extract teacher grading and generate traceable exam reports`。

### Task 5: 外部学习证据与时间重放策略

**Files:** Create `backend/app/exam_diagnostics/evidence.py`, `backend/tests/exams/test_evidence.py`; Modify `backend/app/learner/{evidence,bkt}.py`, `backend/app/reviews/state.py`。

**Interfaces:** `evidence.qualify(question: RecognizedQuestion) -> tuple[bool, str | None]`；`evidence.assessment_time(exam_date: date | None, timezone: str, imported_at: datetime) -> tuple[datetime, str]`；`evidence.event_payload(diagnostic_id: str, question: RecognizedQuestion, imported_at: datetime, exam_date: date | None) -> dict`。归一化器接受 `exam_question_imported`，但现有 `ASSESSMENTS` 集合不变；外部 evaluator 固定 `teacher_mark_extraction:v1`，策略为 `evidence_v3_exam`。

- [ ] **Step 1:** `test_evidence.py` 写 `test_only_clear_single_concept_teacher_results_are_observations`，参数覆盖 correct／incorrect／partial／unanswered／uncertain／低识别置信／低映射置信／多个概念／llm_rubric；断言 external 的 unknown 辅助和 difficulty=1、独立答对为 0、多道正确不单独达到 mastered。写同卷同时间按 leaf_order 重放、已知日期回填到旧证据之前、当天中午未到不产生未来事件、unknown 日期带 provenance；显式调用 `apply_memory_event()` 对外部事件返回 None，卡片／due／日志完全不变。

最小断言示例（变量由上述具名测试的场景准备）：

```python
assert state["evidence_count"] == 1
assert state["independent_correct_count"] == 0
assert state["status"] == "learning"
assert memory_after == memory_before
assert review_log_count == 0
```

- [ ] **Step 2:** Run `.venv/bin/pytest backend/tests/exams/test_evidence.py -q`，确认外部事件当前不被接受而失败。
- [ ] **Step 3:** 实现资格和时间函数；事件用 `assessment_item_id="exam:{diagnostic_id}:{leaf_id}"`，不创建虚假的在线 AssessmentAttempt。排序增加统一字符串 `observation_order`，外部为诊断 ID＋零填充 leaf_order，旧事件默认 event_id，保持历史在线排序。BKT 明确处理 unknown 辅助，外部事件不能覆盖资格规则；状态包含日期来源。只有包含外部证据的状态返回 `evidence_v3_exam`，原在线状态和参数版本兼容；FSRS 在归一化前显式排除导入事件。
- [ ] **Step 4:** Run `.venv/bin/pytest backend/tests/exams/test_evidence.py backend/tests/test_bkt.py backend/tests/test_adaptive_state.py backend/tests/test_adaptive_attempts.py backend/tests/test_fsrs.py backend/tests/test_reviews.py -q`，通过后提交 `feat: integrate conservative external exam evidence with BKT`。

### Task 6: 报告、知识状态和计划的原子发布

**Files:** Create `backend/app/exam_diagnostics/publication.py`, `backend/tests/exams/test_publication.py`; Modify `backend/app/learner/report.py`, `frontend/src/LearningReport.jsx`。

**Interfaces:** `async publication.publish(db, space, claim: ExamClaim, recognition: ExamRecognition, advice: ExamAdvice, *, now: datetime) -> ExamDetail` 在调用者拥有的事务内执行且不自行 commit；`publication.py` 内复用 `append_event()`、`rebuild_states()`、`save_plan()`，模型不能写入算法状态。完整 claim guard 在 Task 7 定义，当前先核对字段及版本，不依赖尚未实现的 queue 函数。

- [ ] **Step 1:** `test_publication.py` 构造持久任务与校验结果，`test_report_and_real_states_publish_atomically` 断言有效事件、BKT 概率、动态下一步和报告 before／after 对应；`test_estimator_or_commit_failure_rolls_back_everything` 注入算法失败／事务提交失败，断言无已完成报告和额外证据；重放相同 claim 不重复入库。断言在线作答数、任务完成与复习率不变，单独 `external_imports={diagnostics, effective_evidence, window_basis:"imported_at"}` 统计正确。

最小断言示例（变量由上述具名测试的场景准备）：

```python
assert diagnostic.status != "completed"  # 模拟提交失败后，用新 Session 读取
assert imported_event_count == 0
assert states_after == states_before
assert report["external_imports"]["window_basis"] == "imported_at"
```

- [ ] **Step 2:** Run `.venv/bin/pytest backend/tests/exams/test_publication.py -q`，确认发布接口缺失导致失败。
- [ ] **Step 3:** 同事务锁 user／space／diagnostic／job，核对非删除非归档状态、token、generation、lease 和模型指纹；读取最新学习状态作为 before、插入每题唯一事件、按考试时间设置 occurred_at、重放状态、保存计划及 after，最后标记 completed 并释放活动占位。有效题为零也发布报告，明确无状态更新。模型建议与实际 next_action 分字段保存；不改变学习意图、课堂或每日任务。学习报告按 imported_at 聚合外部导入，错题清楚标来源；前端旧报告兼容缺少新字段。
- [ ] **Step 4:** Run `.venv/bin/pytest backend/tests/exams/test_publication.py backend/tests/test_learning_report.py backend/tests/test_adaptive_concurrency.py backend/tests/test_activity_review_regressions.py -q`，通过后提交 `feat: publish exam reports and learning updates atomically`。

### Task 7: 可恢复 worker、开始／重试／取消和远端清理

**Files:** Create `backend/app/exam_diagnostics/{queue,worker,cleanup}.py`, `backend/tests/exams/{test_jobs,test_concurrency}.py`; Modify `backend/app/api/exams.py`, `backend/app/api/providers.py`, `backend/app/main.py`, `backend/tests/conftest.py`。

**Interfaces:** `queue.start(db, user, space, diagnostic_id, body: ExamStart) -> ExamDetail`；`queue.claim(sessions, now: datetime) -> ExamClaim | None`；`queue.guard(db, claim: ExamClaim, now: datetime) -> ExamJob`；`queue.checkpoint(sessions, claim, stage: str, checkpoint: ExamCheckpoint) -> None`；`queue.retry(db, user, space, diagnostic_id, body: ExamRetry) -> ExamDetail`；`queue.cancel(db, user, space, diagnostic_id) -> ExamDetail`。`async worker.run_claim(app, claim: ExamClaim) -> None`、`async worker.tick(app) -> int`、`async worker.worker(app) -> None`；`cleanup.register_remote(sessions, claim, provider_id: str, ref: str) -> None`、`async cleanup.run(app, job_id: str) -> None`。

- [ ] **Step 1:** `test_jobs.py` 写 `test_restart_resumes_advice_without_uploading_or_recognizing_again`、`test_changed_provider_invalidates_checkpoint_and_requires_consent`、`test_failure_and_cancel_always_schedule_original_provider_cleanup`；`test_concurrency.py` 用可阻塞适配器验证远端阶段能并发完成其他空间写入、双 worker 只有一次发布、过期 token 不能发布、同内容并发 start 只有一份诊断。未来／未知日期和截断输出失败后可恢复，维护锁阻止新写入。

最小断言示例（变量由上述具名测试的场景准备）：

```python
assert calls.count("upload") == 1
assert calls.count("recognize") == 1
assert calls.count("advise") == 2  # 建议阶段第一次失败，重启后重试
assert effective_event_count == 1
assert cleanup_provider_id == original_provider_id
```

- [ ] **Step 2:** Run `.venv/bin/pytest backend/tests/exams/test_jobs.py backend/tests/exams/test_concurrency.py -q`，确认 worker／生命周期路由缺失导致失败。
- [ ] **Step 3:** start 检查附件全部真实核验，通过唯一 verified_files_digest 去重；占用空间活动 slot，绑定 provider 指纹及知识目录指纹，创建租约任务。重试和取消幂等请求摘要独立保存，原键不同内容 409。租约 180 秒；每次 claim 消耗一次尝试，默认最多 3 次，每个远端操作最多 120 秒并在开始前延租；上传引用立即登记，再继续识别。单轮最多 5 个任务、固定 2 秒轮询，可中断关闭；依次 upload → recognize → advise → publish，阶段完成即短事务保存 checkpoint。
- [ ] **Step 4:** 在 worker 的每个 DB 阶段采用与 activity_db 一致的 SQLite 锁／维护标识检查，但同步 ORM Session 不跨线程／事件循环共享；调用 `publication.publish()` 的异步事务在统一 DB 执行上下文内完成。所有远端阶段在事务之外，用 app 用户级 limiter、120 秒总操作超时和现有适配器重试边界；模型／知识目录指纹变更使旧检查点失效，新授权后重新识别，不沿用旧模型建议。失败回滚发布事务后另开短事务记录脱敏错误及释放活动 slot。
- [ ] **Step 5:** 成功／失败／取消均排队 cleanup；引用带原服务商 ID，关联开始时保存的最小加密配置快照（base URL、模型、加密 API Key 和指纹，不保存明文），避免原配置后来编辑使清理发送给新服务商。引用及在途上传 lease 清空后擦除快照；旧 Key 被服务商撤销时保留清理失败提示而非声称成功。迟到上传仅登记清理，不恢复取消的任务。清理可独立重试、可在空间 tombstone 上运行；provider 删除 API 增加未清理引用占用检查，避免凭证提前移除。`main.py` 加 worker 生命周期，测试 fixture 默认关闭 exam worker，专门 worker 测试显式开启。增加 start／retry／cancel API，POST 处理不等待模型。
- [ ] **Step 6:** Run `.venv/bin/pytest backend/tests/exams/test_jobs.py backend/tests/exams/test_concurrency.py backend/tests/test_activity_runtime.py backend/tests/test_streaming_materials.py backend/tests/test_providers.py -q`，通过后提交 `feat: add resumable exam processing and remote cleanup`。

### Task 8: 待核对修订、隔离和空间删除

**Files:** Create `backend/app/exam_diagnostics/review.py`, `backend/tests/exams/{test_review,test_deletion,test_isolation}.py`; Modify `backend/app/api/exams.py`, `backend/app/services/space_deletion.py`, `backend/app/maintenance/reset_learning.py`, `backend/app/api/providers.py`（Task 7 引用保护的最终回归）。

**Interfaces:** `async review.patch(db, user, space, diagnostic_id, question_id, body: ExamQuestionPatch) -> ExamDetail`；`cleanup.erase_space(db, space, storage_root: str) -> None` 由现有删除事务调用，只保存最小远端清理墓碑；`cleanup.purgeable(db, space_id: str) -> bool`、`cleanup.purge(db, space_id: str) -> None` 供维护最终删除使用。

- [ ] **Step 1:** `test_review.py` 写 `test_mapping_only_review_adds_clear_teacher_evidence_once`、`test_manual_correctness_never_upgrades_unclear_marks`、已入库题只读／expected_version 冲突／重复 PATCH 幂等／并发只补入一题；保留原始识别与核对来源，修订重新计算报告统计。`test_isolation.py` 参数化全部 11 类设计 API，两个账号和两个空间越权均 404，且跨空间 cursor 不可读。`test_deletion.py` 阻塞上传／识别后删空间，断言无迟到发布、原卷／报告／新表已清、原服务商引用最终清理。

最小断言示例（变量由上述具名测试的场景准备）：

```python
assert first_patch.status_code == 200
assert repeated_patch.json()["effective_evidence_count"] == 1
assert unclear_patch.json()["effective_evidence_count"] == 0
assert foreign_download.status_code == 404
```

- [ ] **Step 2:** Run `.venv/bin/pytest backend/tests/exams/test_review.py backend/tests/exams/test_deletion.py backend/tests/exams/test_isolation.py -q`，确认核对和清理集成缺失导致失败。
- [ ] **Step 3:** PATCH 使用原始题目识别资格作为不可提升上界，仅修正映射可在原批改清晰时补入；采用 Task 6 相同事务步骤重放 BKT／保存计划，题目 event_id 唯一，版本单调增加。仅显示用户核对的主观结果，不覆盖原始老师标记。取消已完成报告返回 409，首版不增加撤回／删除成功报告接口。
- [ ] **Step 4:** 删除按 user → space → diagnostic → job 固定锁序，取消／fence 活动任务，删除本地 `exams/` 空间子目录及题目报告，只留必要 provider／ref／lease 墓碑；维护清空扩展 cleanup job 执行、pending 统计及 purge 判断，不能因旧 MaterialAsset 已清理而提前删 space。旧 lease 未到期也阻止最终 purge，以接收迟到远端引用；归档或登录失效后的附件发布失败并清理 staging。
- [ ] **Step 5:** Run `.venv/bin/pytest backend/tests/exams/test_review.py backend/tests/exams/test_deletion.py backend/tests/exams/test_isolation.py backend/tests/test_space_management.py backend/tests/test_reset_learning.py backend/tests/test_activity_deletion.py -q`，通过后提交 `feat: add exam review and complete deletion isolation`。

### Task 9: Web 上传、报告及状态刷新

**Files:** Create `frontend/src/{ExamDiagnostics,ExamUpload,ExamReport}.jsx`, `frontend/src/examDiagnosticState.js`, `frontend/src/examDiagnosticState.test.js`; Modify `frontend/src/main.jsx`, `frontend/src/styles.css`。

**Interfaces:** `ExamDiagnostics({root, concepts, onStateChanged})` 管理历史／选中诊断／轮询；`ExamUpload({root, capabilities, onCreated})` 管理 manifest／顺序／授权；`ExamReport({root, diagnostic, concepts, onUpdated})` 展示报告和核对。`createExamDiagnosticState({api, makeKey, hashFile})` 产生 `upload(root, files, metadata, consent, onCurrent)`、`poll(root, id, onCurrent)`、`patch(root, id, questionId, changes, onCurrent)`、`invalidate()`；辅助方法在动作开始保存 scope generation 和幂等 key，后续步骤均检查作用域。

- [ ] **Step 1:** 在 `examDiagnosticState.test.js` 使用 Node test 写 `test_upload_starts_only_after_all_attachments`、失败重试复用原 key／附件、用户排序与服务端回传顺序一致、相同 timestamp 分页去重、`test_switching_space_stops_late_upload_poll_and_callbacks`、`test_patch_keeps_version_and_does_not_locally_increment_mastery`。API 替身验证 create → PUT 全部 → start 顺序，上传失败绝不 start，重复上传返回既有报告。

最小断言示例（变量由上述具名测试的场景准备）：

```javascript
assert.deepEqual(calls.map((c) => c.step), ["create", "put", "put", "start"]);
assert.equal(staleScopeCallbacks.length, 0);
assert.equal(patchBody.expected_version, 2);
```

- [ ] **Step 2:** Run `node --test frontend/src/examDiagnosticState.test.js`，确认状态模块缺失导致失败。
- [ ] **Step 3:** 实现状态模块，文件哈希默认用 `crypto.subtle.digest`，最多按一个文件串行读取，避免并行复制全部原卷；服务端仍独立核对。一次上传操作串联三步协议；轮询仅在 queued／running 时每 2 秒启用，结束后停止。刷新恢复历史及任务，失效或卸载释放 timer／object URL，晚到失败也不能污染新页面。服务端 completed／PATCH 成功后按版本仅触发一次 `onStateChanged()`。
- [ ] **Step 4:** 新增「成绩诊断」侧栏及标题映射，`ExamDiagnostics` 使用 `key={root}` 隔离空间，刷新回调复用当前空间 detail／plan／concepts 的读取路径。上传显示实际模型、能力限制、文件顺序、日期及传输授权；演示明确“固定样例，未读取上传内容”。报告展示原卷／逐题依据、五种结果、分值冲突／覆盖情况、真实知识变化和未计入原因，待核对编辑带预期版本；未知辅助显示“未知”，不得标为提示作答。图片局部安全预览，PDF 用授权原文下载；390px 单栏、键盘可操作、文字辅助状态颜色。
- [ ] **Step 5:** Run `npm --prefix frontend test` 和 `npm --prefix frontend run build`，全部通过；用 CUA 或可用浏览器工具在隔离演示环境检查桌面和 390px 上传／处理中／成功／核对／失败重试，截图存于 `/private/tmp/study-agent-exam-qa/`，不启动或改动用户正式服务。通过后提交 `feat: add exam diagnostics upload and report interface`。

### Task 10: 端到端验收与使用文档

**Files:** Create `backend/tests/exams/test_e2e.py`, `docs/exam-diagnostics.md`; Modify `README.md`, `README.en.md`, `docs/api.md`, `docs/openapi.json`, `docs/architecture.md`, `docs/security.md`, `docs/acceptance.md`, `docs/usage.zh-CN.md`。

**Interfaces:** 不增加新业务接口；验收使用此前任务的公开 API、`worker.tick(app)` 与现有 progress／plan／report／reviews，明确运行时迁移和模型重新检测要求。

- [ ] **Step 1:** 写 `test_pdf_and_images_update_shared_state_after_restart`：隔离账号先上传一份有明确对错／部分得分／模糊批改的样卷，tick 完成后重建 app；核验诊断历史、实际知识状态、报告、下一步一致，在线任务及 FSRS 无变化；再重复上传／重排照片不重复证据；核对映射补入一次。写 `test_failed_publish_retry_keeps_report_and_state_consistent` 注入一次提交失败，重试后恰好发布一次；固定样例不得宣称识别质量。

最小断言示例（变量由上述具名测试的场景准备）：

```python
assert restored_detail["effective_evidence_count"] == original_detail["effective_evidence_count"]
assert duplicate_detail["id"] == original_detail["id"]
assert restored_review_cards == original_review_cards
```

- [ ] **Step 2:** Run `.venv/bin/pytest backend/tests/exams/test_e2e.py -q`；若此前实现存在缺口，先确认失败证据，再做任务范围内最小修正并重跑受影响测试。
- [ ] **Step 3:** 编写中文使用文档和 README 入口，说明用户模型、已验证格式、三步协议对用户为一次操作、历史日期和更新资格、待核对边界、费用／传输、重复扫描限制、真实模型尚需验收。更新 API／架构／隐私和验收记录；通过 `create_app()` 生成 OpenAPI JSON，不凭手写声明接口完成。不编写与实际能力不符的成功示例。
- [ ] **Step 4:** Run `./scripts/check.sh`，要求 Ruff、格式、Shell 语法、后端全套测试、前端测试与生产构建全绿。迁移测试使用临时数据库；如已有专用 `TEST_DATABASE_URL` 再跑 PostgreSQL 相关测试，未提供时标注未验证，不创建或触碰生产库。新失败先使用 systematic-debugging 技能定位，不能修改无关断言掩盖失败。
- [ ] **Step 5:** 按 verification-before-completion 和 requesting-code-review 技能完成新鲜验证与审查，记录真实执行结果及未验收项；只提交本功能增量和文档 `docs: document and verify graded exam diagnostics`。不自动部署、推送或合并；最终报告说明入口、学习状态更新规则、测试证据及真实 BYOK 验收范围。

## 依赖、自审与执行交接

任务按 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 顺序执行；整个功能是一条持久化学习流程，不拆成彼此无法使用的独立子项目。暂不请求并行实现，共享接口以各任务 Interfaces 为准。

自审覆盖：设计第 1–4 节由任务 1–4／9 实现；第 5 节由任务 5–6 实现；第 6 节由任务 1–2／7–8 实现；第 7 节全部路由由任务 2／7／8 接入，第 8 节由各任务测试和任务 10 验收覆盖。Review Focus 五项均已落入具名测试；没有未定义阶段接口或占位步骤。任务完成的认定以实际测试输出为准，当前所有复选框保持未完成。

计划待用户审阅并选择执行方式：Native（本会话逐项实现，最后独立审查）或 Subagent-driven（逐任务实现与独立审查）。推荐 Native，因为数据库、任务租约、模型检查点和证据发布接口紧密相连，连续实现更容易保持一致；选择执行方式后再进入对应执行技能。
