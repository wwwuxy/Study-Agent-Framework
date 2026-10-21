# 阶段三：原生 BKT 与 FSRS

每个新建或可用学习空间统一启用两个算法，没有关闭选项，也不回退到旧规则。开源项目见 [pyBKT](https://github.com/CAHLR/pyBKT) 与 [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs)，版本、许可证见 THIRD_PARTY_NOTICES.md。

## 知识与记忆

pyBKT 1.4.3 使用先验、学习率与猜对／失误参数，独立与提示是两个原生观测类别。无可靠观测保持 unknown、估计为空；达到掌握还需两道不同、独立、高置信且足够难的题。低置信、LLM 开放题评分、综合题与看答案不直接建立单概念观测。BKT 是技能估计，不拿遗忘时间替代能力。

py-fsrs 6.3.2 实际运行 FSRS-6：Learning／Review／Relearning，四评分，稳定性／难度／回忆预测，原生 JSON 与 ReviewLog；保留分钟级步骤。新卡无观测归为 unassessed。错误与提示映射 Again；独立正确默认 Good，可选 Hard／Easy。服务端拒绝不一致评分。保存原生日志与更新前后卡片，同一事件至多更新一次。单纯 BKT 重建不会重新安排日期。

## 复习、推荐与报告

复习生成一道新的题，保留模型与教材出处校验；同概念活动会话可恢复，跨普通提交与复习提交幂等。下一动作考虑前置关系、目标权重、未知状态、能力差距、复习到期及临近目标日期，并返回理由和分项分数。支持诊断、讲解、练习、补救、阶段／迁移测评与 REVIEW。未完成课堂先恢复。

报告支持 7／30 天窗口：知识状态分布、窗口前后事件重放、独立／辅助／不确定作答、近期错误与误区、到期安排。复习保持率为可靠复习中的独立正确比例；任务完成率为窗口内开始且已读、全部练习提交的课堂比例。无分母返回 null 与原因。读取报告、算法、Q-Matrix 和列表不创建学习事件。Q-Matrix 不返回答案或评分标准。

CLI 用法见 [CLI 指南](cli.md)；Web 在左侧增加复习与学习报告。两端共用相同 API 和持久数据库。

## 安装与参数维护

常规 setup 安装锁定的 pyBKT／fsrs／numpy／scikit-learn。numpy 2.3.5 与 sklearn 1.7.2 是实际验证的兼容组合；较新版本在原生 EM 或导入处失败。线上不需要加载 PyTorch；只有独立 FSRS 校准环境需要官方 optimizer extra。评测步骤见 [评测记录](m3-evaluation.md)。

参数产物为 JSON，验证库版本、参数范围和有限值；普通用户不能上传 pickle／代码。候选参数不能直接上线。先完成验证，再停止 API 写入与 worker，运行：

```bash
.venv/bin/python -m app.evaluation validate --dataset backend/tests/fixtures/m3/sequences.json --parameters data/m3-evaluation/bkt-fit.json --output data/m3-evaluation/validated.json
.venv/bin/python -m app.maintenance rebuild-algorithms --artifact data/m3-evaluation/validated.json --operation-id params-001
# .env 设置 LEARNER_PARAMETERS_PATH=data/m3-evaluation/validated.json 后启动服务
```

维护会重放 BKT，调用原生 FSRS reschedule 重调度，保留原事件与日志版本，按空间提交并记录恢复进度。完成后服务必须加载同一产物；版本不一致返回需重建，不能混用状态。合成候选不应因技术校验通过而被称作对真实学习者已校准。

## 一次性清空与日常启动

本次用户已授权清空所有旧空间及其学习记录、教材、任务、卡片、日志、索引与学习审计，保留账号、登录会话、密码哈希、模型配置和加密密钥。该动作仅通过显式管理命令执行，常规迁移／setup／serve 不会清空。维护默认预览，只输出计数与目标指纹：

```bash
.venv/bin/python -m app.maintenance reset-learning --operation-id OPERATION_ID
# 仅在已确认清空范围、停止写入及 worker 后执行
.venv/bin/python -m app.maintenance reset-learning --operation-id OPERATION_ID --apply --expected-target FINGERPRINT
```

首次 apply 冻结目标 ID；同一操作重试不会删除之后新建的空间。远端删除失败保留最小墓碑和清理句柄，可重跑同一操作；不以本地已删除声称远端完成。异常留下维护标记以阻止写入，修复后重试同一命令。每次新清空必须使用新操作 ID。

PDF 流程继续由用户所选 Files＋Responses 模型负责，不增加独立解析、OCR 或本地向量模型。
