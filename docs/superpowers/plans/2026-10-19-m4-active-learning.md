# M4 Active Learning and Accounts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 后台自动整理每日任务、站内消息和自然周报，提供手动AI分析、运行及用量视图，完善登录页面，并让全部数据严格按账号隔离。

**Architecture:** SQLAlchemy持久队列负责无模型的周期任务；纯数据计算与自有Session事务分离。手动AI分析使用准备／远端／发布三阶段与账号级配额。Web和CLI共用鉴权API，复用现有BKT／FSRS、课堂及诊断服务。

**Tech Stack:** Python3.12、FastAPI、SQLAlchemy／Alembic、SQLite／PostgreSQL、zoneinfo、React／Vite、现有argparse CLI；不新增Redis、Celery或登录框架。

**Spec:** [已确认M4设计](../specs/2026-10-19-m4-active-learning-design.md)，提交 `4a52b14`。用户已于本会话确认文档，本实施计划待审阅／选择执行方式。

## Global Constraints

- “后台使用已有学习数据生成待办和统计周报；LLM分析仅由用户点击触发。”后台协调、周报、通知必须零模型调用。
- “取消新增‘提醒设置’和‘授权与数据控制’模块”；不新增邮件／短信／微信／系统通知、授权／暂停中心或数据导出。现有鉴权、退出和删除保留。
- “现有账号、学习资料和记录继续保留，不重新执行M3清空操作。”真实服务与真实库不用于试验，不启动第二个8000后台，不调用付费模型验收。
- 调度默认每60秒；三次执行尝试，失败退避30秒、120秒；只补当前日期和最近一个已结束自然周。
- 每空间当日主动安排最多6项，建议时长之和不超过daily_minutes；所有空间继续启用原生BKT／FSRS，待办处理不改写能力／卡片日期。
- 每账号每UTC日默认10次M4分析尝试、100000 Token预算、每次最多1500输出Token。统计标明只覆盖M4分析，金额不可用时不虚构费用。
- 所有新公开输出使用Pydantic响应模型；所有对象以认证账号推导归属，跨账号404、未登录401；GET无写入／模型调用。
- 当前分支 `codex/m4-active-learning-accounts`，HEAD `4a52b14` 加既存未提交M2／M3／Chat／脑图。沿用已建立的功能分支，不从HEAD另建丢失依赖的工作树；禁止reset、clean、批量暂存及推送。共享旧文件的修改保留完整工作区diff，不能为了逐任务提交混入历史代码；独立新文档可单独提交。

## Review Focus

1. 两账号猜测子对象ID／复用请求键及父子空间错配，应始终404且不改他人数据；任务1／10覆盖数据库约束与API全域矩阵。
2. 模型等待时登出、删空间、过期租约或换账号，迟到结果不得发布内容或退款为零消耗；任务6／7／10覆盖。
3. DST、时区变更、服务离线跨周、并发worker，应只产生一个当前周期结果且保留已读状态；任务2／4／5覆盖。
4. 同日Chat调整、已完成／改期任务与复习周期变化，不得重复排程、误认完成或超预算；任务3／4覆盖。
5. 多空间同时分析、供应商缺usage或内部重试，不能绕过账号共享配额或静默重复付费；任务6覆盖真实HTTP协议替身和并发。

---

## File Structure and Shared Types

新增 `backend/app/activity/`：`contracts.py`（冻结快照／结果）、`calendar.py`（日周时间）、`db_phase.py`（自有Session执行边界）、`queue.py`（认领／租约／重试）、`scheduler.py`（周期入队）、`worker.py`（生命周期）、`snapshot.py`（读取本人空间纯快照）、`daily.py`（纯排程／协调）、`tasks.py`（任务执行）、`suggestions.py`、`inbox.py`、`weekly.py`、`analysis.py`、`quota.py`、`presentation.py`（分页／输出投影）。新HTTP入口为 `api/activity.py` 与 `api/analyses.py`；请求和响应模型为 `schemas/activity.py`、`schemas/analyses.py`。

`Session`仅在拥有它的线程使用；`now`均为aware UTC datetime。冻结dataclass至少定义：

