# SkillFlow Graph Compiler Design

Status: user-approved design; initial graph-first implementation tracked by `docs/superpowers/plans/2026-05-29-skillflow-graph-compiler.md`

## Background

The current generic text skill compiler is contract-first:

```text
skill/workflow + samples
  -> contract.json
  -> solidification.json
  -> generated Claude skill bundle
```

This proved the feasibility of using an LLM as the compiler and Python as the
deterministic execution layer. However, it misses a critical intermediate
representation: the execution flow of the original natural-language skill.

For log analysis and other text-analysis skills, the optimizer should not jump
from prose directly to generated code. It should first build an auditable graph
of the skill's execution logic, similar in spirit to a code graph for source
code, but extracted from natural-language instructions.

## Goal

Build a graph-first compiler for text-analysis Claude skills.

The compiler converts a natural-language skill or workflow into a structured
`SkillFlow Graph`, classifies each graph node as scriptable, hybrid, or
LLM-only, generates deterministic Python for the stable parts, and rewrites the
Claude skill so runtime work is split between fast scripts and residual LLM
reasoning.

## Non-Goals

- Do not reuse SKVM implementation code.
- Do not hard-code HM kernel log semantics into the generic compiler.
- Do not require BPMN as the internal model.
- Do not claim that every natural-language instruction can be safely compiled
  into code.
- Do not remove the LLM from text analysis. The LLM remains the semantic
  compiler and the runtime reasoning layer where judgment is required.

## Current Step Review

| Current step | What it does today | Correct owner in v2 | v2 change |
| --- | --- | --- | --- |
| Read source skill/workflow and samples | Loads files and sample text | Script | Keep deterministic. Add metadata, size limits, and source IDs. |
| `extract_contract` | Directly extracts input/output contract | LLM plus script validation | Replace as the first pass. Contract should be derived from the graph. |
| Natural-language execution step extraction | Implicit inside `extract_contract` | LLM | Make explicit as `extract_flow_graph`. Require node IDs, edges, inputs, outputs, and evidence spans. |
| Graph validation | Not present | Script | Add schema validation, reachability checks, cycle checks, missing input/output checks, and source-span checks. |
| `find_solidification` | Coarsely classifies work as `python_ready`, `hybrid`, or `llm_only` | Hybrid | Run per graph node. Scripts score deterministic patterns; LLM judges semantic ambiguity. |
| Generate Python analyzer | LLM generates a full analyzer | LLM plus script validation | Generate only for nodes classified as script or hybrid pre-extract. |
| Generate tests | LLM generates tests | Hybrid | LLM proposes tests; script creates fixture wiring and runs them. |
| Validate generated bundle | Runs tests and analyzer | Script | Keep and expand to validate graph-to-code coverage. |
| Repair | LLM repairs generated files after validation failure | Script detects, LLM repairs | Keep. Feed graph validation and runtime failures as compiler diagnostics. |
| Generate optimized `SKILL.md` | LLM generates final skill | LLM plus template checks | Rewrite around graph nodes: run scripts first, then execute residual LLM nodes. |
| Runtime optimization | Minimal | Script trace plus LLM analysis | Add runtime trace collection for misses, fallbacks, slow nodes, and bad extractions. |

## Core Concept: SkillFlow Graph

`SkillFlow Graph` is the compiler's central intermediate representation.

It is not a knowledge graph of entities. It is an execution-flow graph for a
natural-language skill. It should answer:

- What steps does the skill perform?
- What data does each step consume and produce?
- Which steps are sequential, conditional, repeated, or fallback paths?
- Which steps are deterministic enough to script?
- Which steps require LLM judgment?
- Which original instructions justify each node?

Example shape:

```json
{
  "graph_id": "hm-kernel-log-analysis",
  "entry_nodes": ["load_input"],
  "exit_nodes": ["write_report"],
  "nodes": [
    {
      "id": "extract_panic_facts",
      "type": "extract",
      "description": "Extract panic type, crash thread, CPU, ESR, FAR, ELR, and call stack.",
      "inputs": ["log_text"],
      "outputs": ["panic_facts"],
      "owner": "script_candidate",
      "determinism": "high",
      "evidence_spans": [
        {
          "source": "SKILL.md",
          "quote": "Extract crash context and key registers before root-cause analysis."
        }
      ]
    },
    {
      "id": "infer_root_cause",
      "type": "reason",
      "description": "Infer likely root cause from extracted facts and uncertainty.",
      "inputs": ["panic_facts", "timeline"],
      "outputs": ["root_cause_hypothesis"],
      "owner": "llm_required",
      "determinism": "low"
    }
  ],
  "edges": [
    {
      "from": "extract_panic_facts",
      "to": "infer_root_cause",
      "kind": "data_dependency"
    }
  ]
}
```

## Node Types

The first version should keep the type system small:

