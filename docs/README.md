# StudyAgent 文档

首次使用可从[项目主页](../README.md#quick-start)开始。完整安装、配置、命令和故障排查见[中文使用手册](usage.zh-CN.md)。

## 使用指南

| 文档 | 内容 |
|---|---|
| [完整使用手册](usage.zh-CN.md) | 安装、模型连接、日常学习、部署、备份与排错 |
| [CLI](cli.md) | 终端学习、会话、JSON 输出与脚本调用 |
| [私人教材](materials.md) | PDF 能力检测、上传、检索、引用和删除 |
| [学习对话](planning-chat.md) | 调整时间、目标、学习重点与讲解偏好 |
| [成绩诊断](exam-diagnostics.md) | 已批改试卷、报告核对与外部学习证据 |
| [知识掌握与间隔复习](adaptive-learning.md) | BKT、FSRS、报告、参数维护与重建 |
| [每日任务与周报](active-learning.md) | 今日安排、日周统计、后台任务与手动 AI 分析 |

## 技术参考

| 文档 | 内容 |
|---|---|
| [系统架构](architecture.md) | 模块边界、数据库、事件、事务与后台处理 |
| [API 参考](api.md) · [OpenAPI 快照](openapi.json) | HTTP 接口与错误约定；运行版本的 schema 见服务端 `/openapi.json` |
| [安全与隐私](security.md) | 凭证、账号隔离、文件授权、网络访问与部署边界 |
| [离线评测与校准](evaluation.md) | 合成数据评测、候选参数、验证与发布流程 |
| [演示素材说明](assets/README.md) | README 动图和文档截图的来源与更新要求 |

## 使用边界

- 教学、教材理解与试卷识别使用用户配置的模型 API，能力和质量取决于所选服务商。
- 自动化测试使用隔离数据库、固定演示样例与协议替身，不能替代真实模型或部署环境验证。
- 默认 BKT／FSRS 参数尚未针对真实学习者校准；合成数据上的指标不证明学习效果。
- SQLite 用于单进程部署。多副本需 PostgreSQL、共享私有文件存储与共享限流；Docker 和可选 pgvector 路径应在实际环境验证。

项目采用 [PolyForm Noncommercial License 1.0.0](../LICENSE)，允许按许可证条款进行非商业使用、修改和分发，不授予一般商业使用权限；具体获准用途以许可证原文为准。本项目属于源码可用（source-available）项目，该许可证不属于 OSI 认可的开源许可证。第三方依赖仍遵循各自的许可证，相关声明见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
