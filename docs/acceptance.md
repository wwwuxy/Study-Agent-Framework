# M1 验收记录

验收日期：2026-10-15（Asia/Shanghai）。范围严格为原规格第八节阶段一。测试不用真实付费凭证，远端网络由 HTTP 替身和显式 Fake Adapter 覆盖；没有冒充真实服务商连通性。

## 六项验收标准

| 标准 | 结果 | 证据 |
|---|---|---|
| 七步学习闭环、数据库保存状态、重登恢复和模型切换 | 通过（Fake 集成） | `test_full_learning_loop_persistence_and_model_switch`：创建、5–10题、批改、课堂、阅读、练习、重放、重新创建应用登录、切换模型，原状态与事件相同 |
| 未作答不能直接已掌握 | 通过 | `test_views_and_uncertain_scoring_never_imply_mastery`，端到端阅读前后 profile 相同 |
| 事件重放不重复加分 | 通过 | 同键同答案返回原结果；同题不同键/同键异答案 409；profile/rebuild 一致；重复题干哈希唯一 |
| 错误 Key、超时、非法 JSON 明确报错且不破坏状态 | 通过（传输替身 / Fake） | `test_remote_errors_are_classified_without_leaking_secrets`、`test_timeout_is_explicit`、`test_invalid_json_has_bounded_retries`、初始化回滚与失败后状态不变 |
| 多用户无法相互访问空间、事件、模型凭证 | 通过 | `test_user_isolation_credentials_and_csrf`，空间/状态/历史/模型能力均 404，模型列表不包含 Key，数据库凭证为密文 |
| 无本地 Embedding 或文档解析依赖 | 通过 | 阶段一依赖锁仅 Web/API/ORM/加密/HTTP/校验/测试工具；不注册材料接口，不调用本地解析或模型 |

## 额外边界

- 图谱重复概念、缺失前置、循环依赖、伪造已核实来源均拒绝。
- 仅两道不同题、难度 ≥ 2、独立确定性达标才可能已掌握；LLM-only 评分不能直接触发。
- 提示使用由服务端事件推导，客户端不能提交 none 隐藏。
- 多知识点错误不统一归因；证据不足保留 unknown；诊断优先级预算有限。
- 更新凭证后必须重新测试；失败的重新测试会撤销旧能力成功标识。
- SQLite 与 PostgreSQL 学习事件均由数据库触发器保护为 append-only。
- 正式迁移可升级、回滚后重新升级。API 集成测试通过正式 Alembic 迁移建表。

## 验证命令

最终回归结果：后端 **39 项**在 SQLite 与真实 PostgreSQL 上均通过；前端 **3 项**异步隔离回归通过；Ruff 与 React 生产构建通过。

独立代码审查发现并修复了：合法选项键大小写误判、检测期间修改配置而错误沿用旧成功结果、旧空间/旧账号响应覆盖当前界面。相应回归已纳入测试。

```bash
./scripts/check.sh
TEST_DATABASE_URL='postgresql+psycopg://.../test' .venv/bin/pytest backend/tests -q
```

PostgreSQL 使用临时本机实例，测试各自创建独立 schema；不是仅模拟 SQL。Docker 镜像和 Compose 配置已提供，本机无 Docker，未实际构建容器。未使用真实 BYOK 服务商做付费测试，因此真实模型的内容质量、具体端点兼容性和账单不在本次验证范围。

## 浏览器检查

通过本机真实服务检查演示账号登录、概览、课堂讲解、阅读记录、单选提交与反馈、页面重载后的记录。桌面 1280px 与移动 390px 断点检查均无横向溢出。界面没有上传、通知或虚假的向量能力入口。

安装脚本也已使用本机依赖缓存完整执行成功；当前预览使用 SQLite 和显式离线演示。

## 阶段边界

M1 代码与自动化验收已交付，M2–M4 尚未实现。上线前仍需使用部署环境和用户选择的真实模型完成集成验收。规则估计未做教育测量校准，不承诺已提高学习成绩。

## CLI 增量验收（2026-10-16）

范围：终端配置模型、目标创建、诊断、交互课堂、单题答题/提示、进度与计划查询；复用原有后端，无新数据库表或模型接入方式。

- `study-agent` console script 与 `python -m app.cli` 入口通过。
- `setup.sh --backend-only` 完整安装与迁移通过，不执行 npm / Node.js。
- Python 单元及集成回归 **63 项通过**，其中 CLI **24 项**；前端原有 3 项回归与构建通过。
- 使用临时真实 localhost 服务，分别启动独立 CLI 进程，验证注册、模型配置检测、创建课程、诊断作答、讲解、阅读确认、提示、批改、进度、退出重登及恢复。
- CLI HTTP 传输替身转发到真实 FastAPI / 正式迁移后的测试数据库，不替换鉴权、评分或状态逻辑。交互测试验证提示、跳过、退出与续做。
- 凭证环境变量 / 隐藏输入、会话文件 0600、目录 0700、按服务端点隔离、401 清理、损坏状态保护、非公网远程 HTTP 拒绝、终端控制序列清理均有回归。
- wheel 和 sdist 构建通过。
- 独立审查发现并修复了 `learn --new` 跳过已读但未答练习的问题；该命令现在也优先恢复当前未完成练习。损坏 Cookie 元数据及非标准网关错误返回也会清晰报错，不输出 traceback。

本次 CLI 增量在 SQLite 和真实 HTTP 上验证；未重复 PostgreSQL 测试，原 39 项 PostgreSQL 结果仍是上方记录的 M1 基线。未调用真实付费模型。