- `CalendarPeriod(key: str, timezone: str, start: datetime, end: datetime, warning: str|None)`。
- `ActivitySnapshot(user_id: str, space_id: str, now: datetime, intent: dict, concepts: tuple[dict,...], states: dict, memory: dict, events: tuple[dict,...], active_lesson: dict|None, tasks: tuple[dict,...], fingerprint: str)`；禁止凭证或ORM实例。
- `JobClaim(job_id: str, token: str, user_id: str, space_id: str, kind: str, period_key: str, generation: int)`。
- `PreparedAnalysis(run_id: str, user_id: str, space_id: str, session_hash: str, lease_token: str, source_fingerprint: str, provider_snapshot: ProviderSnapshot, payload: dict, reserved_tokens: int, budget_date: date)`；凭证字段禁止repr。

## Task 1: Ownership, Schema and Incremental Migration

**Files:** 创建 `activity/{__init__,contracts}.py`、`schemas/{activity,analyses}.py`、`migrations/versions/0006_active_learning.py`、`tests/test_activity_contracts.py`；修改 `db/models.py`、`tests/test_migrations.py`。

**Interfaces:** ORM为 `PeriodicJob / DailyPlan / DailyTask / LearningSuggestion / InboxMessage / WeeklySummary / AnalysisRun / AnalysisDailyUsage`。公共响应至少有 `DailyPlanResponse / DailyTaskResponse / TaskStartResponse / SuggestionResponse / InboxResponse / WeeklySummaryResponse / ActivityJobResponse / AnalysisResponse / AnalysisUsageResponse`，列表包装为对应Page，字段 `items` 与 `next_cursor`。`DailyPlanResponse.slots`为 `TaskAllocation(task: DailyTaskResponse,allocated_minutes: int,carried_over: bool)` 列表，backlog单独返回；`TaskStartResponse`仅返回 `task / execution_kind / lesson_id / item_ids`，不直接透传原始题目或参考答案。

- [ ] 写失败测试：`test_activity_child_cannot_reference_other_users_space`、`test_task_cannot_reference_another_spaces_plan_or_lesson` 验证复合外键；`test_cycle_keys_and_utc_usage_bucket_are_unique` 验证唯一约束；`test_public_contract_rejects_internal_lease_and_credentials` 验证未知字段拒绝。
- [ ] 运行 `.venv/bin/pytest backend/tests/test_activity_contracts.py -q`，确认因新模型／约束尚不存在而失败。
- [ ] 实现模型及DTO：空间实体统一 `(user_id,space_id)` 复合归属；计划唯一 `(space_id,local_date)`，周报唯一 `(space_id,week_start)`，消息唯一 `(space_id,event_key)`，分析唯一 `(space_id,idempotency_key)`，日配额唯一 `(user_id,utc_date)`。任务关联计划／课堂均带space_id；题目ID列表在服务层逐项校验归属。
- [ ] `PeriodicJob`保存kind（`daily_coordinate`／`weekly_summary`）、period_key、generation、status、available_at、lease_until、lease_token、attempts、executions、input_version及脱敏错误；唯一 `(space_id,kind,period_key)`。DailyTask保存task_key、concept_ids、action、estimated_minutes、status、blocking_reason、lesson_id、item_ids、review_cycle_key、active_cycle_key、postponed_until、origin_task_id；同空间任务键唯一，`(space_id,active_cycle_key)` nullable唯一避免同一复习周期两个活动任务。DailyPlan保存分配快照(task_id、allocated_minutes)，引用ID仅能来自本人同空间；DailyTask保留最初所属计划供历史统计。
- [ ] 用临时0005库生成／审阅迁移0006；`test_m4_upgrade_preserves_existing_accounts_and_learning` 比较升级前后账号、密文、事件、课堂和卡片，`alembic check` 确认metadata一致。运行新测试与 `test_migrations.py`，均通过后审阅本任务diff并登记；不暂存共享旧文件。

## Task 2: Calendar, Durable Queue and Recovery

**Files:** 创建 `activity/{calendar,db_phase,queue,scheduler,worker}.py`、`tests/test_activity_queue.py`；修改 `core/settings.py`，暂不挂接应用启动。

