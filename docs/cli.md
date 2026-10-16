# StudyAgent CLI

CLI 是现有 HTTP API 的客户端，与 Web 使用相同的账号、权限、证据和数据库，不直接改写数据库。远端模型仍由后端 Provider Adapter 调用。

## 只安装命令行和后端

需要 Python 3.12+ 和 uv，无需 Node.js：

```bash
./scripts/setup.sh --backend-only
source .venv/bin/activate
study-agent --help
```

终端一启动后端：

```bash
./scripts/serve.sh
# 无付费 Key 的固定操作系统演示：
ENABLE_FAKE_PROVIDER=true ./scripts/serve.sh
```

终端二运行下述命令。若已有后端运行，直接连接即可，不用再启动一次。

## 首次使用

```bash
study-agent auth register --username yourname
# 密码隐藏输入；已有账号则：
study-agent auth login --username yourname
study-agent auth status

# 隐藏输入 API Key，服务端加密保存；不会写进 CLI 状态文件
study-agent provider add --name '我的模型' --model '服务商模型ID' \
  --base-url 'https://api.example.com/v1' --accept-data-transfer
study-agent provider list
study-agent provider test PROVIDER_ID

# 新建后自动选中该空间；目标日期和预期水平可选
study-agent space create --goal '系统学习操作系统' --provider PROVIDER_ID \
  --minutes 30 --target-date 2026-12-31 --level '基础掌握'
study-agent diagnose
study-agent learn
study-agent progress
study-agent next
```

`PROVIDER_ID` 替换成 `provider add/list` 返回的完整 ID。`--accept-data-transfer` 表示知悉学习目标、上下文、答案会发给所选第三方，调用可能收费，数据保留遵循服务商政策。此参数不会使不支持的文件/Embedding 能力变为可用。

离线演示只替换添加模型这一步：

```bash
study-agent provider add --name '离线演示' --demo
study-agent provider test PROVIDER_ID
study-agent space create --goal '学习操作系统' --provider PROVIDER_ID
study-agent diagnose
study-agent learn
```

服务端必须显式启用 `ENABLE_FAKE_PROVIDER=true`。演示返回固定操作系统课程，不代表能教授任意领域。

## 交互学习

- `diagnose`：生成或读取初始题目；已作答的题展示原反馈并跳过。再次执行可继续未完成题目。
- `learn`：读取最新未完成课堂；完整结束的课堂之后再生成下一课堂。阅读确认与作答分别记录，阅读不会增加掌握度。
- 答题时输入 `/hint` 请求提示、`/skip` 跳过当前题、`/quit` 离开。提示是模型调用且会作为辅助证据保存。
- 每次提交立即保存在后端，退出、关闭终端、重新登录后可继续。
- `learn --new` 请求下一课堂，服务端仍会优先恢复尚未完成的课堂。
- `--no-interactive` 或顶层 `--json` 只获取内容，不自动记录阅读或提交答案。管道中的非 TTY 输入也不会触发答题循环。

## 查看、切换与管理

```bash
study-agent space list
study-agent space use SPACE_ID
study-agent space show SPACE_ID
study-agent space switch-provider SPACE_ID --provider OTHER_PROVIDER_ID
study-agent progress --space SPACE_ID
study-agent plan
study-agent events
study-agent runs
study-agent provider capabilities PROVIDER_ID
study-agent provider update PROVIDER_ID --model 'new-model'
study-agent provider update PROVIDER_ID --rotate-key
study-agent provider test PROVIDER_ID
study-agent provider remove UNUSED_PROVIDER_ID
study-agent auth logout
```

修改 Key、模型或地址后必须重新检测。删除使用中的模型会得到可理解的错误，应先切换学习空间。登录另一个账号或收到 401 时，会清除本地当前空间，避免沿用旧账号的选择。

## 脚本和 JSON

顶层选项放在子命令前。HTTP 错误以非零退出码返回；`--json` 下将领域错误输出为 JSON。参数用法错误遵循 argparse 的 stderr 和退出码 2。Ctrl-C / EOF 返回 130。

```bash
# 密码/Key 的环境变量名称可以自选，不接受明文密码/Key 命令行参数
study-agent auth login --username yourname --password-env MY_PASSWORD
study-agent provider add --name '模型' --model 'chat-model' \
  --api-key-env MY_LLM_KEY --accept-data-transfer
study-agent --json space list
study-agent --json diagnose
study-agent --json learn --no-interactive
study-agent --json hint ITEM_ID
study-agent --json answer ITEM_ID --answer A --request-id my-answer-001
study-agent --json lesson-complete LESSON_ID --request-id my-reading-001
study-agent --json progress
```

未指定变量名时，也可使用 `STUDY_AGENT_PASSWORD` / `STUDY_AGENT_API_KEY`。环境变量不会写进 CLI 本地状态；终端会话的环境安全由使用者管理。

写操作可通过 `--request-id` 指定幂等键。超时不代表服务端没有完成；错误输出会包含当前键，可复用原键和相同请求重试。交互答题遇到超时可重新执行诊断/课堂读取已保存反馈。同题不能靠新键重复增加证据。

## 服务地址、会话和排错

```bash
study-agent --server https://study.example.com --json auth status
# 或设置 STUDY_AGENT_SERVER；默认 http://127.0.0.1:8000
study-agent --config-dir ./data/cli-session auth login --username yourname
# 或设置 STUDY_AGENT_CONFIG_DIR
python -m app.cli --help
```

`--server` 是后端根地址，不是模型 Base URL，也不附带 `/api/v1`。服务器地址按端点隔离会话；不会将一个服务器的 Cookie 发送到另一个服务器。不跟随 HTTP 重定向，不读取系统代理；远程服务器要求 HTTPS，localhost 允许 HTTP。

默认本地目录为 `$XDG_CONFIG_HOME/study-agent` 或 `~/.config/study-agent`。目录权限 0700，状态文件 `state.json` 权限 0600，采用临时文件 + 原子替换保存。它只含会话 Cookie、账号 ID 与当前空间，不含密码、模型 API Key、答案和教材。Cookie 相当于登录凭证，请勿共享此文件。建议一个配置目录同时只供一个 CLI 会话管理账号，多个账号使用不同目录。

本地 HTTP 开发后端需 `COOKIE_SECURE=false`；HTTPS 部署保持 `true`。`connection_failed` 时先检查后端是否运行，`no_active_space` 时先选择空间，`provider_not_tested` 时重新检测模型。本地状态损坏会明确报错并保留原文件，不会静默覆盖。
