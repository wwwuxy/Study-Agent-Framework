<p align="center">
  <img src="docs/assets/readme-hero.svg" alt="StudyAgent：你的模型、你的教材、你的学习进度" width="100%" />
</p>

<h1 align="center">StudyAgent Framework</h1>

<p align="center">
  用户自带模型 API 的个人学习 Agent。<br />
  <strong>从一个学习目标出发，让每一步都有证据，让下一次学习接得上。</strong>
</p>

<p align="center">
  <strong>简体中文</strong> · <a href="README.en.md">English</a>
</p>

<p align="center">
  <img src="docs/assets/readme-stack.svg" alt="Python 3.12+ · FastAPI · React 19 · CLI + Web · BYOK · M1 + M2" width="780" />
</p>

<p align="center">
  <a href="#preview">界面预览</a> ·
  <a href="#quick-start">快速开始</a> ·
  <a href="#cli">命令行使用</a> ·
  <a href="#materials">上传教材</a> ·
  <a href="docs/usage.zh-CN.md">完整中文手册</a>
</p>

---

## StudyAgent 能做什么？

你可以用自己的模型配置，创建学习目标、完成诊断、学习讲解、练习答题，再根据实际证据继续下一步。也可以上传私人 PDF，让教学优先检索教材，并显示文件与章节出处。

**CLI 与 Web 共用后端和学习记录。** 使用同一账号与空间时，关掉终端或刷新网页，进度仍然保留。

| | 功能 | 你会得到什么 |
|---|---|---|
| 🧠 | **连接自己的模型** | 配置 Base URL、API Key 和模型；实际检测聊天、JSON 与可选文件能力 |
| 🎯 | **围绕目标学习** | 生成候选知识结构，安排初始诊断、讲解、示例、提示与练习 |
| 📚 | **私人教材与引用** | 远端理解 PDF，检索章节摘要，展示文件、章节与可下载的原文 |
| 🔄 | **上传后自动入库** | 自动保存文件记录；后台完成后更新知识点、索引和计划，页面同步刷新 |
| 📈 | **用证据记录进度** | 根据实际作答估计知识状态，记录辅助程度，解释下一步推荐 |
| 💻 | **终端与网页协作** | 交互答题、JSON 输出、持久会话、进度恢复与独立学习空间 |

> **当前状态**：M1 学习闭环与 M2 私人教材代码已实现。真实 BYOK 教材样例、pgvector 扩展和 Docker 部署仍需在目标环境验收；M3／M4 尚未实现。[查看验收记录](docs/acceptance.md)

<a id="preview"></a>

## 界面预览

### 教材检索：从答案回到出处

检索结果保留文件和章节信息，可下载原文核对；未验证的页码不会被包装成可靠引用。

![私人教材的关键词检索、章节摘要与来源引用](docs/assets/m2-library.png)

### 知识地图：上传之后，自动更新

上传任务完成后，新知识点会进入数据库与知识地图。**新增内容保持待诊断，上传和阅读不会直接增加掌握度。**

![上传后自动加入知识地图的新概念，状态仍为待诊断](docs/assets/auto-upload-database.png)

<sub>截图来自本机真实界面的独立演示账号，使用明确标注的固定样例；不代表真实服务商已理解教材。当前 Web 界面以中文为主，英文 README 不表示界面已完成英文翻译。</sub>

## 学习流程

![从目标、诊断、教学、练习到证据更新和下一步推荐的学习流程](docs/assets/learning-loop.zh-CN.svg)

- **没有教材**：由用户模型生成候选课程与教学内容，保留待核实标记。
- **上传教材**：先检索用户资料；证据不足时默认停止新教学，通用知识补充需单独授权。
- **形成进度**：作答保存为学习证据，再由规则更新状态与计划；阅读记录与掌握证据分别处理。

<a id="quick-start"></a>

## 快速开始

### 1. 安装并启动

准备 **Python 3.12+、uv**；使用 Web 还需要 **Node.js 22+、npm**。以下命令适用于 macOS／Linux，Windows 可使用 WSL。

```bash
git clone https://github.com/wwwuxy/Study-Agent-Framework.git
cd Study-Agent-Framework

# 安装后端、CLI、Web 依赖，生成本机配置并迁移数据库
./scripts/setup.sh

# 保持此终端运行：后端同时托管已构建的 Web 页面
./scripts/serve.sh
```

打开 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**：注册／登录 → 添加并测试模型 → 创建学习空间 → 开始诊断与学习。

安装脚本不会覆盖已有 `.env`，也不会默认开启演示。已有用户升级后重启 `serve.sh` 即会执行数据库迁移。

<details>
<summary><strong>只用 CLI，或进行 Web 开发</strong></summary>

只安装 CLI 与后端，不需要 Node.js：

```bash
./scripts/setup.sh --backend-only
./scripts/serve.sh
```

Web 开发模式（自动启动后端与 Vite）：