**Interfaces:** `local_day(now: datetime, timezone: str) -> CalendarPeriod`、`previous_week(now,timezone) -> CalendarPeriod`；`enqueue_cycles(session_factory, now) -> int`；`claim_job(session_factory,now) -> JobClaim|None`；`finish_job(session_factory,claim,now,error: ProviderError|None) -> bool`；`retry_activity_job(db,user_id,job_id,now) -> ActivityJobResponse`；`async activity_db(app, fn, *args, write=True)`；`async process_once(app,now) -> bool`、`async worker(app)`。处理器最终由任务11接入，队列单测注入无网络处理器。

- [ ] 写失败测试，固定UTC时钟：上海当地00:00与纽约DST周边界；无效时区返回Shanghai及warning；停机20天只入当前日和最近已结束周；相同当地日期换时区不重复建周期；`test_expired_lease_cannot_publish_after_second_worker_claim` 验证旧token失效。
- [ ] 运行 `.venv/bin/pytest backend/tests/test_activity_queue.py -q` 确认失败。

  固定日界线断言（其余用例同样用手工给定的UTC区间作期望）：
  ```python
  period = local_day(datetime(2026, 10, 19, 16, 0, tzinfo=UTC), "Asia/Shanghai")
  assert period.key == "2026-10-20"
  assert period.start == datetime(2026, 10, 19, 16, 0, tzinfo=UTC)
  assert period.end == datetime(2026, 10, 20, 16, 0, tzinfo=UTC)
  ```
- [ ] 实现日／周左闭右开UTC区间。每天一个daily协调job，成功后设置下一available_at为now+60秒；到时原子重置queued、attempts=0并增加generation以再次协调，复用同一周期行。周报job成功后不再次认领；dead_letter不因定时扫描自动复活。
- [ ] 实现queued→running→succeeded／retry_wait／dead_letter／cancelled；每次认领attempts加1、租约180秒，失败分别30秒、120秒重试，第3次失败死信。失效空间取消；成功发布必须匹配token、generation、状态及未过期租约。只认领job的事务不同时持有User／Space锁；发布锁顺序User→Space→Job。
- [ ] PostgreSQL认领使用短事务 `FOR UPDATE SKIP LOCKED`，SQLite仅在短DB阶段取得应用锁。维护标记存在时暂停入队／发布；worker有限等待退出，无ORM跨线程。运行队列测试及带两个并发claim者的PG检查，验证唯一结果、死信和显式retry，不调用模型。
- [ ] 审阅日／周键、事务、租约和重试边界并登记；应用生命周期留待任务11，避免启用尚未接入的业务处理器。

## Task 3: Daily Plans, Execution and Evidence-Based Completion

**Files:** 创建 `activity/{snapshot,daily,tasks,presentation}.py`、`api/activity.py`、`teaching/diagnostics.py`、`tests/test_daily_plans.py`；修改 `api/learning.py`、`teaching/attempts.py`（仅必要协调触点）。

**Interfaces:** `read_snapshot(db,space,now) -> ActivitySnapshot`；`build_daily_plan(snapshot: ActivitySnapshot, period: CalendarPeriod) -> DailyPlanResponse`（纯计算）；`coordinate_day(session_factory,user_id,space_id,now) -> DailyPlanResponse`；`async start_daily_task(request,db,space,task_id) -> TaskStartResponse`；`set_task_disposition(db,space,task_id,status: Literal['skipped','postponed'],now) -> DailyTaskResponse`；`refresh_completion(db,space,now) -> int`；提取 `async ensure_diagnostics(request,db,space) -> dict` 供原路由及任务开始共用。

