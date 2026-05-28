# Text Skill Compiler 快速开始

该工具用于优化文本分析 skill，尤其是日志解析 skill。它使用 LLM 作为编译器，生成确定性 Python analyzer，在本地测试，失败时用 LLM 修复，并输出优化后的 Claude skill。

## 输入

你需要：

- 一个源 skill 或 workflow 文件，例如 `path/to/SKILL.md` 或 `path/to/workflow.js`。
- 一个或多个样例文本或日志文件。
- 一个用于保存优化后 skill 的输出目录。
- 一个 LLM provider。使用本地模型时，需要 OpenAI-compatible endpoint。

## 本地模型设置

你的本地模型服务必须暴露 OpenAI Chat Completions API：

```text
POST /v1/chat/completions
```

响应必须包含：

```json
{
  "choices": [
    {
      "message": {
        "content": "{\"files\":{...}}"
      }
    }
  ]
}
```

推荐的本地服务方式包括 vLLM、LM Studio、llama.cpp server、Ollama OpenAI-compatible endpoint，或任何支持 `/v1/chat/completions` 的 gateway。

为了获得更好效果，模型最好具备：

- 较强的 JSON 遵循能力。
- 至少 32k context；如果 skill 和日志较长，64k 更好。
- 较强的代码生成能力，因为模型需要生成 Python 脚本和测试。

## 使用本地模型编译

示例：

```powershell
python doc-skill-ops\compiler\text_skill_compiler.py `
  --skill path\to\your\SKILL.md `
  --sample path\to\sample_log.txt `
  --out doc-skill-ops\outputs\your-skill-optimized `
  --name your-skill-optimized `
  --provider local `
  --base-url http://127.0.0.1:8000/v1 `
  --model your-local-model-name
```

如果本地服务需要 key：

```powershell
python doc-skill-ops\compiler\text_skill_compiler.py `
  --skill path\to\your\SKILL.md `
  --sample path\to\sample_log.txt `
  --out doc-skill-ops\outputs\your-skill-optimized `
  --name your-skill-optimized `
  --provider local `
  --base-url http://127.0.0.1:8000/v1 `
  --model your-local-model-name `
  --api-key your-local-key
```

如果没有提供 key，编译器会发送 `Authorization: Bearer local`。

## 使用 OpenRouter 编译

```powershell
$env:OPENROUTER_API_KEY="..."

python doc-skill-ops\compiler\text_skill_compiler.py `
  --skill path\to\your\SKILL.md `
  --sample path\to\sample_log.txt `
  --out doc-skill-ops\outputs\your-skill-optimized `
  --name your-skill-optimized `
  --provider openrouter `
  --model openrouter/anthropic/claude-sonnet-4.6
```

## 离线演示

仓库包含一个 mock LLM 演示。它不会调用外部模型，只用于证明编译器流水线和验证循环。

```powershell
python doc-skill-ops\compiler\text_skill_compiler.py `
  --skill doc-skill-ops\examples\hm-kernel-logs\workflow.js `
  --sample doc-skill-ops\examples\hm-kernel-logs\test_log.txt `
  --out doc-skill-ops\outputs\hm-kernel-logs-optimized `
  --name hm-kernel-logs-optimized `
  --mock-llm doc-skill-ops\examples\hm-kernel-logs\mock_llm
```

## 输出

编译器写出：

```text
<out>/
  SKILL.md
  scripts/
    analyze_text.py
  references/
    analysis-contract.md
    report-format.md
  tests/
    test_analyze_text.py
  compiled/
    flow_graph.raw.json
    flow_graph.json
    graph_validation.json
    contract.json
    solidification.json
    generation.json
    validation.json
  evaluation/
    baseline-vs-optimized.json
    baseline-vs-optimized.md
```

将 `<out>/SKILL.md` 作为优化后的 Claude skill 使用。

## 它如何优化

LLM 编译器会：

1. 读取原始 skill/workflow 和样例日志。
2. 从自然语言 workflow 抽取 SkillFlow 执行流图。
3. 验证图结构，并从图中派生输入/输出 contract。
4. 识别确定性的图节点和操作，例如解析、regex 抽取、分组、时间线生成和 schema 验证。
5. 生成 `scripts/analyze_text.py` 和测试。
6. 在本地运行生成的测试。
7. 如果测试失败，将失败信息发回 LLM 修复。
8. 写出优化后的 `SKILL.md`，先运行 Python analyzer，再把剩余推理交给 Claude。

Python 不是智能层。Python 是由 LLM 生成的确定性执行层。

## 验证

运行全部本地测试：

```powershell
python -m unittest discover -s doc-skill-ops\tests
```

在输出目录内运行生成的 skill 测试：

```powershell
python -m unittest discover -s doc-skill-ops\outputs\your-skill-optimized\tests
```

运行生成的 analyzer：

```powershell
python doc-skill-ops\outputs\your-skill-optimized\scripts\analyze_text.py `
  doc-skill-ops\outputs\your-skill-optimized\samples\sample_log.txt `
  --handoff --pretty
```

## 故障排查

- 如果 JSON 解析失败，换用更强的模型，或在本地服务端降低 temperature。编译器期望原始 JSON，不是 markdown。
- 如果生成的测试失败，增加 `--max-repair-rounds`。
- 如果本地模型超时，缩短样例或使用更长 context、更快的服务后端。
- 如果 token 降幅很小，确认生成脚本输出的是紧凑 handoff JSON，而不是完整原始日志。
- 如果本地 endpoint 路径不是 `/v1`，传入准确的 base URL，使编译器追加 `/chat/completions` 后能访问正确接口。