| Type | Meaning | Typical owner |
| --- | --- | --- |
| `load_input` | Read the user-provided file path and normalize text | Script |
| `chunk` | Split or window large text | Script |
| `extract` | Extract entities, timestamps, sections, counters, stack traces, key-value facts | Script or hybrid |
| `normalize` | Canonicalize names, timestamps, severity labels, paths, codes | Script |
| `filter` | Select relevant lines or events | Script |
| `aggregate` | Count, group, sort, deduplicate, correlate by key | Script |
| `classify` | Classify text into known labels | Hybrid |
| `decide` | Apply explicit thresholds or decision rules | Script or hybrid |
| `reason` | Explain cause, assess uncertainty, connect weak signals | LLM |
| `report` | Produce final user-facing report | LLM, optionally template-assisted |
| `validate` | Check schema, completeness, confidence, or missing evidence | Script |
| `fallback` | Route to LLM/manual path when deterministic extraction fails | Hybrid |

## Edge Types

| Edge type | Meaning |
| --- | --- |
| `sequence` | Step B normally runs after step A |
| `data_dependency` | Step B consumes output from step A |
| `condition_true` | Conditional branch when a predicate is true |
| `condition_false` | Conditional branch when a predicate is false |
| `loop` | Repeated operation over chunks, events, sections, or candidates |
| `fallback` | Recovery path when a previous node fails or confidence is low |
| `evidence` | Link from a source instruction or sample observation to a node |
| `refinement` | Later runtime feedback changes a previous static decision |

## Revised Compiler Pipeline

```text
source skill/workflow + samples
        |
        v
ingest_sources                      [script]
        |
        v
extract_flow_graph                  [LLM]
        |
        v
validate_flow_graph                 [script]
        |
        v
derive_contract                     [script + LLM supplement]
        |
        v
classify_solidification_by_node     [script + LLM]
        |
        v
generate_deterministic_artifacts    [LLM]
        |
        v
validate_generated_bundle           [script]
        |
        v
repair_until_valid                  [script diagnostics + LLM repair]
        |
        v
rewrite_skill_around_graph          [LLM + template checks]
        |
        v
runtime_trace                       [script]
        |
        v
next_round_optimization             [script + LLM]
```

## Static vs Runtime Responsibilities

Static compilation should do:

- Extract the SkillFlow Graph from the natural-language skill.
- Validate graph shape and source grounding.
- Derive input/output/report contracts.
- Classify nodes by determinism and scriptability.
- Generate Python for deterministic nodes.
- Generate tests and fixture expectations.
- Emit the optimized Claude skill bundle.

Runtime optimization should do:

- Record which graph nodes ran.
- Record analyzer timing and extraction confidence.
- Record missing fields and fallback reasons.
- Preserve compact handoff JSON for Claude.
- Collect failure cases for the next compiler run.
- Suggest newly scriptable patterns once enough runtime examples exist.

## LLM vs Script Rule

Use the LLM when the operation requires semantic interpretation:

- Understanding natural-language instructions.
- Splitting prose into meaningful analysis steps.
- Inferring implicit dependencies between steps.
- Judging whether a rule is explicit enough to script.
- Generating Python and tests from graph nodes.
- Writing the residual reasoning instructions in `SKILL.md`.
- Explaining runtime failures that are semantic rather than mechanical.

Use scripts when the operation is mechanical, checkable, or repeatable:

- File loading and sample management.
- JSON schema validation.
- Graph reachability and edge validation.
- Regex extraction once patterns are known.
- Timestamp parsing, sorting, grouping, counting, deduplication.
- Running tests.
- Measuring speed and token estimates.
- Capturing runtime traces.
- Checking generated skill bundle structure.

Use hybrid handling when LLM semantics can define a rule and scripts can execute
it:

- The LLM identifies the extraction target and candidate patterns.
- The script implements and validates the extraction.
- The optimized skill keeps an LLM fallback if confidence is low.

## Output Layout

The optimized output should include graph-first compiler artifacts:

```text
<out>/
  SKILL.md
  scripts/
    analyze_text.py
  references/
    analysis-contract.md
    flow-graph.md
    report-format.md
  tests/
    test_analyze_text.py
  samples/
    ...
  compiled/
    source_manifest.json
    flow_graph.raw.json
    flow_graph.json
    graph_validation.json
    contract.json
    solidification.json
    generation.json
    validation.json
    runtime_trace.schema.json
  evaluation/
    baseline-vs-optimized.json
    baseline-vs-optimized.md
```

## Why Not Use BPMN Internally

BPMN and process mining are useful references, but they are not the ideal
internal model for this compiler.

BPMN is strong for business-process control flow. This project needs extra
fields that BPMN does not naturally carry:

- LLM-only reasoning nodes.
- Scriptability and determinism scores.
- Source evidence spans from `SKILL.md`.
- Test coverage metadata.
- Runtime extraction confidence.
- Fallback reasons.
- Token and speed optimization metrics.