- [ ] 写失败测试：30分钟预算的主动任务不超过6项且总时长≤30；未掌握先修不排后继；既有课堂恢复相同lesson／题ID；2个待安排到期项不重复计入预算；Chat意图更新后已开始／完成／跳过项保留，未开始的离范围项superseded。
- [ ] 写 `test_task_completion_requires_real_linked_work`：仅读课堂仍未完成、全部练习提交才完成；诊断任务必须其关联整批题均提交；skip／postpone前后BKT及FSRS JSON完全一致；同复习周期改期后最多1个可执行待办。运行 `.venv/bin/pytest backend/tests/test_daily_plans.py -q` 确认失败。
- [ ] 写跨日继续测试：昨天in_progress任务今天进入carryover slot，task_id和最初plan_id不变；今天分配分钟可以小于整课估计，完成后只产生一次任务／课堂完成记录。昨日未开始的到期任务滚动时旧项postponed并清active_cycle_key，新项链接origin_task_id；不产生两个可执行周期任务。
- [ ] 实现纯排程，复用policy与scope／priority，不模拟未来掌握。活动课堂优先；主行动后按到期和稳定key填充可执行复习，预算不足或先修不足留backlog并给原因。来源指纹覆盖意图、课程、状态、卡片周期、活动课堂、已有任务；写阶段重读版本，冲突不覆盖新状态。
- [ ] 实现开始事务，稳定键 `m4_task_<task_id>`。LEARN／PRACTICE／ASSESS／REMEDIATE使用既有课堂服务，REVIEW使用start_review；DIAGNOSE共用ensure_diagnostics、登记已有完整诊断批次ID。先检查实际当前状态，目标已变返回409；另一活动课堂优先恢复，不冒称启动了别的知识任务。复用原公共presentation，禁止将答案／rubric写入新响应。
- [ ] 新路由：`GET /study-spaces/{id}/daily-plans/today`（无记录返回plan=null及reason）、`POST /daily-plans/refresh`（显式无模型协调）、`GET /tasks?status=`、`POST /tasks/{tid}/start|complete|skip|postpone`。所有写请求带幂等键，postpone仅允许下一个当地日期。GET不协调／创建事件；DTO明确响应。
- [ ] 运行新测试及 `test_reviews.py test_adaptive_attempts.py test_planning_intent.py test_e2e.py`；验证原diagnostics路由行为未改，重复task-start只调用一次生成，失败回滚不产生孤儿关联。审阅并登记diff。

## Task 4: Deviation Suggestions and Inbox

**Files:** 创建 `activity/{suggestions,inbox}.py`、`tests/test_activity_suggestions.py`；修改 `api/activity.py`、`schemas/activity.py`、`activity/daily.py`。

**Interfaces:** `derive_suggestions(snapshot,period) -> list[SuggestionResponse]`；`publish_suggestions(db,space,candidates,now) -> None`；`apply_suggestion(db,space,suggestion_id,decision: Literal['accept','skip'],now) -> SuggestionResponse`；`put_message(db,space,event_key,kind,source_id,summary,now) -> InboxResponse`；`list_inbox(db,user_id,cursor,limit) -> InboxPage`、`read_message(db,user_id,message_id,now) -> InboxResponse`。

- [ ] 写失败测试：最近学习3个当地日期以前产生中断建议；从未学习不能虚构中断；至少2项旧未完成任务或复习建议时长超预算产生堆积建议；接受后只拆分／减量待办，跳过／接受都不改space.daily_minutes、目标、证据和卡片。
- [ ] 写并发／重复协调测试：相同空间当地日期仅1条到期摘要，新增到期项更新摘要但保留read_at；重启不重复通知；其他账号读／标已读返回404；旧建议指纹与新Chat版本不符返回409。运行 `.venv/bin/pytest backend/tests/test_activity_suggestions.py -q` 确认失败。
- [ ] 实现pending／accepted／skipped／expired状态，接受时检查source_fingerprint及当前预算。建议操作明确为减少当日未开始项目／将溢出项目改期，不修改总需求。站内事件键固定 `due:<local_date>`、`deviation:<reason>:<period>`、`weekly:<week_start>`。
- [ ] 新路由：`GET /study-spaces/{id}/suggestions`、`POST /suggestions/{gid}/accept|skip`、`GET /inbox?cursor=&limit=`、`POST /inbox/{mid}/read`、`GET /inbox/unread-count`、`GET /activity-jobs?cursor=&limit=`、`POST /activity-jobs/{jid}/retry`（只允许本人dead_letter的非付费作业）。来源类型只允许daily_plan／suggestion／weekly_summary，链接由前端固定映射；分页默认30最大100，稳定(created_at,id)游标且校验账号作用域。
- [ ] 运行本任务及daily测试，验证消息与其来源在同一事务发布，失败无孤儿消息；审阅并登记diff。

## Task 5: Natural-Week Reports and Transparent Forecasts

**Files:** 创建 `activity/weekly.py`、`tests/test_weekly_summaries.py`；修改 `activity/suggestions.py`、`api/activity.py`、`schemas/activity.py`。

