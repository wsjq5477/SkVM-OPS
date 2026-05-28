# 通用文本 Skill 编译器设计

状态：已作为 v1 实现；后续工作由 `2026-05-28-skillflow-graph-compiler-design.md` 中的设计取代。

本文档描述第一版 contract-first 实现。除非任务明确要求修改 v1 行为，新的编译器工作都应遵循 graph-first 的 SkillFlow 设计。

## 目标

构建一个面向文本分析 skill 的通用优化器，尤其是日志解析类 skill。优化器必须使用 LLM 作为编译器：读取已有 skill 或 workflow，识别确定性的文本处理工作，生成 Python 脚本和测试，用样例文件在本地验证，在失败时让 LLM 修复，最终输出优化后的 Claude skill。

当前 HM kernel log 工作只是一个示例，而不是框架本身。

## 非目标

- 不复用 SkVM 实现代码。
- 不在编译器中硬编码 HM kernel log 语义。
- 单元测试不依赖真实 LLM。
- 不声称 provider 计费 token 数；除非真实 provider 返回 usage，否则只使用本地估算。

## 架构

```text
输入 skill/workflow + 样例文件
          |
          v
编译器 CLI
          |
          v
+----------------------+    +----------------------+
| LLM 静态 pass        |    | 本地确定性验证       |
| - 抽取 contract      |--->| - 跑生成的测试       |
| - 查找候选项         |    | - 捕获失败           |
| - 生成文件           |<---| - 评估速度           |
| - 修复文件           |    |                      |
+----------------------+    +----------------------+
          |
          v
优化后的 Claude skill
  SKILL.md
  scripts/analyze_text.py
  references/analysis-contract.md
  references/report-format.md
  tests/test_analyze_text.py
  evaluation/
```

## CLI

```bash
python doc-skill-ops/compiler/text_skill_compiler.py \
  --skill path/to/SKILL.md-or-workflow.js \
  --sample path/to/sample.log \
  --out path/to/output-skill \
  --name my-text-analysis-skill \
  --provider openrouter \
  --model openrouter/anthropic/claude-sonnet-4.6 \
  --max-repair-rounds 2
```

离线测试和演示：

```bash
python doc-skill-ops/compiler/text_skill_compiler.py \
  --skill doc-skill-ops/examples/hm-kernel-logs/workflow.js \
  --sample doc-skill-ops/examples/hm-kernel-logs/test_log.txt \
  --out doc-skill-ops/outputs/hm-kernel-logs-optimized \
  --name hm-kernel-logs-optimized \
  --mock-llm doc-skill-ops/examples/hm-kernel-logs/mock_llm
```

## Pass

1. `extract_contract`
   - 输入：skill/workflow 文本和样例元数据。
   - 输出：`contract.json`。
   - 描述输入模式、输出报告格式、关键实体、确定性操作、剩余推理和失败模式。

2. `find_solidification`
   - 输入：contract 和 skill/workflow。
   - 输出：`solidification.json`。
   - 将工作分类为 `python_ready`、`hybrid` 或 `llm_only`。

3. `generate_artifacts`
   - 输入：contract、可固化候选项和样例文件。
   - 输出：生成的文件包：
     - `SKILL.md`
     - `scripts/analyze_text.py`
     - `references/analysis-contract.md`
     - `references/report-format.md`
     - `tests/test_analyze_text.py`

4. `validate`
   - 本地运行生成的测试。
   - 在样例上运行生成的 analyzer。
   - 捕获 stdout、stderr、退出码和运行时间。

5. `repair`
   - 如果验证失败，将生成文件和失败输出交给 LLM。
   - LLM 返回替换文件内容。
   - 最多重复到 `--max-repair-rounds`。

6. `evaluate`
   - 估算 baseline skill + sample 的输入 token。
   - 估算优化后 skill + references + handoff 的 token。
   - 记录 analyzer 速度和结果摘要。

## LLM Client

支持：

- `--mock-llm <dir>`：用于确定性的本地测试。
- `--provider openai`，使用 `OPENAI_API_KEY`。
- `--provider openrouter`，使用 `OPENROUTER_API_KEY`。
- `--provider anthropic`，使用 `ANTHROPIC_API_KEY`。

编译器使用要求返回 JSON 的 prompt。每个 LLM 响应都会在进入下一个 pass 前解析并做 schema 检查。

## 输出契约

每次编译写出：

```text
<out>/
  SKILL.md
  scripts/analyze_text.py
  references/analysis-contract.md
  references/report-format.md
  tests/test_analyze_text.py
  compiled/
    contract.json
    solidification.json
    generation.json
    validation.json
  evaluation/
    baseline-vs-optimized.json
    baseline-vs-optimized.md
```

## 测试策略

单元测试必须使用 `--mock-llm`，不得调用真实 provider。测试证明：

- CLI 创建标准 Claude skill 结构。
- Mock LLM pass 响应按顺序消费。
- 生成的测试会在本地运行。
- 验证失败可以触发修复响应。
- 评估报告包含结果、速度和 token 估算。

真实 LLM 使用属于集成行为，由环境变量控制。
