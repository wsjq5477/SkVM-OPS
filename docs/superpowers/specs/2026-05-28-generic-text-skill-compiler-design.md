# Generic Text Skill Compiler Design

Status: approved for implementation

## Goal

Build a generic optimizer for text-analysis skills, especially log parsing skills. The optimizer must use an LLM as the compiler: it reads an existing skill or workflow, identifies deterministic text-processing work, generates Python scripts and tests, validates them locally against sample files, asks the LLM to repair failures, and emits an optimized Claude skill.

The current HM kernel log work becomes one example, not the framework itself.

## Non-Goals

- Do not reuse SkVM implementation code.
- Do not hard-code HM kernel log semantics in the compiler.
- Do not require a live LLM for unit tests.
- Do not claim provider billing token counts; use local estimates unless a live provider reports usage.

## Architecture

```text
input skill/workflow + sample files
          |
          v
compiler CLI
          |
          v
+----------------------+    +----------------------+
| LLM static passes    |    | local deterministic  |
| - extract contract   |--->| validation           |
| - find candidates    |    | - run generated test |
| - generate files     |<---| - capture failures   |
| - repair files       |    | - evaluate speed     |
+----------------------+    +----------------------+
          |
          v
optimized Claude skill
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

For offline tests and demos:

```bash
python doc-skill-ops/compiler/text_skill_compiler.py \
  --skill doc-skill-ops/examples/hm-kernel-logs/workflow.js \
  --sample doc-skill-ops/examples/hm-kernel-logs/test_log.txt \
  --out doc-skill-ops/outputs/hm-kernel-logs-optimized \
  --name hm-kernel-logs-optimized \
  --mock-llm doc-skill-ops/examples/hm-kernel-logs/mock_llm
```

## Passes

1. `extract_contract`
   - Input: skill/workflow text and sample metadata.
   - Output: `contract.json`.
   - Describes input mode, output report format, key entities, deterministic operations, residual reasoning, failure modes.

2. `find_solidification`
   - Input: contract and skill/workflow.
   - Output: `solidification.json`.
   - Classifies work as `python_ready`, `hybrid`, or `llm_only`.

3. `generate_artifacts`
   - Input: contract, solidification candidates, sample files.
   - Output: generated file bundle:
     - `SKILL.md`
     - `scripts/analyze_text.py`
     - `references/analysis-contract.md`
     - `references/report-format.md`
     - `tests/test_analyze_text.py`

4. `validate`
   - Runs generated tests locally.
   - Runs generated analyzer on samples.
   - Captures stdout, stderr, exit code, runtime.

5. `repair`
   - If validation fails, feed generated files and failure output to the LLM.
   - LLM returns replacement file contents.
   - Repeat up to `--max-repair-rounds`.

6. `evaluate`
   - Estimate baseline skill+sample input tokens.
   - Estimate optimized skill+references+handoff tokens.
   - Record analyzer speed and result summary.

## LLM Client

Support:

- `--mock-llm <dir>` for deterministic local tests.
- `--provider openai` with `OPENAI_API_KEY`.
- `--provider openrouter` with `OPENROUTER_API_KEY`.
- `--provider anthropic` with `ANTHROPIC_API_KEY`.

The compiler uses JSON-returning prompts. Every LLM response is parsed and schema-checked before the next pass.

## Output Contract

Each compiler run writes:

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

## Test Strategy

Unit tests must use `--mock-llm` and must not call a real provider. Tests prove:

- CLI creates the standard Claude skill structure.
- Mock LLM pass responses are consumed in order.
- Generated tests are run locally.
- Validation failure can trigger a repair response.
- Evaluation report includes result, speed, and token estimates.

Live LLM usage is integration behavior, guarded by environment variables.
