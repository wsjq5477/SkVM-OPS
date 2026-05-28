# HM Kernel Log Skill 实施计划

> **给 agent worker 的要求：** 实施该计划时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按任务逐步执行。步骤使用 checkbox（`- [ ]`）语法追踪状态。

**目标：** 将 `doc-skill-ops/hm-kernel-logs.js` 转换为文本形式的 Claude `SKILL.md`，构建一个带 Python 静态分析脚本的优化版 Claude skill，用 `doc-skill-ops/test_log.txt` 测试，并评估 baseline 与优化版在行为、速度和 token 占用上的差异。

**架构：** 在 `doc-skill-ops/skills/` 下创建两个并列 skill 产物：一个纯文本 baseline skill，以及一个包含 `SKILL.md + scripts/ + references/` 的优化 skill。优化脚本负责确定性解析和报告数据生成；Claude 仍负责最终叙述判断。由于仓库中没有可运行的 Claude workflow runner，评估使用本地确定性检查和 token 估算。

**技术栈：** Markdown Claude skills、Python 标准库、`unittest`、JSON 报告。

---

### 任务 1：脚本测试

**文件：**
- 创建：`doc-skill-ops/tests/test_analyze_hm_kernel_log.py`
- 后续创建：`doc-skill-ops/skills/hm-kernel-logs-optimized/scripts/analyze_hm_kernel_log.py`

- [ ] 为解析 `test_log.txt` 编写失败测试。
- [ ] 确认测试失败原因是 analyzer 脚本尚不存在。
- [ ] 实现 analyzer 脚本，直到测试通过。

### 任务 2：Skill 产物

**文件：**
- 创建：`doc-skill-ops/skills/hm-kernel-logs-baseline/SKILL.md`
- 创建：`doc-skill-ops/skills/hm-kernel-logs-optimized/SKILL.md`
- 创建：`doc-skill-ops/skills/hm-kernel-logs-optimized/references/report-format.md`
- 创建：`doc-skill-ops/skills/hm-kernel-logs-optimized/references/analysis-contract.md`

- [ ] 将 `hm-kernel-logs.js` 中的 workflow 阶段和报告规则转换为纯文本 baseline skill。
- [ ] 编写优化 skill，使其先运行 `scripts/analyze_hm_kernel_log.py`，再用脚本 JSON 写最终报告。
- [ ] 保持 `SKILL.md` 简洁，把较长的报告和 schema 细节放到 `references/`。

### 任务 3：评估

**文件：**
- 创建：`doc-skill-ops/evaluate_hm_kernel_skills.py`
- 创建：`doc-skill-ops/evaluation/hm-kernel-log-evaluation.json`
- 创建：`doc-skill-ops/evaluation/hm-kernel-log-evaluation.md`

- [ ] 重复运行优化脚本并记录中位运行时间。
- [ ] 根据 baseline skill + 完整日志估算 baseline 输入 token。
- [ ] 根据优化 skill + 使用到的 references + analyzer JSON 估算优化版输入 token。
- [ ] 将抽取结果与预期 kernel log 事实比较。
- [ ] 编写简洁评估报告，包含结果质量、速度和 token 估算。

### 任务 4：验证

**文件：**
- 上述已有或新增文件。

- [ ] 运行 `python -m unittest discover -s doc-skill-ops/tests`。
- [ ] 运行 `python doc-skill-ops/evaluate_hm_kernel_skills.py`。
- [ ] 检查生成的 evaluation JSON/Markdown。
- [ ] 确认 baseline 和 optimized skill 产物存在，并且 optimized skill 是标准 `SKILL.md + scripts/ + references/` 结构。
