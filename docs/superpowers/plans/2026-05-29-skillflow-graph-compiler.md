# SkillFlow Graph Compiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the graph-first SkillFlow compiler pass so text-analysis skills are first converted into an auditable execution-flow graph before contract extraction, solidification, artifact generation, validation, and evaluation.

**Architecture:** Extend the existing `doc-skill-ops/compiler/text_skill_compiler.py` CLI without replacing the v1 workflow. Add a new `extract_flow_graph` LLM pass, deterministic graph validation helpers, graph-derived contract fallback behavior, node-level solidification prompt context, and graph-aware compiled outputs while keeping mock LLM tests offline and deterministic.

**Tech Stack:** Python standard library, `unittest`, JSON compiler artifacts, Markdown docs.

---

### Task 1: Add graph validation tests

**Files:**
- Modify: `doc-skill-ops/tests/test_text_skill_compiler.py`
- Later modify: `doc-skill-ops/compiler/text_skill_compiler.py`

- [ ] Add unit tests that import `validate_flow_graph` and `derive_contract_from_graph`.
- [ ] Test that a valid graph with `load_input`, `extract`, and `report` nodes produces `status == "passed"`.
- [ ] Test that a graph with an edge pointing to a missing node reports `status == "failed"`.
- [ ] Test that `derive_contract_from_graph` creates a contract containing `input_mode`, `report_sections`, `entities`, `deterministic_operations`, `residual_reasoning`, and `failure_modes`.
- [ ] Run `python -m unittest doc-skill-ops.tests.test_text_skill_compiler` and confirm the tests fail because the functions are not implemented yet.

### Task 2: Implement graph helpers

**Files:**
- Modify: `doc-skill-ops/compiler/text_skill_compiler.py`

- [ ] Add `validate_flow_graph(graph)` to check required graph keys, node IDs, entry/exit presence, duplicate IDs, unknown edge endpoints, and reachability from entry nodes.
- [ ] Add `derive_contract_from_graph(graph)` to derive a v1-compatible contract from graph nodes.
- [ ] Keep helper functions pure so tests can call them without filesystem or LLM dependencies.
- [ ] Run `python -m unittest doc-skill-ops.tests.test_text_skill_compiler` and confirm the new helper tests pass.

### Task 3: Add graph-first compiler pass tests

**Files:**
- Modify: `doc-skill-ops/tests/test_text_skill_compiler.py`
- Modify mock fixture directory: `doc-skill-ops/examples/hm-kernel-logs/mock_llm/`
- Later modify: `doc-skill-ops/compiler/text_skill_compiler.py`

- [ ] Update the mock fixture sequence so call 1 returns `01_extract_flow_graph.json`, call 2 returns `02_extract_contract.json`, call 3 returns `03_find_solidification.json`, and call 4 returns `04_generate_artifacts.json`.
- [ ] Update tests to assert compiled output includes `compiled/flow_graph.raw.json`, `compiled/flow_graph.json`, and `compiled/graph_validation.json`.
- [ ] Update repair test fixture numbering so repair becomes call 5.
- [ ] Run `python -m unittest doc-skill-ops.tests.test_text_skill_compiler` and confirm the compile test fails before implementation because the new graph files are missing.

### Task 4: Wire graph pass into compiler

**Files:**
- Modify: `doc-skill-ops/compiler/text_skill_compiler.py`

- [ ] Add `prompt_extract_flow_graph(skill_text, sample_texts)`.
- [ ] In `compile_skill`, call `extract_flow_graph` before `extract_contract`.
- [ ] Write `compiled/flow_graph.raw.json`, `compiled/flow_graph.json`, and `compiled/graph_validation.json`.
- [ ] If graph validation fails, stop compilation with a diagnostic pointing to `compiled/graph_validation.json`.
- [ ] Pass the graph into contract extraction and solidification prompts.
- [ ] Run `python -m unittest doc-skill-ops.tests.test_text_skill_compiler` and confirm the graph-first compile tests pass.

### Task 5: Add graph-aware output documentation

**Files:**
- Modify: `doc-skill-ops/QUICKSTART.md`
- Modify: `doc-skill-ops/QUICKSTART-cn.md`
- Modify: `docs/superpowers/specs/2026-05-28-skillflow-graph-compiler-design.md`
- Modify: `docs/superpowers/specs/2026-05-28-skillflow-graph-compiler-design-cn.md`

- [ ] Update quick start output listings to include `compiled/flow_graph.raw.json`, `compiled/flow_graph.json`, and `compiled/graph_validation.json`.
- [ ] Explain that the first LLM pass now produces SkillFlow Graph.
- [ ] Keep English and Chinese docs aligned.

### Task 6: Full verification and publish

**Files:**
- All modified files above.

- [ ] Run `python -m unittest discover -s doc-skill-ops\tests`.
- [ ] Run the offline mock compile command from `doc-skill-ops\QUICKSTART.md`.
- [ ] Inspect generated `compiled/graph_validation.json` and confirm `status` is `passed`.
- [ ] Run `git status --short`.
- [ ] Commit the implementation and docs.
- [ ] Push the current `codex/skillflow-graph-compiler` branch to `origin`.