**Interfaces:** `summarize_week(snapshot,period,weekly_progress: tuple[dict,...]) -> WeeklySummaryResponse`；`forecast_goal(remaining: int, complete_week_gains: list[int],as_of: datetime,target_date: str|None) -> GoalForecast`；`publish_week(session_factory,user_id,space_id,period,now) -> WeeklySummaryResponse`。GoalForecast含status、remaining_concepts、sample_weeks、weekly_gains、earliest／latest、reason、uncertainty，不含未经校准成功概率。

- [ ] 写失败测试，固定自然周：事件恰在end的归入下周；无分母rate=null；有效／辅助／待核实计数分开；历史报告按当时scope与版本快照保存，不随随后Chat改目标变动。运行 `.venv/bin/pytest backend/tests/test_weekly_summaries.py -q` 确认失败。
- [ ] 实现周内开始且完成任务的分母、独立可靠复习保持率、前后BKT重放与错误摘要；只向纯计算线程传snapshot。历史前后状态只能用period.start／end之前的事件重放，不能复用当前缓存把下一周答案算入旧周；用生成时scope统计并保存版本。增加晚于周末的可靠答题不会改变既有周报的回归，原事件和FSRS日志不可更新。
- [ ] 预测测试固定字面预期：剩余8个概念、完整周净增[2,4]得到2至4周范围；[0,4]、[-1,4]或只有[4]返回不足数据；remaining=0返回当前范围已达标。只取最近28天内完整周，不过滤零／负增长来缩窄范围；不足数据的风险建议直接说明依据不足。

  ```python
  result = forecast_goal(8, [2, 4], datetime(2026, 10, 19, tzinfo=UTC), None)
  assert result.earliest == date(2026, 11, 2)
  assert result.latest == date(2026, 11, 16)
  assert forecast_goal(8, [0, 4], datetime(2026, 10, 19, tzinfo=UTC), None).status == "insufficient_data"
  ```
- [ ] 新路由：`GET /study-spaces/{id}/weekly-summaries?cursor=&limit=`、`GET /weekly-summaries/{wid}`、`GET /weekly-summaries/current`（纯统计预览）、`POST /weekly-summaries/refresh`（显式协调最近已结束周，无LLM）。周报唯一键冲突返回已存结果，消息只发布一次。
- [ ] 运行本任务、daily／suggestion／learning_report测试，断言GET事件／模型调用计数不变，保留原7／30天报告。审阅并登记diff。

## Task 6: Explicit AI Analysis and Account-Level Quotas

**Files:** 创建 `activity/{analysis,quota}.py`、`api/analyses.py`、`tests/test_activity_analysis.py`、`tests/test_activity_analysis_concurrency.py`；修改 `schemas/analyses.py`、`providers/{base,compatible,fake}.py`、`core/orchestrator.py`、`core/settings.py`。

**Interfaces:** `providers/base.py` 新增冻结 `ModelCallLimits(max_output_tokens: int, retries: int)`，`get_adapter(request,config,*,call_limits: ModelCallLimits|None=None)` 保留旧调用默认值；CompatibleAdapter实例输出上限默认为原6000，M4实例为1500且retries=0，NativeFileAdapter继承聊天行为。`reserve_usage(db,user_id,utc_date,run_id,tokens,limits) -> None`、`settle_usage(db,run,usage: dict|None,now) -> None`；`prepare_analysis(session_factory,session_hash,space_id,body,now) -> PreparedAnalysis|AnalysisResponse`、`publish_analysis(session_factory,prepared,call,now) -> AnalysisResponse`、`async send_analysis(app,session_hash,space_id,body) -> AnalysisResponse`。