The compiler can later export a simplified BPMN, DOT, or Mermaid view for human
inspection, but the internal model should be `SkillFlow Graph`.

## Industry and Research Alignment

The design is related to several existing areas:

- Process model generation from natural-language text. Fabian Friedrich, Jan
  Mendling, and Frank Puhlmann published "Process Model Generation from Natural
  Language Text" at CAiSE 2011:
  https://dblp.uni-trier.de/rec/conf/caise/FriedrichMP11.html
- Text-to-BPMN extraction. A 2024 open-access paper describes extracting BPMN
  models from textual descriptions using NLP, spaCy, BERT, and GPT models:
  https://www.sciencedirect.com/science/article/pii/S187705092401439X
- Universal LLM prompting for process model information extraction. This work
  targets activities, actors, and relations from process descriptions:
  https://arxiv.org/abs/2407.18540
- Procedural knowledge graph extraction. This line extracts steps, actions,
  objects, equipment, and temporal information from procedural text:
  https://arxiv.org/abs/2412.03589 and
  https://github.com/cefriel/procedural-kg-llm
- Procedural graph extraction with structural and logical refinement. This is
  close to the proposed graph-first design because it uses extraction,
  structural feedback, and semantic feedback loops:
  https://arxiv.org/abs/2601.19170
- PM4Py. Useful for runtime trace and process-mining ideas, but it works from
  event logs rather than natural-language skill text:
  https://github.com/process-intelligence-solutions/pm4py
- LangGraph. Useful as a possible graph execution target, but it does not solve
  natural-language-to-graph extraction:
  https://docs.langchain.com/oss/python/langgraph/workflows-agents
- DSPy. Similar compiler mindset for LLM pipelines, but it optimizes LM program
  prompts and modules rather than compiling natural-language skills into
  deterministic scripts:
  https://arxiv.org/abs/2310.03714

The gap this project fills is narrower and more practical: compile
natural-language text-analysis skills into auditable flow graphs and deterministic
Python where safe.

## Validation Strategy

Graph validation:

- JSON schema must pass.
- Every node must have an ID, type, description, owner, inputs, and outputs.
- Entry and exit nodes must exist.
- Non-entry nodes should be reachable.
- Non-exit nodes should feed at least one later node unless marked terminal.
- Conditional edges must name a predicate.
- Scriptable nodes must have test obligations.
- LLM-required nodes must keep enough input context for Claude to reason.

Generated artifact validation:

- Standard Claude skill layout must exist.
- Generated Python tests must pass.
- Analyzer must run on every sample.
- Analyzer output must match the derived handoff schema.
- Handoff JSON must be smaller than passing the full source text when possible.
- `SKILL.md` must mention the analyzer path and residual LLM responsibilities.

Runtime validation:

- Trace file must be JSONL and schema-valid.
- Each trace event should include graph node ID, status, duration, and fallback
  reason when applicable.
- Failed extractions should be replayable as future fixtures.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| LLM invents steps not present in the skill | Require evidence spans and mark unsupported nodes during graph validation. |
| Graph is structurally valid but semantically wrong | Add LLM semantic review pass and sample-based validation. |
| Over-solidification removes useful reasoning | Keep confidence thresholds and LLM fallback paths. |
| Generated Python passes one sample but fails generally | Require multiple samples over time and runtime trace feedback. |
| Graph becomes too complex | Start with a small node/edge taxonomy and avoid BPMN-level completeness. |
| Local models produce malformed JSON | Keep strict JSON parsing, retries, and mock fixtures for tests. |

## Implementation Phases

Phase 1: Graph IR and compiler pass split

- Add `extract_flow_graph`.
- Add `flow_graph.json` schema validation.
- Derive `contract.json` from graph.
- Keep existing generation flow working after the new graph pass.

Phase 2: Node-level solidification

- Replace coarse candidate classification with per-node classification.
- Add scriptability scoring.
- Generate `flow-graph.md` for human review.

Phase 3: Graph-aware artifact generation

- Generate Python only for scriptable nodes.
- Generate residual `SKILL.md` instructions for LLM nodes.
- Add graph-to-code coverage checks.

Phase 4: Runtime tracing

- Add trace schema.
- Make generated analyzers emit node-level trace events.
- Feed runtime failures into repair or next compilation.

Phase 5: Visualization and optional exports

- Export DOT or Mermaid diagrams.
- Optionally export a simplified BPMN-like view.
- Do not make BPMN the internal representation.

## Success Criteria

- The compiler emits a valid `flow_graph.json` for a new text-analysis skill.
- Each generated script function maps back to one or more graph nodes.
- The optimized skill clearly states which graph nodes are handled by Python and
  which remain LLM responsibilities.
- Unit tests pass without a live LLM using mock graph responses.
- A local OpenAI-compatible model can run the live pipeline.
- Runtime trace can identify slow, failed, or fallback-heavy nodes.
- The design remains generic across text-analysis skills, not HM-kernel-specific.