```bash
./scripts/dev.sh
# 网页：http://localhost:5173
# 后端：http://127.0.0.1:8000
```

`serve.sh` 与 `dev.sh` 任选一种运行，避免同时占用 8000 端口。

</details>

<a id="cli"></a>

### 2. 在终端开始学习

另开终端，进入项目目录。密码和 API Key 使用隐藏输入，不必放进命令历史。

```bash
source .venv/bin/activate
study-agent auth register --username yourname
# 已有账号：study-agent auth login --username yourname

study-agent provider add --name '我的学习模型' \
  --model '服务商提供的聊天模型ID' \
  --base-url 'https://你的服务商/v1' \
  --accept-data-transfer
```

将返回的完整模型 ID 替换到 `PROVIDER_ID`，然后执行：

```bash
study-agent provider test PROVIDER_ID
study-agent space create --goal '系统学习操作系统' \
  --provider PROVIDER_ID --minutes 30

study-agent diagnose
study-agent learn
study-agent progress
study-agent next
```

模型 ID 与地址须由服务商提供。`--accept-data-transfer` 表示授权将学习目标、上下文与答案发送至该服务商，知悉可能产生的费用与保留政策。

### 3. 暂时没有付费 Key？先体验演示

启动后端时明确开启演示：

```bash
ENABLE_FAKE_PROVIDER=true ./scripts/serve.sh
```

在已登录的另一个终端中：

```bash
study-agent provider add --name '操作系统演示' --demo
study-agent provider test PROVIDER_ID
study-agent space create --goal '学习操作系统' --provider PROVIDER_ID
study-agent diagnose
study-agent learn
```

这里的 `PROVIDER_ID` 使用本次演示配置返回的 ID。演示使用固定操作系统样例，不访问付费模型，也不会在真实服务失败后静默回退为演示。

<a id="materials"></a>

## 把自己的教材带进来

### 先验证文件能力，再上传

聊天可用并不意味着文件可用。新建原生文件配置，使用实际支持 Files + Responses 协议的服务和模型：

```bash
study-agent provider add --name '我的文件模型' --files \
  --model '服务商提供的文件理解模型ID' \
  --base-url 'https://你的服务商/v1' --accept-data-transfer
study-agent provider test FILE_PROVIDER_ID
study-agent space switch-provider SPACE_ID --provider FILE_PROVIDER_ID
study-agent space use SPACE_ID
```

`FILE_PROVIDER_ID` 与 `SPACE_ID` 分别替换为模型配置和学习空间的完整 ID。检测会上传框架生成的随机标识 PDF，实际读回后才开放 PDF，并尝试删除测试文件；检测可能产生费用。

```bash
study-agent material upload '/绝对路径/教材.pdf' \
  --accept-file-transfer --request-id textbook-001

# 可选：查询处理进度。后台已自动开始，不需要 job run。
study-agent job wait JOB_ID --seconds 180
study-agent material search '进程调度' --mode keyword
study-agent material show MATERIAL_ID
```

| 自动更新阶段 | 持久化内容 |
|---|---|
| 上传成功 | 文件元数据、哈希、所属空间和处理任务 |
| 后台理解 | 上传引用、目录、章节进度与可恢复检查点 |
| 校验并发布 | 章节、摘要、知识点、来源、可选向量和更新后的学习计划 |
| 页面同步 | 自动刷新资料详情、知识地图与计划；重启后仍可读取数据库记录 |

默认单文件 **20 MiB**、最多 **20 个章节**，后台 worker 默认启用。每次上传／重新索引均需单独授权；处理失败可以重试，取消后可重新索引。

<details>
<summary><strong>资料管理、检索选项与能力矩阵</strong></summary>

```bash
study-agent material list
study-agent job show JOB_ID
study-agent job retry FAILED_JOB_ID --request-id retry-001
study-agent job cancel JOB_ID
study-agent material reindex MATERIAL_ID --accept-file-transfer
study-agent material download MATERIAL_ID --output '/新的路径/教材.pdf'
study-agent material remove MATERIAL_ID
```

删除立即移除本地原文和索引，另行执行远端清理；清理失败仍会显示提示与可重试任务。下载不会覆盖已有文件。

| 模型配置 | 聊天／JSON | PDF | 远端 Embedding |
|---|---|---|---|
| 默认兼容聊天接口 | 实际检测 | 不开放 | 不开放 |
| `--files` 原生接口 | 实际检测 | 随机文件探测通过后开放 | 配置模型并检测通过后可选 |
| `--demo` | 固定演示 | 不支持 | 不支持 |
| `--demo-files` | 固定演示 | 固定资料样例，未读取上传内容 | 可选演示向量 |

默认使用**关键词 + 用户模型精排**，不需要向量模型。需要向量方式时，在原生配置中增加 `--embedding-model '向量模型ID'`、重新检测，并在本次上传／重索引增加 `--embeddings`。查询时可用 `--mode embedding`；数据库 pgvector 扩展需要管理员额外安装与初始化。

