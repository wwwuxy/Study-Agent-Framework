# M1 / M2 架构与数据库

此实现遵循原规格第 10.1 节，按顺序实现 M1、M2。一个确定性 Orchestrator 协调模块，不创建模型间对话。

```mermaid
flowchart LR
  UI[React 学习工作台] --> API[FastAPI 与用户鉴权]
  API --> O[Learning Orchestrator]
  O --> G[Provider Adapter]
  G --> L[用户远端聊天 API]
  O --> K[课程 DAG 校验]
  O --> E[教学与评分]
  E --> EV[只追加学习事件]
  EV --> S[rules_v1 状态重放]
  S --> P[确定性下一步策略]
  K --> DB[(PostgreSQL / SQLite 开发)]
  P --> DB
  EV --> DB
```

## 稳定边界

CLI（`backend/app/cli`）是与 Web 并列的 HTTP 客户端。命令入口 `study-agent`；本地仅保存按服务端点隔离的受限权限会话与空间选择，模型凭证仍只在后端加密保存。命令不会越过 API 直接读写知识状态。CLI 使用细节见 `docs/cli.md`。

`ProviderAdapter` 提供文本、严格 JSON、能力探测和明确拒绝的文件 / Embedding 方法。网关不能直接更新学习状态。所有课程、题目、讲解、提示与开放评分先经过 Pydantic / JSON Schema，再经过 DAG、知识点归属和题目唯一性检查。

教学模型调用同步等待返回，事务在完整校验后保存。M2 新增数据库持久队列，用户授权的资料任务在后台分步运行；各远端步骤有界并记录检查点。调用失败保留脱敏 AgentRun；索引原子发布，课程、题目与状态不留半成品。

## 数据表

| 表 | 作用与主要约束 |
|---|---|
| users | 用户名唯一；scrypt 密码摘要与时区 |
| auth_sessions | SHA-256 会话令牌摘要与过期时间；HttpOnly Cookie |
| provider_configs | 所有者、模型、Fernet 密文凭证、能力检测状态 |
| study_spaces | 所有者、目标、每日时长、日期；用户内初始化幂等键唯一；复合外键限制模型所有者 |
| knowledge_concepts | 空间内唯一知识点 key；初始来源 model_generated_unverified，教材可补充 user_material_derived，删除后保留 source_removed_unverified |
| concept_prerequisites | 空间内概念 / 前置概念复合外键，禁止跨空间依赖 |
| assessment_items | 题目内容与答案；空间内题干哈希唯一；课堂归属复合外键 |
| assessment_attempts | 答案、评分、评估器、请求指纹；同题仅一条有效作答；幂等键唯一 |
| lessons | 讲解、动作理由、阅读状态；空间内创建键唯一 |
| learning_events | 用户 / 空间复合外键，幂等键唯一；数据库触发器拒绝 UPDATE / DELETE |
| learner_concept_states | 空间 / 概念复合主键和外键；状态、证据、算法版本、UTC 测评时间 |
| learning_plans | 下一动作、理由、证据 ID、目标日期、每日任务 |
| agent_runs | run_id、模型、空间、步骤、耗时、token 用量、错误码；不保存完整输入输出 |

## 测评事务与重放

提交幂等键相同且请求指纹相同则返回原结果；同键异内容或同题另开提交返回 409。确定性选择题判分优先。服务端检查历史提示事件并提升 assistance_level，客户端无法隐藏提示。

一笔事务完成：作答事件 → 重放规则状态 → 保存下一计划 → plan_adjusted 事件 → 保存作答结果。失败全部回滚。事件不保存敏感答案全文，只保留作答引用、判分和证据属性；答案在鉴权控制的 attempts 表。

PostgreSQL 对用户行加锁串行化同一用户的写操作，同时使用唯一约束防重复。SQLite 以应用内写锁配合数据库约束，仅支持单进程开发；部署多 worker 必须切 PostgreSQL。

规则只接受高置信、可归因证据；以题目 ID 去重。不同模型版本可通过 `profile/rebuild` 重新计算当前规则状态，原事件不变。事件与状态中的时间统一为 UTC，避免数据库会话时区影响重放。

策略先过滤所有前置未满足的知识点，再按目标重要性、可用时长排序。最多五次初始诊断作答优先级，之后进入基础学习，避免永久诊断循环。复习 / 遗忘模型属于 M3。


## M2 文件、任务与检索

- `material_assets`：用户/空间复合外键、原始文件元数据、哈希、上传幂等指纹、索引代次、原服务商指纹、待清理远端句柄；不复制旧密钥。
- `material_sections`：远端摘要、关键词与概念、未经核实的章节定位、可选远端向量 JSON；空间/资料复合外键。
- `material_jobs`：持久 queued/running/succeeded/failed/cancelled 状态、租约、尝试次数、分步检查点、错误类型；本人与空间内请求键唯一。
- 可选 `material_vectors`：由 scripts/pgvector.sql 初始化，存放远端向量的 pgvector 镜像；与章节外键级联删除。

原文仅作为私有字节对象保存。Files + Responses 适配器通过真实随机 PDF 探测，仅支持已验证 MIME。后台 worker 原子领取任务，分步“上传→目录→章节→可选远端向量→发布”；每步后验证代次与租约，最终发布在同一事务按 asset→job 锁序校验，删除／取消不能被旧任务覆盖。迟到上传句柄重新建立清理任务，失败墓碑仍可发现与重试。

检索限定本人、空间与 ready 资料，关键词／远端向量产生候选，用户模型只可从候选 ID 精排。新的诊断与课堂先取资料证据，默认证据不足停止；通用补充需空间显式授权。模型返回的引用经白名单与存活来源校验，读取时再次过滤已删除来源。概念来源可补充，但不生成作答证据；rules_v1 仍保持 M1 规则。

默认单实例 worker；SQLite 仅用于单进程开发。多副本应使用 PostgreSQL、共享资料存储与共享限流。当前租约提供崩溃恢复，远端上传请求在未收到响应时可能存在无法确认的远端保留，需遵循服务商政策核对。M3 / M4 未实现。
