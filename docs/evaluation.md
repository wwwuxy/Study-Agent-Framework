# 离线评测与参数校准

评测工具用于检查 BKT／FSRS 的预测指标、生成候选参数并验证参数产物。工具不调用网络，也不读取应用中的真实用户数据库。

## 数据与指标

`backend/tests/fixtures/m3/sequences.json` 是项目自有合成序列：40 名虚构学习者、每人 32 次观测，共 1280 条。数据按学习者分为 train 28／validation 6／test 6，包含独立／提示、正确／错误和跨日复习；manifest 保存来源、分组与 SHA-256，加载时校验。

预测在当前答案进入模型前计算。训练集用于拟合，验证集用于选择候选，测试集用于报告结果。指标包括 Brier、log loss、混淆矩阵及独立／辅助分组；FSRS 使用跨日观测，空分母返回 null。

## 运行评测与拟合

应用环境可运行基础评测。FSRS 优化使用独立校准环境与锁定依赖，避免将优化器依赖加入在线服务。以下输出均位于被 Git 忽略的 `data/`：

```bash
uv venv --python 3.12 data/calibration-env
uv pip sync --python data/calibration-env/bin/python backend/requirements-calibration.lock
uv pip install --python data/calibration-env/bin/python --no-deps -e backend

.venv/bin/python -m app.evaluation evaluate --dataset backend/tests/fixtures/m3/sequences.json --output data/evaluation/default.json
data/calibration-env/bin/python -m app.evaluation fit-bkt --dataset backend/tests/fixtures/m3/sequences.json --output data/evaluation/bkt-fit.json
data/calibration-env/bin/python -m app.evaluation optimize-fsrs --dataset backend/tests/fixtures/m3/sequences.json --output data/evaluation/fsrs-fit.json --optimize-retention
```

BKT 使用 pyBKT 原生 EM，采用固定种子初始化和两个观测类别，并按验证指标选择候选。FSRS 使用官方 Optimizer 生成参数及可选目标保持率。两个候选分别修改对应算法，产物包含参数、库版本、数据版本和验证／测试结果。

## 验证与发布

选择候选后先验证产物，例如：

```bash
.venv/bin/python -m app.evaluation validate --dataset backend/tests/fixtures/m3/sequences.json --parameters data/evaluation/bkt-fit.json --output data/evaluation/validated.json
```

技术校验检查库版本、参数范围、有限值、数据版本和独立验证／测试指标。通过校验的产物不会自动替换在线参数；维护者仍需评估候选是否改善预测，以及数据是否适合目标学习者。

发布前备份数据，停止 API 写入和 Worker，按[算法维护说明](adaptive-learning.md#安装与参数维护)重建派生状态，再将 `LEARNER_PARAMETERS_PATH` 指向同一参数产物。参数版本与状态不一致时，服务会要求重建。

## 结果解释

合成数据只用于验证工程流程。拟合不保证比默认参数更好，指标改善也不证明真实学习者的教育效果。线上默认 `calibration_status=uncalibrated`；真实参数校准需要适当的数据授权、独立验证与效果评估。

算法来源与许可证见[第三方声明](../THIRD_PARTY_NOTICES.md)。
