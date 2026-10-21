# 阶段三评测与原生校准记录（2026-10-19）

## 数据与边界

`backend/tests/fixtures/m3/sequences.json` 是本项目自有合成序列，固定种子 20261019。40 名虚构学习者、每人 32 次观测，共 1280 条；按学习者分 train 28／validation 6／test 6，包含独立／提示、正确／错误、跨日复习。manifest 保存来源、分组和 SHA-256，加载时校验，不读取真实用户数据库或下载他人记录。

预测在当前答案进入模型前计算；验证集选择候选、测试集只报告结果。指标包括 Brier、log loss、混淆矩阵和独立／辅助分组，FSRS 使用跨日观测；空分母明确返回 null。数据泄漏、坏参数、数据不足与原日志不变有回归测试。

## 已实际执行

在线 `.venv` 可运行评测；独立 `data/calibration-env` 安装完整官方优化 extra，产物在 git 忽略的 `data/m3-evaluation`：

```bash
uv venv --python 3.12 data/calibration-env
uv pip sync --python data/calibration-env/bin/python backend/requirements-calibration.lock
uv pip install --python data/calibration-env/bin/python --no-deps -e backend
.venv/bin/python -m app.evaluation evaluate --dataset backend/tests/fixtures/m3/sequences.json --output data/m3-evaluation/default.json
data/calibration-env/bin/python -m app.evaluation fit-bkt --dataset backend/tests/fixtures/m3/sequences.json --output data/m3-evaluation/bkt-fit.json
data/calibration-env/bin/python -m app.evaluation optimize-fsrs --dataset backend/tests/fixtures/m3/sequences.json --output data/m3-evaluation/fsrs-fit.json --optimize-retention
```

BKT 实际调用 pyBKT 原生 EM，三次固定种子初始化、两个观测类别，训练后以验证指标选候选。FSRS 实际调用官方 Optimizer 的参数与目标保持率优化；训练集有 868 条跨日复习，超过库所需 512 条，不使用 mock 代替优化器运行。

| 测试集指标 | 初始参数 | BKT EM 候选 | FSRS 优化候选 |
|---|---:|---:|---:|
| BKT 观测数 | 192 | 192 | 192 |
| BKT Brier | 0.147540 | 0.152178 | 0.147540 |
| BKT log loss | 0.459710 | 0.476966 | 0.459710 |
| FSRS 跨日观测数 | 186 | 186 | 186 |
| FSRS Brier | 0.285760 | 0.285760 | 0.249044 |
| FSRS log loss | 0.830047 | 0.830047 | 0.707161 |

BKT 候选在测试集比初始参数差，因此不能宣称训练必然改善，更不自动发布。FSRS 候选保持率为 0.8、包含 21 个权重；这只是本合成分布结果。两个候选分别只替换对应算法参数，不把它们误称为一个联合优化结果。完整产物包含参数、库版本、数据版本及 validation／test 结果。

**结论：原生拟合、优化、评测和参数重建的工程流程已跑通；真实学习者教育效果尚未评估。线上继续使用初始／库默认参数，calibration_status=uncalibrated。** 校验产物通过只证明结构、版本与计算有效，部署者仍须判断泛化性能，不自动凭指标上涨推广。

上游实现：[pyBKT](https://github.com/CAHLR/pyBKT)、[py-fsrs 的优化与重调度](https://github.com/open-spaced-repetition/py-fsrs)。
