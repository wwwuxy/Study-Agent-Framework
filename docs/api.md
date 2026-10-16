# M1 API

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

教材、review、notifications、jobs 端点未注册，避免把后续阶段标成已实现。
