# SkillFlow 图编译器实施计划

> **给 agent worker 的要求：** 实施该计划时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按任务逐步执行。步骤使用 checkbox（`- [ ]`）语法追踪状态。

**目标：** 实现 graph-first 的 SkillFlow 编译器 pass，使文本分析 skill 在 contract 抽取、固化、产物生成、验证和评估之前，先被转换成可审计的执行流图。

**架构：** 扩展现有 `doc-skill-ops/compiler/text_skill_compiler.py` CLI，不替换 v1 workflow。新增 `extract_flow_graph` LLM pass、确定性图验证 helper、图派生 contract fallback、节点级 solidification prompt 上下文，以及图感知 compiled 输出，同时保持 mock LLM 测试离线且确定。

**技术栈：** Python 标准库、`unittest`、JSON 编译器产物、Markdown 文档。

---

### 任务 1：增加图验证测试

**文件：**
- 修改：`doc-skill-ops/tests/test_text_skill_compiler.py`
- 后续修改：`doc-skill-ops/compiler/text_skill_compiler.py`

- [ ] 添加导入 `validate_flow_graph` 和 `derive_contract_from_graph` 的单元测试。
- [ ] 测试一个包含 `load_input`、`extract` 和 `report` 节点的合法图会产生 `status == "passed"`。
- [ ] 测试一条指向缺失节点的边会产生 `status == "failed"`。
- [ ] 测试 `derive_contract_from_graph` 创建的 contract 包含 `input_mode`、`report_sections`、`entities`、`deterministic_operations`、`residual_reasoning` 和 `failure_modes`。
- [ ] 运行 `python -m unittest doc-skill-ops.tests.test_text_skill_compiler`，确认测试失败，因为函数尚未实现。

### 任务 2：实现图 helper

**文件：**
- 修改：`doc-skill-ops/compiler/text_skill_compiler.py`

- [ ] 添加 `validate_flow_graph(graph)`，检查必需 graph key、节点 ID、入口/出口存在性、重复 ID、未知边端点和从入口节点的可达性。
- [ ] 添加 `derive_contract_from_graph(graph)`，从图节点派生 v1-compatible contract。
- [ ] 保持 helper 为纯函数，使测试无需文件系统或 LLM 依赖即可调用。
- [ ] 运行 `python -m unittest doc-skill-ops.tests.test_text_skill_compiler`，确认新的 helper 测试通过。

### 任务 3：增加 graph-first 编译 pass 测试

**文件：**
- 修改：`doc-skill-ops/tests/test_text_skill_compiler.py`
- 修改 mock fixture 目录：`doc-skill-ops/examples/hm-kernel-logs/mock_llm/`
- 后续修改：`doc-skill-ops/compiler/text_skill_compiler.py`

- [ ] 更新 mock fixture 顺序，使 call 1 返回 `01_extract_flow_graph.json`，call 2 返回 `02_extract_contract.json`，call 3 返回 `03_find_solidification.json`，call 4 返回 `04_generate_artifacts.json`。
- [ ] 更新测试，断言 compiled 输出包含 `compiled/flow_graph.raw.json`、`compiled/flow_graph.json` 和 `compiled/graph_validation.json`。
- [ ] 更新 repair 测试 fixture 编号，使 repair 变成 call 5。
- [ ] 运行 `python -m unittest doc-skill-ops.tests.test_text_skill_compiler`，确认实现前编译测试失败，因为新的 graph 文件缺失。

### 任务 4：把 graph pass 接入编译器

**文件：**
- 修改：`doc-skill-ops/compiler/text_skill_compiler.py`

- [ ] 添加 `prompt_extract_flow_graph(skill_text, sample_texts)`。
- [ ] 在 `compile_skill` 中，在 `extract_contract` 前调用 `extract_flow_graph`。
- [ ] 写出 `compiled/flow_graph.raw.json`、`compiled/flow_graph.json` 和 `compiled/graph_validation.json`。
- [ ] 如果图验证失败，带着指向 `compiled/graph_validation.json` 的诊断停止编译。
- [ ] 将 graph 传入 contract extraction 和 solidification prompt。
- [ ] 运行 `python -m unittest doc-skill-ops.tests.test_text_skill_compiler`，确认 graph-first 编译测试通过。

### 任务 5：增加图感知输出文档

**文件：**
- 修改：`doc-skill-ops/QUICKSTART.md`
- 修改：`doc-skill-ops/QUICKSTART-cn.md`
- 修改：`docs/superpowers/specs/2026-05-28-skillflow-graph-compiler-design.md`
- 修改：`docs/superpowers/specs/2026-05-28-skillflow-graph-compiler-design-cn.md`

- [ ] 更新 quick start 输出列表，包含 `compiled/flow_graph.raw.json`、`compiled/flow_graph.json` 和 `compiled/graph_validation.json`。
- [ ] 说明第一个 LLM pass 现在会生成 SkillFlow Graph。
- [ ] 保持英文和中文文档一致。

### 任务 6：完整验证和发布

**文件：**
- 上述全部修改文件。

- [ ] 运行 `python -m unittest discover -s doc-skill-ops\tests`。
- [ ] 运行 `doc-skill-ops\QUICKSTART.md` 中的离线 mock compile 命令。
- [ ] 检查生成的 `compiled/graph_validation.json`，确认 `status` 为 `passed`。
- [ ] 运行 `git status --short`。
- [ ] 提交实现和文档。
- [ ] 将当前 `codex/skillflow-graph-compiler` 分支 push 到 `origin`。
