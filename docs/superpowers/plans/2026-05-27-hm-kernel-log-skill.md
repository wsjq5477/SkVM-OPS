# HM Kernel Log Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert `doc-skill-ops/hm-kernel-logs.js` into a textual Claude `SKILL.md`, build an optimized Claude skill with Python static analysis scripts, test it against `doc-skill-ops/test_log.txt`, and evaluate baseline vs optimized behavior, speed, and token footprint.

**Architecture:** Create two sibling skill artifacts under `doc-skill-ops/skills/`: a baseline text-only skill and an optimized skill with `SKILL.md + scripts/ + references/`. The optimized script performs deterministic parsing and report-data generation; Claude remains responsible for final narrative judgment. Evaluation uses local deterministic checks and token estimates because no live Claude workflow runner is available in the repository.

**Tech Stack:** Markdown Claude skills, Python standard library, `unittest`, JSON reports.

---

### Task 1: Script Tests

**Files:**
- Create: `doc-skill-ops/tests/test_analyze_hm_kernel_log.py`
- Later create: `doc-skill-ops/skills/hm-kernel-logs-optimized/scripts/analyze_hm_kernel_log.py`

- [ ] Write failing tests for parsing `test_log.txt`.
- [ ] Verify the tests fail because the analyzer script does not exist yet.
- [ ] Implement the analyzer script until tests pass.

### Task 2: Skill Artifacts

**Files:**
- Create: `doc-skill-ops/skills/hm-kernel-logs-baseline/SKILL.md`
- Create: `doc-skill-ops/skills/hm-kernel-logs-optimized/SKILL.md`
- Create: `doc-skill-ops/skills/hm-kernel-logs-optimized/references/report-format.md`
- Create: `doc-skill-ops/skills/hm-kernel-logs-optimized/references/analysis-contract.md`

- [ ] Convert the workflow phases and report rules from `hm-kernel-logs.js` into a text-only baseline skill.
- [ ] Write the optimized skill so it runs `scripts/analyze_hm_kernel_log.py` first, then uses the script JSON for final report writing.
- [ ] Keep `SKILL.md` concise and move long report/schema details into `references/`.

### Task 3: Evaluation

**Files:**
- Create: `doc-skill-ops/evaluate_hm_kernel_skills.py`
- Create: `doc-skill-ops/evaluation/hm-kernel-log-evaluation.json`
- Create: `doc-skill-ops/evaluation/hm-kernel-log-evaluation.md`

- [ ] Run the optimized script repeatedly and record median runtime.
- [ ] Estimate baseline input tokens from baseline skill + full log.
- [ ] Estimate optimized input tokens from optimized skill + references used + analyzer JSON.
- [ ] Compare extracted results against expected kernel-log facts.
- [ ] Write a concise evaluation report with result quality, speed, and token estimates.

### Task 4: Verification

**Files:**
- Existing/new files above.

- [ ] Run `python -m unittest discover -s doc-skill-ops/tests`.
- [ ] Run `python doc-skill-ops/evaluate_hm_kernel_skills.py`.
- [ ] Inspect generated evaluation JSON/Markdown.
- [ ] Confirm baseline and optimized skill artifacts exist with standard `SKILL.md + scripts/ + references/` structure for the optimized skill.