- [ ] 写失败测试：查询／后台worker模型计数0；只有POST分析发模型请求；跨空间共用账号10次上限；两个并发大请求不能超过100000预留；重复幂等键只占1次，失败后显式新尝试才再占次数。运行新分析测试确认失败。
- [ ] 固定请求体上限48000 UTF-8字节（含真实系统提示、schema和序列化元数据），先裁剪概念／统计摘要，仍超限返回422且不占quota；预留完整字节长度+1500。新增供应商usage_reported标记区分真实0和未返回；不得把现有初始零usage当作已知免费。
- [ ] HTTP协议替身测试必须断言 `max_tokens=1500`、最多1个远端HTTP请求、错误JSON不二次修复、timeout不二次请求；一般教学仍沿用原重试及输出上限。Fake离线分析有固定样例和明确demo标志，失败不得自动回退Fake。
- [ ] 实现准备／等待／发布，180秒租约、90秒模型总时限；配额事务顺序User→Space→AnalysisRun→DailyUsage。模型上下文仅本人当前空间受限统计；结构输出为 `summary(max4000) / recommendations(max6,每项max1000) / caveats(max6)`，不允许计划补丁、工具执行或跨空间ID。AnalysisRun支持processing／completed／failed／conflict／cancelled，错误保存实际用量或未知保守占用。
- [ ] 新路由：`POST /study-spaces/{id}/analyses`，body为source_kind（daily_plan／weekly_summary）、source_id、idempotency_key；`GET /analyses/{aid}`、`GET /analyses?cursor=`；账号级 `GET /analysis-usage`。失败重试POST携带新的幂等键与retry_of原分析ID，相同重试键不重复付费。无HTTP自动付费retry路由。
- [ ] 并发测试验证远端等待时health和普通作答可用；登出、删空间、来源版本／模型配置变化、旧租约返回均不发布分析，已发生消耗不退款；实际usage缺失或超时仍占保守额度，UTC次日新桶，换时区不获得第二桶。完整运行供应商、Chat和分析相关测试后审阅登记。

## Task 7: Login and Registration Routes with Session-Scope Invalidation

**Files:** 创建 `frontend/src/{AuthPage.jsx,authRouting.js,authRouting.test.js}`、`backend/tests/test_auth_pages.py`；修改 `frontend/src/{main.jsx,api.js,api.test.js}`、`backend/app/main.py`。

**Interfaces:** `authRoute(pathname: str) -> 'login'|'register'|'workspace'`、`navigateAuth(mode: str,{replace: bool}) -> void`（仅本地固定路径）；api新增 `advanceSessionScope() -> number` 及可取消的401订阅函数 `onSessionExpired(handler) -> unsubscribe`，每次请求捕获世代，旧世代401不通知。函数不存储密码／Cookie。抽取AuthPage({mode,onModeChange,onLogin,config})。

- [ ] 先写失败测试：无dist时静态路由不假装成功；有临时dist时GET /login及/register刷新返回index，GET /api/v1/不存在仍404；authRoute只接受固定三类路径；账户A的401不得清空随后账户B的新会话。
- [ ] 运行 `.venv/bin/pytest backend/tests/test_auth_pages.py -q` 与 `npm --prefix frontend test` 确认失败。
- [ ] 只为 `/`、`/login`、`/register`提供SPA入口，不加入吞掉任意API的catch-all；React监听popstate并用history保持登录／注册切换和前进后退一致。有效会话访问登录页replace到工作台；未登录／当前会话401replace到/login。
- [ ] 统一会话世代：每次请求捕获世代，登出／登录成功后递增并失效旧读；只有当前世代401触发退出。退出撤销失败保持当前账号并提示错误；成功后清空模型、空间、Chat和所有M4状态。表单清理密码、注册确认、autocomplete、输入校验及重复提交防护保持原功能。
- [ ] 运行auth／e2e／前端全套测试；使用临时账号验证注册→登录→退出→另一账号→浏览器后退，旧资料不出现。审阅并登记diff。

## Task 8: Web Daily Workbench, Inbox, Weekly Summary and Operations

**Files:** 创建 `frontend/src/{DailyTasks,Inbox,WeeklySummaries,ActivityRuns,AIAnalysis}.jsx`、`activityState.js`、`activityState.test.js`；修改 `main.jsx`、`styles.css`、`LearningReport.jsx`（仅添加自然周入口）。

**Interfaces:** 所有页面以 `scopeKey=user.id+':'+sid` 建立请求作用域；DailyTasks({root,onStarted})的onStarted接TaskStartResponse：lesson调用refreshSpace并进入classroom；diagnostic复用既有POST /diagnostics读取已建批次后进入classroom。AIAnalysis({root,sourceKind,sourceId})明确点击才POST，202处理中每2秒GET轮询，卸载清理。

