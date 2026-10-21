# StudyAgent 中文完整使用手册

> 返回[中文项目主页](../README.md) · [English overview](../README.en.md)。本页保留完整命令、配置、部署与排错说明。

StudyAgent 是一个用户自带大语言模型 API 的个人学习 Agent 框架。你可以在终端或网页中填写学习目标，由框架组织知识结构、安排初始诊断、生成讲解与练习，并根据实际作答证据持续更新学习状态、推荐下一步任务。

当前已实现**阶段一学习闭环（M1）**、**阶段二私人教材（M2）代码**与**阶段三原生 BKT／FSRS 自适应学习（M3）**，CLI 和 Web 均可使用。阶段二已用演示适配器和协议替身验证；真实 BYOK 教材与 pgvector 部署验收仍待执行，详见[阶段二使用说明](m2-materials.md)。

```text
配置自己的模型 → 创建学习目标 → 生成候选课程 → 初始诊断
        → 课堂讲解 → 作答与反馈 → 保存学习证据 → 推荐下一步
```

学习进度保存在后端数据库中。关闭终端、刷新网页或重新登录后，可以继续之前的学习。CLI 与 Web 使用同一后端、同一账号和同一学习空间时，共享学习记录。

## 目录

- [一、当前功能与实现范围](#一当前功能与实现范围)
- [阶段二：上传教材、检索与引用](#阶段二上传教材检索与引用)
- [二、运行环境](#二运行环境)
- [三、CLI 快速开始](#三cli-快速开始)
- [四、不使用付费 API 的离线演示](#四不使用付费-api-的离线演示)
- [五、日常学习与进度恢复](#五日常学习与进度恢复)
- [六、CLI 命令参考](#六cli-命令参考)
- [七、JSON 输出与脚本调用](#七json-输出与脚本调用)
- [八、Web 界面使用](#八web-界面使用)
- [九、配置项说明](#九配置项说明)
- [十、数据存储、凭证与隐私](#十数据存储凭证与隐私)
- [十一、PostgreSQL 与 Docker 部署](#十一postgresql-与-docker-部署)
- [十二、测试、构建与数据库迁移](#十二测试构建与数据库迁移)
- [十三、项目结构与技术实现](#十三项目结构与技术实现)
- [十四、常见问题](#十四常见问题)
- [十五、后续开发计划与文档](#十五后续开发计划与文档)

## 一、当前功能与实现范围

### 已实现

| 功能 | 说明 |
|---|---|
| 命令行学习 | 在终端完成注册登录、模型配置、目标创建、诊断、课堂与进度查询 |
| Web 学习工作台 | 中文响应式界面，包含学习概览、专属课堂、知识地图、私人教材、学习记录和模型设置 |
| 用户自带模型（BYOK） | 使用用户配置的 Base URL、API Key 和模型名称调用远端服务 |
| 模型连接检测 | 实际验证聊天调用与结构化 JSON 输出，记录能力和调用结果 |
| 候选课程生成 | 根据目标生成知识点、学习目标和前置关系，服务端验证唯一性与无环依赖 |
| 初始诊断 | 生成 5～10 道诊断题，以实际作答建立初始证据 |
| 课堂与练习 | 获取讲解、示例、提示和练习，保存作答反馈 |
| 知识状态 | 记录待诊断、学习中、已掌握及对应证据，支持从事件重建状态 |
| 下一步推荐 | 根据前置知识、证据、目标权重和时间预算选择任务，并展示理由 |
| 持久化与幂等 | 学习记录进入数据库；相同提交重试不会重复计分 |
| 多用户隔离 | 服务端校验模型配置、学习空间、题目和学习记录的归属 |
| 私人教材 | 原生 PDF 能力检测、逐次授权上传、远端目录／章节理解、进度与失败恢复 |
| 教材检索与引用 | 关键词 + 用户模型精排；可选远端 Embedding；真实文件与章节引用 |
| 资料生命周期 | 下载、重索引、取消、删除与远端清理任务；按用户与空间隔离 |
| 离线演示 | 使用明确标注的 Fake Adapter，无需付费 Key 即可体验固定样例 |

### 当前边界

- 通用模型适配器对接 **OpenAI-compatible `/chat/completions` 接口**。
- CLI 是 StudyAgent 的 HTTP 客户端，使用时需要一个正在运行的 StudyAgent 后端。
- CLI 不是 Codex CLI 或 Claude Code 的模型适配器；本项目目前没有将这些命令行工具作为模型后端接入。
- 新增 `openai_files` 原生 Files + Responses 适配器，仅开放实际探测成功的 PDF；DOCX、EPUB 暂不支持。
- 远端 Embedding 为可选项，默认可用关键词检索；pgvector 需要管理员另行安装初始化。BKT、间隔复习与主动提醒属于后续阶段。
- 不引入或运行本地 Embedding、PDF／EPUB／DOCX 正文解析和 OCR。
- 课程、题目及其参考答案由模型生成，均不代表已核实的权威内容或最新考试大纲。

## 阶段二：上传教材、检索与引用

已有项目先升级数据库并重启后端：

```bash
.venv/bin/alembic -c backend/alembic.ini upgrade head
./scripts/serve.sh
```

另开终端，激活虚拟环境并登录。新建一个支持原生文件输入的模型配置：

```bash
source .venv/bin/activate
study-agent auth login --username 你的账号
study-agent provider add --name '我的文件模型' --files \
  --model '服务商的文件模型ID' --base-url 'https://你的服务商/v1' \
  --accept-data-transfer
study-agent provider test PROVIDER_ID
study-agent space switch-provider SPACE_ID --provider PROVIDER_ID
study-agent space use SPACE_ID
```

检测会上传框架生成的随机标识 PDF，实际读回后才开放 PDF；只支持聊天的连接会明确禁用上传。文件探测可能产生费用，检测文件会尝试远端删除。需要服务商同时实现聊天、Files、Responses 和文件删除协议，具体模型必须自行检测。

```bash
study-agent material upload '/绝对路径/教材.pdf' \
  --accept-file-transfer --request-id textbook-001
study-agent job wait JOB_ID --seconds 180
study-agent material list
study-agent material show MATERIAL_ID
study-agent material search '进程调度' --mode keyword
study-agent diagnose
study-agent learn
```

上传成功后会立即自动写入数据库中的文件记录和处理任务；后台完成理解后，自动更新章节、知识点、来源、可选向量与学习计划，页面同步刷新资料详情和知识地图，无需手动执行 SQL 或 `job run`。新增知识点保持待诊断，已有答题证据不变。

上传响应包含 `id` 和 `job_id`。默认后台按“上传 → 目录 → 各章节摘要／关键词／概念 → 可选向量 → 发布”处理，保存检查点，失败时可重试。每次上传／重新索引都须明确授权将文件发送到所选服务商，并知悉费用和第三方保留政策。默认 20 MiB、最多 20 节；`MATERIAL_MAX_BYTES` 最高可设为 `1073741824`（1024 MiB），修改后需重启后端。上传会分块写入私有临时文件，校验完成后发布，后台从磁盘流式转发；CLI 上传和下载也采用文件流。磁盘空间、处理时限和服务商自身限制仍然适用，详见[教材大小说明](m2-materials.md#2-选择空间并上传)。原文留在本机私有目录，不执行本地正文解析。

```bash
study-agent job show JOB_ID
study-agent job retry FAILED_JOB_ID --request-id retry-001
study-agent job cancel JOB_ID
study-agent material reindex MATERIAL_ID --accept-file-transfer --request-id reindex-001
study-agent material download MATERIAL_ID --output '/新的路径/教材.pdf'
study-agent material remove MATERIAL_ID
# 删除返回清理任务 ID；继续 job show/wait 确认远端清理结果
```

上传资料后，新诊断与课堂优先检索教材，并显示真实文件、章节和可下载原文。当前页码无法核实，界面明确标记；模型不能编造引用。资料不足默认停止新教学，用户可通过 `space knowledge-policy SPACE_ID --allow-general-knowledge` 授权通用知识补充。索引、阅读与重索引均不会直接增加掌握度。

可选向量方式需要配置并检测远端 Embedding 模型，且本次上传增加 `--embeddings`。未配置时继续使用关键词 + 用户模型精排，不运行本地向量模型。Web 的“私人教材”页面提供相同功能，以及进度、失败提示与引用查看。

无需付费 Key 的资料演示可使用 `provider add --name '资料演示' --demo-files`；这是独立演示适配器，**使用固定操作系统资料，未读取上传内容**，不能代表真实文件理解成功。

完整的模型配置、命令示例、检索策略、远端清理、pgvector 与部署说明见[阶段二私人教材文档](m2-materials.md)。

## 二、运行环境

| 使用方式 | 必需环境 |
|---|---|
| 仅使用 CLI 与本地后端 | Python 3.12+、uv、可运行 Bash 的终端 |
| 本地 Web 开发 | 上述环境，以及 Node.js 22+、npm |
| Docker 部署 | Docker 与 Docker Compose；容器内安装 Python 和 Node.js 依赖 |
| 连接已有后端的 CLI | 已安装本项目的 Python 环境，以及可访问的 StudyAgent 服务地址 |

仓库中的启动脚本使用 Bash，以下示例适用于 macOS／Linux 终端。Windows 用户可在 WSL 中使用这些脚本；当前未单独验证 Windows 原生脚本流程。

先进入项目根目录。后文除特别说明外，所有命令都从项目根目录执行。

```bash
cd /你的项目目录/Study-Agent-Framework
python3.12 --version
uv --version
```

安装脚本默认寻找 `python3.12`。如果本机的兼容 Python 使用其他名称，可以显式指定：

```bash
PYTHON_BIN=python3 ./scripts/setup.sh --backend-only
```

`PYTHON_BIN` 指向的解释器仍须满足 Python 3.12+。首次安装需要下载依赖；uv 安装方式可参考其[官方安装文档](https://docs.astral.sh/uv/getting-started/installation/)。

## 三、CLI 快速开始

### 1. 安装 CLI 和后端

仅使用终端学习时，不需要安装 Node.js，也不需要启动 Web 开发服务器。

```bash
./scripts/setup.sh --backend-only
```

该命令会：

1. 创建项目内的 `.venv` 虚拟环境并安装锁定的后端开发依赖。
2. 安装 `study-agent` 命令。
3. 在 `.env` 不存在时生成本地开发配置、独立凭证加密密钥和数据库密码。
4. 创建数据目录，并执行 Alembic 数据库迁移。

脚本不会覆盖已有 `.env`，也不会默认启用离线演示。

激活虚拟环境并查看命令：

```bash
source .venv/bin/activate
study-agent --help
```

也可以不激活环境，直接使用完整入口：

```bash
.venv/bin/study-agent --help
.venv/bin/python -m app.cli --help
```

### 2. 在终端一启动后端

```bash
./scripts/serve.sh
```

后端默认监听 `http://127.0.0.1:8000`。保持这个终端运行；使用完毕后可按 `Ctrl-C` 停止服务。

如果同一地址已有 StudyAgent 后端运行，直接连接已有服务即可，不要重复启动占用相同端口的进程。

### 3. 在终端二注册或登录

另开一个终端，进入相同项目目录并激活环境：

```bash
source .venv/bin/activate
study-agent auth register --username yourname
```

程序会提示输入密码，输入过程不回显。用户名允许 3～64 位字母、数字、下划线和短横线；密码长度为 10～128 位。注册成功后会建立登录会话。

已有账号时，改用：

```bash
study-agent auth login --username yourname
study-agent auth status
```

### 4. 配置自己的模型

```bash
study-agent provider add \
  --name '我的学习模型' \
  --model '服务商提供的聊天模型ID' \
  --base-url 'https://api.example.com/v1' \
  --accept-data-transfer
```

请将示例中的模型 ID 和地址替换为服务商实际提供的值；`api.example.com` 只是占位地址。API Key 通过终端隐藏输入，不作为明文命令行参数传入。

| 参数 | 含义 |
|---|---|
| `--name` | 方便辨认的模型连接名称 |
| `--model` | 服务商实际使用的聊天模型 ID，不是自定义显示名称 |
| `--base-url` | 模型服务的兼容接口根地址，例如以 `/v1` 结尾的地址；不要再追加 `/chat/completions` |
| `--accept-data-transfer` | 确认授权将学习目标、教学上下文和答案发送至该第三方服务，并知悉调用可能产生费用 |

成功后会输出模型配置的完整 ID。可以再次查看：

```bash
study-agent provider list
```

将后文的 `PROVIDER_ID` 替换为此处返回的完整 ID，不要原样输入占位符。

### 5. 测试模型连接

```bash
study-agent provider test PROVIDER_ID
study-agent provider capabilities PROVIDER_ID
```

检测会实际调用模型，验证聊天与结构化输出，可能产生服务商费用。只有通过检测的配置才能用于创建学习空间。

聊天模型可用，不等于它支持文件、Embedding、联网或工具调用。当前通用适配器不会宣称这些未实现的能力可用。

### 6. 创建学习目标

```bash
study-agent space create \
  --goal '系统学习操作系统，理解进程、内存与文件系统' \
  --provider PROVIDER_ID \
  --minutes 30
```

`--goal` 和 `--provider` 必填，其余参数可选：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--minutes` | `30` | 每日可用时间，范围 5～480 分钟 |
| `--target-date` | 不设置 | 目标日期，格式为 `YYYY-MM-DD` |
| `--level` | `基础掌握` | 预期学习水平 |
| `--request-id` | 自动生成 | 初始化幂等键，用于复用相同请求重试 |

例如，为备考目标补充日期与预期水平：

```bash
study-agent space create \
  --goal '复习操作系统基础知识' \
  --provider PROVIDER_ID \
  --minutes 45 \
  --target-date 2026-12-31 \
  --level '能独立完成基础分析题'
```

创建成功后，CLI 会自动选中新空间。课程初始化会调用所选模型，等待时间取决于服务商响应。

### 7. 开始诊断和学习

```bash
study-agent diagnose
study-agent learn
study-agent progress
study-agent next
```

- `diagnose`：生成或读取初始诊断题，在终端逐题作答。
- `learn`：开始或继续一节课堂，阅读讲解、查看示例并完成练习。
- `progress`：查看各知识点的状态、有效证据数和独立达标次数。
- `next`：查看系统推荐的下一学习动作及理由。

## 四、不使用付费 API 的离线演示

如果希望先熟悉流程，可以使用固定的操作系统演示课程。

**终端一：启动允许演示的后端。**

```bash
ENABLE_FAKE_PROVIDER=true ./scripts/serve.sh
```

如果后端已经运行，需要先停止，再用上述方式重新启动。仅在 CLI 进程前设置这个变量，不会改变已运行后端的配置。

**终端二：注册账号并添加演示连接。**

```bash
source .venv/bin/activate
study-agent auth register --username demo_learner
study-agent provider add --name '操作系统离线演示' --demo
```

记下输出的模型 ID，替换以下 `PROVIDER_ID`：

```bash
study-agent provider test PROVIDER_ID
study-agent space create --goal '学习操作系统' --provider PROVIDER_ID
study-agent diagnose
study-agent learn
study-agent progress
```

演示模式不连接远端模型、不产生模型 API 费用。它只返回固定操作系统样例，不会根据任意学习目标生成真实课程，也不会在真实模型失败时被静默用作回退。

还可以生成已经包含诊断历史的演示账号：

```bash
ENABLE_FAKE_PROVIDER=true .venv/bin/python scripts/seed_demo.py
```

账号信息写入 `data/demo-access.txt`，文件权限为 `0600`，不纳入版本控制。查看其中的信息后，使用 `auth login` 登录，再执行 `space list` 和 `space use SPACE_ID` 选择演示空间。重复生成同一账号时，需要提供原来的 `DEMO_PASSWORD`，或使用新的 `DEMO_USERNAME`；脚本不会重置已有账号密码。

## 五、日常学习与进度恢复

### 交互答题

在 `diagnose` 和 `learn` 的答题提示中，可以输入：

| 输入 | 行为 |
|---|---|
| 选项键，例如 `A` | 提交选择题答案 |
| 回答文本 | 提交开放题答案，由模型按评分准则评估 |
| `/hint` | 请求提示，并在服务端记录提示使用情况 |
| `/skip` | 跳过当前题，不提交答案 |
| `/quit` | 结束本次交互，保留已提交的记录 |

课堂讲解结束后，按提示回车记录阅读经历。阅读记录和答题证据是两件不同的事，阅读不会直接增加掌握度。

每次答题提交后，后端立即保存对应记录。初始诊断再次执行时，会读取同一批题目，展示已答题的反馈，并继续未答题。

`learn` 会优先恢复最新课堂中的未读内容或未完成练习；当前课堂全部完成后，再请求下一课堂。即使执行 `learn --new`，也会优先恢复尚未完成的练习。

### 下次继续学习

如果后端已停止，先重新启动。然后在 CLI 终端执行：

```bash
source .venv/bin/activate
study-agent auth status
study-agent space list
study-agent learn
```

会话有效且当前空间已保存时，无需每次重新登录或重新选空间。会话过期或已退出登录时：

```bash
study-agent auth login --username yourname
study-agent space list
study-agent space use SPACE_ID
study-agent learn
```

重新登录会清除 CLI 中旧账号的当前空间选择，需要重新选择空间；后端中的学习历史仍然保留。

### 如何理解掌握状态

| 状态 | 含义 |
|---|---|
| `unknown`／待诊断 | 尚无足够、可归因的有效测评证据，不等于认定不会 |
| `learning`／学习中 | 已有证据，尚未达到BKT 证据门槛 |
| `mastered`／已掌握 | 达到BKT 估计与业务证据门槛，仍需后续表现验证 |

当前使用原生 pyBKT：至少在两道不同题上独立达标、满足难度要求且模型估计达标，才可能标记为已掌握。最近有效错误可使状态回到学习中；提示使用单独的原生猜对／失误观测类别。py-fsrs 独立保存记忆与到期时间。

低置信度评分、阅读和仅有未经外部验证的 LLM 开放回答评分，不会直接触发“已掌握”。综合题答错也不会自动将所有关联概念都判为不掌握。当前算法参数尚未经过真实用户教育测量校准，状态是估计，不是权威成绩。

## 六、CLI 命令参考

### 账号与会话

| 命令 | 用途 |
|---|---|
| `study-agent auth register --username NAME` | 注册并登录 |
| `study-agent auth login --username NAME` | 登录已有账号 |
| `study-agent auth status` | 查看当前登录用户 |
| `study-agent auth logout` | 撤销当前会话，并清除本地登录与空间选择 |

### 模型连接

```bash
study-agent provider list
study-agent provider test PROVIDER_ID
study-agent provider capabilities PROVIDER_ID

# 修改显示名称
study-agent provider update PROVIDER_ID --name '新的连接名称'

# 修改聊天模型；之后需要重新检测
study-agent provider update PROVIDER_ID --model '新的模型ID'

# 更新 API Key，终端隐藏输入；之后需要重新检测
study-agent provider update PROVIDER_ID --rotate-key

# 修改服务地址时，需要再次明确第三方数据发送授权
study-agent provider update PROVIDER_ID \
  --base-url 'https://api.example.com/v1' \
  --accept-data-transfer

study-agent provider test PROVIDER_ID

# 只能删除未被学习空间使用的模型配置
study-agent provider remove UNUSED_PROVIDER_ID
```

更换 Key、模型或地址后，原来的能力检测成功标识会失效，必须重新测试。修改名称不会清空学习记录。

### 学习空间

```bash
study-agent space list
study-agent space use SPACE_ID
study-agent space show SPACE_ID

# 换用另一个已通过检测的模型，保留学习历史
study-agent space switch-provider SPACE_ID --provider OTHER_PROVIDER_ID
```

`space use` 会保存默认空间。学习命令中的 `--space` 只改变本次操作的空间，不改写默认选择：

```bash
study-agent progress --space SPACE_ID
study-agent diagnose --space SPACE_ID
study-agent learn --space SPACE_ID
```

### 学习、证据和计划

| 命令 | 用途 |
|---|---|
| `study-agent diagnose` | 初始诊断与续做 |
| `study-agent learn` | 开始或继续课堂 |
| `study-agent learn --new` | 请求下一课堂，仍优先恢复未完成内容 |
| `study-agent progress` | 知识状态和证据概览 |
| `study-agent next` | 下一动作及推荐理由 |
| `study-agent plan` | 已保存的学习计划 |
| `study-agent events` | 本空间的学习事件 |
| `study-agent runs` | 最近的模型调用、耗时、用量及错误记录 |
| `study-agent hint ITEM_ID` | 为指定题目请求提示 |
| `study-agent answer ITEM_ID --answer A` | 提交指定题目的答案 |
| `study-agent lesson-complete LESSON_ID` | 记录已阅读指定课堂讲解 |

这里的 `SPACE_ID`、`ITEM_ID` 和 `LESSON_ID` 均是服务端返回的完整 ID。需要程序化获取时可使用 JSON 输出。

### 全局选项

全局选项放在子命令之前：

```bash
study-agent --server https://study.example.com --json space list
study-agent --timeout 120 diagnose
study-agent --config-dir ./data/cli-account-a auth login --username yourname
```

| 选项 | 默认值 | 说明 |
|---|---|---|
| `--server` | `http://127.0.0.1:8000` | StudyAgent 后端根地址，不附带 `/api/v1` |
| `--config-dir` | 用户配置目录下的 `study-agent` | 存放 CLI 会话及空间选择，建议使用独立目录 |
| `--json` | 关闭 | JSON 输出，同时关闭交互答题循环 |
| `--timeout` | `100` | CLI HTTP 请求超时，允许 1～300 秒，不改变服务端任务时限 |
| `--help` | — | 查看当前命令帮助 |

各级命令均可查看帮助：

```bash
study-agent --help
study-agent provider add --help
study-agent space create --help
study-agent learn --help
```

## 七、JSON 输出与脚本调用

### 获取内容而不进入交互

```bash
study-agent --json space list
study-agent --json diagnose
study-agent --json learn
study-agent --json progress
```

也可以输出面向人的文本，但不进入答题循环：

```bash
study-agent diagnose --no-interactive
study-agent learn --no-interactive
```

上述命令仍可能生成课程、题目或讲解，从而调用模型；“不交互”只表示不会自动记录阅读或提交答案。非 TTY 管道输入同样不会触发交互答题循环。

### 通过环境变量提供凭证

CLI 不提供明文 `--password` 或 `--api-key` 参数。脚本可以从已经设置的环境变量读取凭证：

```bash
# MY_PASSWORD、MY_LLM_KEY 应事先由你自己的环境或密钥管理方式设置
study-agent auth login --username yourname --password-env MY_PASSWORD

study-agent provider add \
  --name '脚本使用的模型' \
  --model '服务商模型ID' \
  --api-key-env MY_LLM_KEY \
  --accept-data-transfer
```

未指定变量名时，也可使用 `STUDY_AGENT_PASSWORD` 和 `STUDY_AGENT_API_KEY`。密码和模型 Key 不会写入 CLI 状态文件。

### 指定提交幂等键

```bash
study-agent --json answer ITEM_ID \
  --answer A \
  --request-id my-answer-001

study-agent --json lesson-complete LESSON_ID \
  --request-id my-reading-001
```

网络超时不代表服务端没有完成。重试时应使用**相同幂等键和相同请求内容**；CLI 的相关错误输出会包含该键。已答题不能通过更换幂等键重复增加掌握证据。

如果答案是在提示或解答辅助下完成的，可以显式标注：

```bash
study-agent answer ITEM_ID --answer A --assistance hint
```

服务端也会检查已经记录的提示事件，不能通过传入 `none` 隐藏提示使用情况。

### 退出码与错误输出

| 退出码 | 含义 |
|---|---|
| `0` | 命令成功 |
| `1` | 运行或接口错误，例如连接失败、鉴权失败、模型调用失败 |
| `2` | 参数、输入或前置条件问题，例如尚未选择空间 |
| `130` | `Ctrl-C` 或输入结束导致交互停止 |

`--json` 模式下，运行错误以 JSON 输出，例如：

```json
{"error":{"code":"no_active_space","message":"尚未选择学习空间。请运行 space create 或 space use ID。"}}
```

命令行语法错误仍遵循 argparse 的标准行为，输出到 stderr，退出码为 `2`。

## 八、Web 界面使用

希望使用浏览器时，需要 Node.js 22+ 和 npm：

```bash
./scripts/setup.sh
./scripts/dev.sh
```

`dev.sh` 会同时启动后端和 Vite 前端。运行前，请先停止占用同一后端端口的 `serve.sh` 进程。

| 地址 | 用途 |
|---|---|
| [http://localhost:5173](http://localhost:5173) | Web 开发界面 |
| [http://localhost:8000/docs](http://localhost:8000/docs) | Swagger 交互式 API 文档 |
| [http://localhost:8000/redoc](http://localhost:8000/redoc) | API 文档阅读界面 |
| [http://localhost:8000/health](http://localhost:8000/health) | 后端健康检查 |

网页使用流程：注册或登录 → 模型与设置 → 添加并测试模型 → 新建学习空间 → 初始诊断 → 专属课堂 → 查看知识状态与学习记录。

左侧「学习空间」提供空间管理页面，可查看目标、教学模型、创建日期和当前空间，并进入学习、新建或删除空间。点击「删除空间 → 确认永久删除」后，学习记录、课程、答题内容、学习画像、本地教材和索引将永久删除，**无法恢复**。删除当前空间后自动切换到其他空间；没有剩余空间时仍可在管理页新建。

正在处理的教材索引会取消，远端文件进入后台清理队列。「远端教材清理」区域显示等待、进行中和失败状态，失败后可点击「重试清理」。如已更换 API Key 或模型配置，可能需要恢复原配置后重试，或到供应商控制台删除文件；远端保留遵循供应商政策。上传尚未结束时，系统仍会登记晚到的文件标识并清理；相关任务结束前请保留原模型凭证。

系统只保留必要的删除标记、任务和远端文件标识，不保留可恢复的学习内容。新版不会自动清除旧版已移除空间；这些空间在「此前已移除的空间」中单独列出，需用户逐一确认永久删除。此更改包含数据库迁移，更新后重新运行 `./scripts/serve.sh`（或 `./scripts/dev.sh`）应用迁移。存在永久删除标记时，迁移禁止直接降回旧版本，以免遗失远端清理信息。

在「模型与设置 → 添加模型」中选择供应商，填写 API Key 并勾选数据传输授权，即可保存。预设会自动填写连接名称、Base URL 和默认聊天模型；保存后点击「测试连接」，通过能力检测后再创建学习空间。

| 网页预设 | 默认聊天模型 | 接口地址 |
|---|---|---|
| DeepSeek | `deepseek-flash` | `https://api.deepseek.com` |
| Qwen · 北京 | `qwen-plus` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Qwen · 新加坡 | `qwen-plus` | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |
| 硅基流动 | `Qwen/Qwen3.5-397B-A17B` | `https://api.siliconflow.cn/v1` |

Qwen 的 Key 需要与所选地域匹配。以上配置于 2026-10-19 根据官方文档核对：[DeepSeek](https://api-docs.deepseek.com/)、[百炼地域与地址](https://help.aliyun.com/zh/model-studio/base-url)、[千问接入](https://help.aliyun.com/zh/model-studio/first-api-call-to-qwen)、[硅基流动接入](https://docs.siliconflow.cn/docs/userguide/quickstart)与[模型示例](https://docs.siliconflow.cn/docs/userguide/capabilities/multimodal-vision)。供应商的实际可用模型与账号权限以连接检测为准。

- **调整预设**：展开「高级设置」，可修改连接名称、接口地址和模型 ID。
- **自定义供应商**：手动填写接口地址和模型；需要上传 PDF 时，选择「原生 PDF（Files + Responses，需检测）」接口，可选填远端 Embedding 模型。
- **切换供应商**：会清空已输入的 Key 与数据授权，需要填写新供应商的 Key 并重新授权。
- **编辑已有连接**：显示已保存的实际配置，不用预设覆盖；API Key 留空即可保留原密钥。
- **离线演示**：仅在后端开启 `ENABLE_FAKE_PROVIDER` 时显示，无需 Key，可选择普通演示或固定资料演示。

CLI 和浏览器需要各自登录；账号、后端服务和学习空间相同时，学习记录相通，本地登录会话不需要共享。

## 九、配置项说明

### 后端配置：`.env`

模板位于 [.env.example](../.env.example)。后端从项目根目录读取 `.env`，环境变量可覆盖同名配置。修改后需重启后端。

| 配置项 | 模板默认值 | 说明 |
|---|---|---|
| `CREDENTIAL_ENCRYPTION_KEY` | 空 | 后端加密模型 API Key 的 Fernet 主密钥；首次 setup 自动生成 |
| `DATABASE_URL` | `sqlite:///./data/study.db` | SQLAlchemy 数据库连接地址 |
| `ALLOW_PRIVATE_PROVIDER_URLS` | `false` | 是否允许模型地址指向内网；默认阻止非公网地址 |
| `ENABLE_FAKE_PROVIDER` | `false` | 是否允许创建离线演示模型配置 |
| `COOKIE_SECURE` | `true` | HTTPS 部署启用；setup 生成的本机 HTTP 开发配置会设为 `false` |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | 允许的前端来源，用于写请求 Origin 校验 |
| `FRONTEND_DIST` | `frontend/dist` | 后端可直接托管的前端构建目录 |
| `STRUCTURED_RETRIES` | `2` | 结构化输出的额外重试次数，允许 0～3 |
| `PROVIDER_CALLS_PER_MINUTE` | `30` | 每用户模型任务入口的应用内限流次数 |
| `SESSION_HOURS` | `168` | 登录会话有效期，单位小时 |
| `POSTGRES_PASSWORD` | 空 | Docker Compose 使用的 PostgreSQL 密码；首次 setup 自动生成 |

`.env.example` 是模板，不是可以直接运行的完整配置。若手工复制 `.env`，需填好加密主密钥和所需数据库密码；已有 `.env` 不会被安装脚本覆盖。

`CREDENTIAL_ENCRYPTION_KEY`、账号密码和模型 API Key 是三种不同的凭证：主密钥由部署者保管，账号密码用于登录 StudyAgent，API Key 用于访问模型服务。

### CLI 配置：终端环境变量

CLI 直接读取进程环境，**不会自动加载后端 `.env` 中的 CLI 专属变量**。

| 环境变量 | 用途 |
|---|---|
| `STUDY_AGENT_SERVER` | CLI 默认连接的后端根地址 |
| `STUDY_AGENT_CONFIG_DIR` | CLI 本地会话目录 |
| `XDG_CONFIG_HOME` | 未指定专用目录时，作为用户配置目录的根路径 |
| `STUDY_AGENT_PASSWORD` | 隐藏输入密码之外的默认环境变量来源 |
| `STUDY_AGENT_API_KEY` | 隐藏输入模型 Key 之外的默认环境变量来源 |

例如，连接已有的 HTTPS 后端：

```bash
export STUDY_AGENT_SERVER='https://study.example.com'
study-agent auth login --username yourname
```

CLI 服务地址与模型服务地址的区别：

| 地址 | 配置方式 | 示例 |
|---|---|---|
| StudyAgent 后端 | `study-agent --server ...` | `http://127.0.0.1:8000` |
| 大模型服务 | `provider add --base-url ...` | `https://api.example.com/v1` |

### 启动脚本配置

| 环境变量 | 用途 |
|---|---|
| `PYTHON_BIN` | 首次创建虚拟环境时使用的 Python，默认 `python3.12` |
| `STUDY_AGENT_PORT` | `serve.sh` 的监听端口，默认 `8000` |
| `UV_CACHE_DIR` | 自定义 uv 缓存目录 |
| `STUDY_AGENT_NPM_CACHE` | 自定义 setup 脚本使用的 npm 缓存目录 |

例如，后端改用另一个本机端口时，CLI 也需要连接相应地址：

```bash
# 终端一
STUDY_AGENT_PORT=8001 ./scripts/serve.sh

# 终端二
study-agent --server http://127.0.0.1:8001 auth login --username yourname
```

## 十、数据存储、凭证与隐私

### 后端数据库

本地开发默认使用 `data/study.db`，SQLite 还可能生成相关日志文件。数据库保存用户、加密模型凭证、课程、题目、作答、学习事件、知识状态、学习计划和模型执行记录。

- SQLite 仅用于单进程本地开发；多 worker 或正式部署应使用 PostgreSQL。
- 学习事件由数据库触发器保护为只追加，状态和计划可根据事件重算。
- 切换模型不会清空学习历史。
- 不同数据库是独立的数据存储；切换 `DATABASE_URL` 不会自动迁移旧数据。

### CLI 本地状态

默认位置为 `$XDG_CONFIG_HOME/study-agent/state.json`，未设置 XDG 时为 `~/.config/study-agent/state.json`。可通过 `--config-dir` 或 `STUDY_AGENT_CONFIG_DIR` 改到独立目录。

目录权限为 `0700`，状态文件权限为 `0600`。文件只保存会话 Cookie、账号 ID 和当前空间选择，不保存密码、模型 API Key、作答全文或教材。不同服务端点的会话分别存储。

会话 Cookie 相当于登录凭证，不应共享或提交到版本控制。多账号使用时，建议各自指定配置目录；同一配置目录建议同时只管理一个 CLI 账号会话。

### 模型凭证与调用边界

- API Key 在后端通过 Fernet 加密保存，不通过查询接口回传原文。
- 自定义模型地址默认进行 SSRF 检查，拒绝非公网地址；自托管内网模型需要管理员明确放开。
- 模型输出经过结构化和业务规则校验，不能直接覆盖知识掌握度或执行服务器命令。
- 日志和调用记录不保存密码、API Key 或敏感答案正文；作答本身由后端受权限控制的数据表保存。
- 教学任务由用户操作触发；教材处理和远端清理会在本次上传／删除授权后于后台继续，有进度、取消和有界恢复。当前不实现主动学习提醒。
- 单次模型任务总时限为 90 秒，并有有界重试。令牌用量与可得费用信息会记录；服务商未提供可靠金额时明确显示“未提供”，当前不承诺货币预算硬限额。

备份学习数据时，应同时妥善保管数据库和对应加密主密钥。直接换掉主密钥会导致已有密文无法解密；丢失后需要重新配置模型 API Key。

## 十一、PostgreSQL 与 Docker 部署

### 使用 Docker Compose

仓库提供多阶段 Dockerfile：先构建 Web，再将后端与静态页面放入应用镜像。Compose 同时启动 PostgreSQL 16 和应用服务。

先准备包含 `CREDENTIAL_ENCRYPTION_KEY`、`POSTGRES_PASSWORD` 的 `.env`。前面的 setup 步骤已经生成这些值；也可按模板自行配置。

本机 HTTP 演示启动方式：

```bash
COOKIE_SECURE=false FRONTEND_ORIGIN=http://localhost:8000 docker compose up --build
```

访问 [http://localhost:8000](http://localhost:8000)。CLI 可以连接相同后端地址。

Compose 配置中的应用端口只绑定到本机 `127.0.0.1:8000`，数据库不映射主机端口；数据库数据保存在命名卷 `postgres_data` 中，教材原文保存在 `material_data` 卷中。容器中的 `DATABASE_URL` 会使用 PostgreSQL，不沿用本地 SQLite。

停止服务：

```bash
docker compose down
```

这个命令不删除数据库命名卷。删除命名卷会丢失其中的数据，应按实际备份和运维流程处理。

### HTTPS 部署

通过可信反向代理提供 HTTPS 时，应设置 `COOKIE_SECURE=true` 和实际使用的 `FRONTEND_ORIGIN`，并保留默认的模型地址访问限制。多副本发布时，数据库迁移应作为独立发布步骤执行。

当前应用内限流适合单实例 MVP，多副本部署需要共享限流设施或网关。Docker 配置已提供，但本次开发环境没有实际运行 Docker 容器；部署环境仍需单独验证。

## 十二、测试、构建与数据库迁移

### 仅后端和 CLI

在执行过 `setup.sh --backend-only` 后，可以运行：

```bash
.venv/bin/pytest backend/tests -q
.venv/bin/pytest backend/tests/test_cli.py -q
.venv/bin/ruff check backend
.venv/bin/ruff format --check backend
```

测试使用 Fake Adapter 或 HTTP 传输替身，不需要真实付费 API Key。CLI 集成测试保留真实鉴权、数据库迁移、评分与状态逻辑。

### 包含前端的完整检查

先执行完整的 `./scripts/setup.sh` 安装前端依赖，再运行：

```bash
./scripts/check.sh
```

该脚本执行 Python 静态检查、格式检查、Shell 语法检查、Python 测试、前端测试和生产构建。

也可单独执行：

```bash
npm --prefix frontend test
npm --prefix frontend run build
```

M1＋CLI 基线为 63 项 Python 与 3 项前端测试。M2 新增资料、原生接口和 CLI 资料回归，并重新运行 SQLite、PostgreSQL、前端与真实 HTTP 联调。最终结果与未验证的真实 BYOK／pgvector 范围见[验收记录](acceptance.md)。

### PostgreSQL 集成测试

在专用测试数据库中运行：

```bash
TEST_DATABASE_URL='postgresql+psycopg://user:password@localhost/study_agent_test' \
  .venv/bin/pytest backend/tests -q
```

每个集成测试会创建独立 schema，并在结束后删除；测试账号需要相应权限。不要把业务生产数据库当作测试数据库使用。

### 数据库迁移

```bash
# 升级到当前版本
.venv/bin/alembic -c backend/alembic.ini upgrade head

# 查看当前版本
.venv/bin/alembic -c backend/alembic.ini current
```

需要在可丢弃的开发数据库中验证完整回滚时，可执行：

```bash
.venv/bin/alembic -c backend/alembic.ini downgrade base
```

当前初始迁移回滚会删除该阶段的数据表，包含用户、凭证和学习历史；它不是学习状态撤销命令。启动脚本会自动运行升级迁移。

## 十三、项目结构与技术实现

后端使用 Python 3.12+、FastAPI、Pydantic、SQLAlchemy 和 Alembic；部署数据库为 PostgreSQL，本地开发可用 SQLite。CLI 使用 Python 标准库 argparse 和 HTTP 客户端，Web 使用 React／Vite。

```text
Study-Agent-Framework/
├── backend/
│   ├── app/
│   │   ├── cli/                 # 命令解析、HTTP 客户端、会话、终端交互与展示
│   │   ├── api/                 # REST API、鉴权和归属校验
│   │   ├── core/                # 配置、安全与学习流程编排
│   │   ├── providers/           # 远端模型协议、兼容接口和离线演示
│   │   ├── knowledge/           # 候选课程与知识依赖图校验
│   │   ├── learner/             # 原生 pyBKT 估计、参数与学习报告
│   │   ├── planning/            # 确定性下一步决策
│   │   ├── teaching/            # 评分逻辑
│   │   ├── schemas/             # API 输入和模型输出结构
│   │   └── db/                  # ORM 模型和数据库会话
│   ├── migrations/              # 迁移、约束及事件防修改触发器
│   ├── tests/                   # 领域、模型接入、API 和 CLI 测试
│   ├── requirements.lock        # 运行依赖锁
│   ├── requirements-dev.lock    # 开发依赖锁
│   └── pyproject.toml           # Python 项目与 study-agent 命令入口
├── frontend/                    # 中文 Web 工作台
├── scripts/
│   ├── setup.sh                 # 安装初始化，支持 --backend-only
│   ├── serve.sh                 # 仅启动后端
│   ├── dev.sh                   # 同时启动后端和 Web 开发服务器
│   ├── check.sh                 # 完整检查
│   └── seed_demo.py             # 演示账号与数据
├── docs/                        # API、架构、安全、CLI 和验收文档
├── .env.example                 # 后端环境配置模板
├── Dockerfile
├── docker-compose.yml
└── README.md
```

模型调用经过 Provider Adapter，状态更新由服务端原生 BKT／FSRS 与观测规范控制。框架采用一个主学习流程和确定性服务模块，不依靠多个模型互相对话推进学习。

API 在线文档由 FastAPI 自动生成；保存的接口快照位于 [docs/openapi.json](openapi.json)。已包含教材与持久任务接口；复习调度和通知仍未实现。

## 十四、常见问题

### 找不到 `study-agent` 命令

先确认已执行安装并激活当前项目环境：

```bash
./scripts/setup.sh --backend-only
source .venv/bin/activate
study-agent --help
```

或者直接使用 `.venv/bin/study-agent`。如果在 CLI 功能加入之前安装过项目，需要重新执行安装脚本注册命令入口。

### 只有 Python 3.13／3.14，安装脚本找不到 `python3.12`

指定本机实际的解释器，例如 `PYTHON_BIN=python3 ./scripts/setup.sh --backend-only`，并确认它满足项目版本要求。

### `connection_failed`：无法连接服务

CLI 不会自动启动后端。检查 `serve.sh` 是否仍在运行、端口是否一致，以及 `--server` 是否误填成了模型服务地址。

### 端口 8000 已被占用

确认是否已经启动了本项目的后端。如果是，直接复用；如果需要独立服务，可以通过 `STUDY_AGENT_PORT` 指定其他端口，并让 CLI 连接同一端口。

### 注册成功，但后续仍提示未登录

本机 HTTP 后端需要 `COOKIE_SECURE=false`，修改后重启并重新登录。远程服务应使用 HTTPS 并保持 Secure Cookie 开启。另请检查是否交替使用了 `localhost` 和 `127.0.0.1`：CLI 会将这些地址视为不同的服务端点。

### `no_active_space`：尚未选择学习空间

```bash
study-agent space list
study-agent space use SPACE_ID
```

注册、切换账号、重新登录或收到 401 后，可能需要重新选择空间。数据库中的历史仍然保留。

### `provider_not_tested`：模型尚未通过检测

运行 `study-agent provider test PROVIDER_ID`。修改模型、Key 或地址后必须重新检测；先前的成功结果不会自动沿用。

### `demo_disabled`：离线演示未启用

用 `ENABLE_FAKE_PROVIDER=true ./scripts/serve.sh` 启动后端。这个开关由后端读取，仅设置在 CLI 进程中没有作用。

### `invalid_api_key`、`provider_timeout` 或 `rate_limited`

分别检查模型 Key 权限、服务响应与配额。连接检测本身也会调用服务商。超时后先查询已有进度，或使用原幂等键重试，不要假定先前提交一定失败。

### `invalid_structured_output` 或课程创建失败

模型没有返回通过结构与业务校验的内容。框架会停止任务，不保存不完整课程。可以检查模型兼容性后重试，或改用另一个已检测的模型配置。

### 自托管内网模型被拒绝

默认会拒绝模型地址指向环回、内网等非公网地址。只有自托管管理员明确允许时，才设置 `ALLOW_PRIVATE_PROVIDER_URLS=true` 并重启后端；这和 CLI 连接本机 StudyAgent 服务是两个独立的地址检查。

### `invalid_local_state`：CLI 状态损坏

程序会保留原状态文件。可以先改用一个新的独立 `--config-dir`，重新登录并选择空间；之后再检查原文件。不要将包含 Cookie 的状态文件粘贴到公开问题反馈中。

### 提示未配置 `CREDENTIAL_ENCRYPTION_KEY`

首次安装且 `.env` 不存在时，setup 会自动生成。如果已经手工创建了一个空模板 `.env`，脚本不会覆盖它，需要自行填写有效 Fernet 密钥。已有数据库使用的主密钥应保持一致，不要通过随意生成新值来尝试修复旧凭证解密问题。

### 为什么读完讲解还没有“已掌握”

阅读只记录经历。掌握状态需要独立作答、不同题目和足够证据；这是设计中的证据规则，不是进度丢失。

### 能否上传教材或直接核实最新考纲

阶段二已支持经过实际检测的 PDF 远端理解、检索和引用；详见[教材使用说明](m2-materials.md)。尚未实现可信联网核验，模型提取摘要与生成内容均需核实，不会自动标记成某年官方考试大纲。

## 十五、后续开发计划与文档

| 阶段 | 状态 | 计划内容 |
|---|---|---|
| M1：学习闭环 | 已实现，含 CLI | BYOK、目标、课程、诊断、教学、测评、持久化状态与推荐 |
| M2：私人教材 | 已实现代码，真实 BYOK／pgvector 验收待执行 | PDF 远端理解、持久任务、教材检索、出处、删除与 CLI／Web |
| M3：自适应提升 | 已实现，真实教育效果待评估 | 原生 BKT＋FSRS、间隔复习、报告与版本化评测 |
| M4：主动陪伴 | 已实现，工程验证见验收记录 | 每日任务、到期复习、偏离建议、自然周报、手动分析配额与账号隔离；新提醒设置／授权控制模块取消 |

开发按阶段推进；后续功能不会以虚假入口或伪造成功结果提前开放。

- [原始开发规格](../StudyAgent_Framework_Development_Spec.md)：需求、硬约束、阶段任务与验收标准。
- [CLI 使用说明](cli.md)：命令行专项说明。
- [系统架构](architecture.md)：模块边界、数据库与状态重放。
- [API 说明](api.md)：接口与错误约定。
- [安全与隐私](security.md)：凭证、隔离、网络访问与部署边界。
- [开发路线图](development-roadmap.md)：后续阶段规划。
- [验收记录](acceptance.md)：已有验证证据和未验证范围。

## 阶段三：复习、报告与算法版本

所有空间统一运行原生 BKT＋FSRS。CLI 与 Web 共用后端，CLI 不计算概率或日期。先用 `study-agent review list` 查看 due／upcoming／unassessed，再用 `study-agent review start --concept CONCEPT_ID --request-id review-001` 开始或恢复；交互课堂可答题，也可用 `study-agent review submit REVIEW_ID --item ITEM_ID --answer A --rating good --request-id answer-001`。评分支持 again、hard、good、easy；提示或答错只能 again。`learn` 遇到 REVIEW 会进入同一复习会话。

`study-agent algorithms` 查看必启算法与实际参数版本；`study-agent report --days 7`（或 30）查看状态变化、近期错误、复习保持率和任务完成率。所有命令支持 `--space SPACE_ID` 和主命令前的 `--json`。Web 对应「复习」「学习概要」；空报告显示证据不足，不伪造百分比。退出重登与刷新保留已提交数据。默认参数未针对真实用户校准。部署、离线校准与维护参见 [阶段三说明](m3-adaptive-learning.md)。


## 使用知识脑图

左侧选择「知识地图」。学习目标是中心节点，知识点按前置关系展开；实线连接主分支，带箭头的虚线表示额外前置关联。同一知识点只显示一次，颜色与文字标明待诊断、学习中和已掌握。

点击节点查看学习目标、模块、建议时长、有效证据及前置知识；点击详情中的关联节点可跳转定位。也可使用「定位知识点」下拉框查找较大脑图中的知识点。拖动画布平移，滚轮／双指缩放，工具栏提供放大、缩小和居中适配。键盘聚焦画布后可用方向键平移、加减号缩放、数字0适配；知识节点和关联按钮也支持键盘访问。

脑图直接读取已有课程与学习状态，上传资料或通过学习对话补充的知识点会在刷新后显示。查看或拖动脑图不会修改掌握度和复习时间。手机端详情位于画布下方，整图缩小时可先用下拉框定位节点。

## 使用学习对话实时调整计划

左侧「学习对话」或概览／课堂的调整入口可打开Chat。明确需求自动保存，并显示前后差异；例如“每天15分钟，先学进程调度，使用面试例子”。支持目标、时间、日期、重点、讲解偏好和补充知识；模糊要求先澄清。聊天历史、需求版本和阶段路线保存在同一数据库，CLI的plan／next／learn读取同一结果。旧课堂可暂存并继续原题，已有学习证据与FSRS保留。

失败可按原消息重试，刷新可恢复历史；当前版本校验后一次发布完整回复与计划。详细行为、演示范围、费用和故障恢复见[聊天指南](planning-chat.md)。


## M4 每日学习工作台

使用 `/login` 或 `/register` 进入个人账号。在「今日任务」查看今日安排、到期复习与计划建议；「学习概要」统一提供学习概览、近期统计、自然周报、间隔复习和学习记录五个同级标签，侧栏不再单列概览、复习和记录。今日任务的「查看全部复习安排」会定位到报告内复习标签。后台运行和空间管理位于「模型与设置」标签中。站内消息页面已移除。日周统计使用现有数据自动生成，只有点击 AI 分析才调用模型。详情、时区规则、配额、升级与截图见[M4完整指南](m4-active-learning.md)，终端命令见[CLI指南](cli.md)。不新增提醒设置或授权与数据控制模块；本地数据库与资料仍受现有忽略规则保护，登录账号的数据由后端隔离。

## 成绩诊断

Web 侧栏选择「成绩诊断」，上传老师批改后的 PDF 或 JPG／PNG。识别由当前用户配置的模型负责，PDF／图片能力需分别检测。报告展示逐题依据及状态变化，可靠单知识点结果自动更新知识状态和后续计划，模糊结果可核对。导入不会延后 FSRS 复习日期。见[详细指南](exam-diagnostics.md)。