当前只开放实际验证的 PDF，不支持 DOCX／EPUB。远端文件保留时间与费用遵循所选服务商政策；框架不运行本地正文解析、OCR 或本地 Embedding。[完整教材指南](docs/m2-materials.md)

</details>

## 日常命令速查

| 任务 | 命令 |
|---|---|
| 继续上次学习 | `study-agent learn` |
| 查看知识状态与证据 | `study-agent progress` |
| 查看计划与下一步 | `study-agent plan` / `study-agent next` |
| 切换学习空间 | `study-agent space list` → `study-agent space use SPACE_ID` |
| 查看学习事件与调用用量 | `study-agent events` / `study-agent runs` |
| 输出 JSON，便于脚本调用 | `study-agent --json progress` |
| 连接其他后端 | `study-agent --server https://study.example.com auth login --username yourname` |

交互答题支持 `/hint`、`/skip`、`/quit`；全局 `--json`、`--server` 等选项放在主命令之前。CLI 与 Web 需要各自登录，但共享后端学习记录。[CLI 详细说明](docs/cli.md)

## 配置与数据

完整模板见 [`.env.example`](.env.example)，更多配置、Docker 部署和故障排查见[中文完整手册](docs/usage.zh-CN.md)。

| 配置 | 默认值／作用 |
|---|---|
| `CREDENTIAL_ENCRYPTION_KEY` | 首次 setup 生成，用于后端加密 API Key；备份时单独妥善保管 |
| `DATABASE_URL` | `sqlite:///./data/study.db`；可切换 PostgreSQL |
| `MATERIAL_WORKER_ENABLED` | `true`，上传后自动处理并更新数据库 |
| `MATERIAL_MAX_BYTES` / `MATERIAL_MAX_SECTIONS` | `20971520` / `20` |
| `PGVECTOR_ENABLED` | `false`；开启前先安装扩展并执行 `scripts/pgvector.sql` |
| `ENABLE_FAKE_PROVIDER` | `false`，显式开启后才能使用演示 |
| `COOKIE_SECURE` | HTTPS 部署保持 `true`；setup 生成的本机 HTTP 配置为 `false` |

- **原文与索引分别保存**：原文在本机私有目录；元数据、章节和学习记录在数据库。备份时同时保存数据库、资料目录与对应加密主密钥。
- **用户模型处理资料**：目标、答案与授权文件会发给用户选择的远端服务，模型调用可能产生费用。
- **权限按用户和空间隔离**：CLI 本地状态只保存会话和空间选择，API Key 在后端加密保存。
- **内容仍需核实**：模型生成的课程、摘要与评分不等于权威核验；当前规则估计没有做教育测量校准。

## 开发与验证

```bash
./scripts/check.sh
# Ruff、格式、Shell 语法、Python 测试、前端测试与生产构建

# 专用 PostgreSQL 测试数据库；不要使用生产库
TEST_DATABASE_URL='postgresql+psycopg://user:password@localhost/study_agent_test' \
  .venv/bin/pytest backend/tests -q
```

已有验证覆盖自动后台入库、重启恢复、引用隔离、删除竞态、计划同步与并发答题。验收使用显式演示适配器和协议替身；真实 BYOK 内容质量、原生 pgvector 和 Docker 验收范围见[验收记录](docs/acceptance.md)。

## 路线图

| 阶段 | 当前状态 | 范围 |
|---|---|---|
| **M1 · 学习闭环** | 已实现 | BYOK、目标、诊断、教学、练习、证据、计划与 CLI |
| **M2 · 私人教材** | 代码已实现，部分部署验收待完成 | 原生 PDF、自动入库、持久任务、检索、引用与删除 |
| **M3 · 自适应提升** | 未实现 | BKT、间隔复习、学习报告与质量评估 |
| **M4 · 主动陪伴** | 未实现 | 用户授权后的调度、提醒与预算控制 |

## 文档导航

| 文档 | 内容 |
|---|---|
| [中文完整手册](docs/usage.zh-CN.md) | 完整安装、命令参考、环境变量、部署与常见问题 |
| [CLI 指南](docs/cli.md) | 交互学习、JSON、会话管理与命令详解 |
| [私人教材指南](docs/m2-materials.md) | 文件能力、处理任务、检索、删除与 pgvector |
| [架构](docs/architecture.md) · [API](docs/api.md) · [OpenAPI](docs/openapi.json) | 模块、数据模型和接口 |
| [安全与隐私](docs/security.md) · [验收记录](docs/acceptance.md) | 数据边界、已验证内容与待验证事项 |
| [开发规格](StudyAgent_Framework_Development_Spec.md) · [路线图](docs/development-roadmap.md) | 需求、阶段与后续规划 |

---

<p align="center"><strong>以目标为起点，以证据为方向。</strong><br /><a href="README.en.md">Read in English →</a></p>