- [ ] 先写失败行为测试：重复开始共用请求键；读取旧账号A／空间A的响应不能覆盖B；AI分析按钮之外不POST；重试使用新的尝试键但重复点击同一次重试复用键。沿用现有node:test，无需为布局样式添加镜像测试。
- [ ] 运行 `npm --prefix frontend test` 确认新增测试失败。
- [ ] 实现今日日期／预算、任务状态、backlog和依据；待办完成请求只核对服务端条件。建议accept／skip显示真实改变；站内消息有未读数和已读操作，链接按受控source类型路由。
- [ ] 实现自然周预览／历史选择、统计分子分母、预测范围及不足数据原因，保留滚动报告；运行页展示本人作业／错误／重试和配额，分析显示实际／预留／未知Token、适用范围及货币不可用说明。副作用写入后刷新失败提示已保存，避免用户重复分析。
- [ ] 新侧栏今日任务、站内消息、学习周报／现有报告内切换、后台运行入口；不出现取消范围的设置页。桌面／390px验证无页面横向溢出，键盘可访问，分析文本按纯文本渲染。
- [ ] 运行前端全套及生产构建，临时服务验证点击待办恢复原课堂、建议处理、消息已读、空周报、定位周报分析、刷新恢复；保存真实截图供README和最终交付，审阅登记diff。

## Task 9: CLI Entry Points Over the Same APIs

**Files:** 修改 `backend/app/cli/{main,render}.py`；创建 `tests/test_cli_activity.py`；更新 `docs/cli.md`。

**Interfaces:** 命令 `today [--refresh]`；`task list|start ID|complete ID|skip ID|postpone ID`；`suggestion list|accept ID|skip ID`；`inbox list|read ID`；`weekly list|show ID|current|refresh`；`analyze --source daily_plan|weekly_summary --source-id ID [--retry-of ID] [--request-id KEY]`；`analysis list|show ID`；`activity-jobs list|retry ID`；`analysis-usage`。空间命令统一支持既有--space／--json，账号级消息／配额不接受客户端user_id。

- [ ] 先写失败测试覆盖端点、分页、相同请求键重试、JSON和中文输出；`today`／`weekly current`／`analysis-usage`不得发模型POST；只有明确analyze才申请付费分析。
- [ ] 运行 `.venv/bin/pytest backend/tests/test_cli_activity.py -q` 确认失败。
- [ ] 实现解析和映射，postpone固定下一个当地日期由服务端计算；task start返回课堂／诊断的继续入口，不在本地重算计划。控制字符过滤沿用render安全函数，输出不含密钥或内部租约。
- [ ] 运行全部CLI测试，独立临时HTTP进程验证账号A建计划、Web／CLI读同一任务、start／skip、周报、消息、退出再登录B读取空列表且不能访问A的对象。审阅登记diff。

## Task 10: Deletion, Maintenance and End-to-End Tenant Boundaries

**Files:** 修改 `services/space_deletion.py`、`maintenance/{reset_learning,rebuild_algorithms}.py`（仅新实体兼容与协调版本失效）、`api/providers.py`（分析在途配置删除保护）；创建 `tests/test_activity_isolation.py`、`tests/test_activity_deletion.py`；扩展相关既有删除测试。

**Interfaces:** `cancel_space_activity(db,space,now) -> None` 放 `activity/tasks.py`（取消队列与分析租约），空间删除在FK顺序中先移除新任务／消息／周报／分析正文；AnalysisDailyUsage保留本人无正文聚合计数。普通rebuild-algorithms不生成M4学习证据，后续协调识别参数版本变化。

- [ ] 写失败矩阵：两个账号同名请求键、不同空间／父子错配，覆盖模型配置、空间、题／答案、教材／下载／任务、Chat、M4计划／任务／建议／消息／周报／分析／作业／用量。断言401／404和原数据计数／哈希不变，不仅断言前端隐藏。
- [ ] 写真实租约／迟到模型结果用例：删除空间后所有新内容为零、后台不复活、账号日配额不降低；在途分析所需模型配置不可直接删除；完成／失败后可清理。维护标记阻止协调发布，非付费任务可恢复，付费分析不自动重跑。
- [ ] 运行新测试确认失败；实施删除依赖顺序、归属校验与令牌失效，reset-learning复用共用清理服务并认识新表，但验收只操作临时库。冻结目标不能扩大到后来新建空间。
- [ ] 运行activity、reset、space、materials、Chat及安全测试；临时PostgreSQL验证复合FK、同时删除／发布、并发配额。审阅登记diff，遗留真实学习库保持不变。

## Task 11: Runtime Wiring, Whole-Project Verification and Documentation

**Files:** 修改 `main.py`、`core/settings.py`、`tests/conftest.py`、`.env.example`、`docker-compose.yml`、`StudyAgent_Framework_Development_Spec.md`、`README.md`／`README.en.md`、`docs/{api,architecture,usage.zh-CN,development-roadmap,acceptance}.md`、`docs/openapi.json`；创建 `docs/m4-active-learning.md`、`tests/test_activity_runtime.py`、`scripts/check_postgres.py`。

**Interfaces:** settings最终默认 `M4_WORKER_ENABLED=true`、`M4_TICK_SECONDS=60`、`M4_ANALYSIS_DAILY_CALL_LIMIT=10`、`M4_ANALYSIS_DAILY_TOKEN_LIMIT=100000`、`M4_ANALYSIS_MAX_OUTPUT_TOKENS=1500`、`M4_ANALYSIS_MAX_INPUT_BYTES=48000`。pytest fixtures显式关闭M4 worker，运行时专用测试自行启用。worker将daily_coordinate绑定任务3／4、weekly_summary绑定任务5；注册两个API router，health／config阶段为M4。

- [ ] 先写运行时失败测试：应用进入lifespan立即开始协调，退出不留下循环；停机／重启只恢复当前周期；两个worker只发布一份周报及消息；无供应商或供应商故障时无模型请求且日报／周报可读。
- [ ] 运行runtime测试确认失败；接入生命周期与配置、只传纯快照到计算线程，已有material worker继续独立运行，默认配置新增周期功能不触发模型。运行脚本不清空真实数据、不创建守护进程。
- [ ] 将临时PostgreSQL全套核验封装为可重复脚本，使用现有本机可用原生测试工具或显式TEST_DATABASE_URL；实例／schema测试后自动清理，不下载／连接真实学习数据。执行 `./scripts/check.sh`、PG全套、增量迁移metadata check、静态OpenAPI与内存应用一致性、wheel／sdist构建。
- [ ] 使用一次独立只读最终审查检查跨账号、租约／幂等、配额、晚到响应及删除保护；已证实问题先复现再修复，不删测试换取通过。不再重复分派同一最终审查。
- [ ] 在独立8770临时库／演示账号验证完整Web＋CLI流程、登录路由刷新、桌面／390px，保存截图。完成后关闭自己启动的服务和页面，核对端口已释放，不停止用户原有服务。
- [ ] 同步文档的M4范围与用户取消项、后台零模型规则、手动分析配额及边界，更新OpenAPI、实际测试计数与截图。明确工程验证、Fake／HTTP替身与真实BYOK／教育效果的区别，M2／M3历史未验证项继续保留。
- [ ] 执行最终 `git diff --check`，报告功能、验证、风险与部署步骤；保留可审阅工作区diff，按既定归属策略处理提交，不混入既存未授权改动，不推送。

## Coverage and Handoff

设计1／2对应总体约束；3／10对应任务2／11；4对应任务3；5／6对应任务4；7对应任务5；8对应任务6；9对应任务1／10；11对应任务7／8；12对应任务3–9；13对应各任务测试及最终验收；14对应任务11。

自审检查：请求／输出模型、日周周期键、TaskStartResponse消费端、队列处理器、DTO名称及配额预留／结算由上述接口唯一约定。后台处理器永远不调用send_analysis；GET永远不偷偷刷新。计划依赖顺序为1→2→3→4→5→6，7在1后可实现，8依赖3–7，9依赖3–6，10完成隔离／清理，11才启用实际周期worker并执行整体验收。

建议沿用本会话直接实施（Native），因为任务共享用户／空间锁序、版本指纹和返回契约，连续实施易于保持一致；最终安排一次独立审查。分任务子代理方式也可选择，需为每项实施与审查分配独立上下文。实施前须完成本计划审阅并明确执行方式。
