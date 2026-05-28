#!/usr/bin/env python3
"""Generic LLM-driven compiler for text-analysis Claude skills."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, data: Any) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / 4))


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def validate_flow_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Validate the natural-language execution-flow graph shape."""
    errors: list[str] = []
    warnings: list[str] = []
    required_keys = ["graph_id", "entry_nodes", "exit_nodes", "nodes", "edges"]
    for key in required_keys:
        if key not in graph:
            errors.append(f"missing required graph key: {key}")

    nodes = _as_list(graph.get("nodes"))
    edges = _as_list(graph.get("edges"))
    entry_nodes = [str(n) for n in _as_list(graph.get("entry_nodes"))]
    exit_nodes = [str(n) for n in _as_list(graph.get("exit_nodes"))]
    node_ids: set[str] = set()
    duplicate_ids: set[str] = set()

    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"node {index} must be an object")
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            errors.append(f"node {index} is missing non-empty id")
            continue
        if node_id in node_ids:
            duplicate_ids.add(node_id)
        node_ids.add(node_id)
        for field in ["type", "description", "inputs", "outputs", "owner"]:
            if field not in node:
                errors.append(f"node {node_id} is missing required field: {field}")
        if "inputs" in node and not isinstance(node["inputs"], list):
            errors.append(f"node {node_id} inputs must be a list")
        if "outputs" in node and not isinstance(node["outputs"], list):
            errors.append(f"node {node_id} outputs must be a list")

    for node_id in sorted(duplicate_ids):
        errors.append(f"duplicate node id: {node_id}")
    for node_id in entry_nodes:
        if node_id not in node_ids:
            errors.append(f"entry node is not defined: {node_id}")
    for node_id in exit_nodes:
        if node_id not in node_ids:
            errors.append(f"exit node is not defined: {node_id}")
    if not entry_nodes:
        errors.append("entry_nodes must contain at least one node id")
    if not exit_nodes:
        errors.append("exit_nodes must contain at least one node id")

    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"edge {index} must be an object")
            continue
        source = edge.get("from")
        target = edge.get("to")
        kind = edge.get("kind")
        if not isinstance(source, str) or not source:
            errors.append(f"edge {index} is missing non-empty from")
            continue
        if not isinstance(target, str) or not target:
            errors.append(f"edge {index} is missing non-empty to")
            continue
        if not isinstance(kind, str) or not kind:
            errors.append(f"edge {index} is missing non-empty kind")
        if source not in node_ids:
            errors.append(f"edge {index} source is not defined: {source}")
        if target not in node_ids:
            errors.append(f"edge {index} target is not defined: {target}")
        if source in adjacency and target in node_ids:
            adjacency[source].append(target)

    reachable: set[str] = set()
    stack = [node_id for node_id in entry_nodes if node_id in node_ids]
    while stack:
        node_id = stack.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        stack.extend(adjacency.get(node_id, []))
    for node_id in sorted(node_ids - reachable):
        warnings.append(f"node is not reachable from entry nodes: {node_id}")

    return {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "reachable_nodes": sorted(reachable),
    }


def derive_contract_from_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Derive a v1-compatible contract from a SkillFlow graph."""
    nodes = [node for node in _as_list(graph.get("nodes")) if isinstance(node, dict)]
    entities: list[str] = []
    deterministic_operations: list[str] = []
    residual_reasoning: list[str] = []
    report_sections: list[str] = []
    deterministic_types = {"load_input", "chunk", "extract", "normalize", "filter", "aggregate", "decide", "validate"}
    residual_types = {"classify", "reason", "report", "fallback"}
    deterministic_owners = {"script", "script_candidate", "python_ready"}
    residual_owners = {"llm", "llm_only", "llm_required"}

    input_mode = "text"
    for node in nodes:
        node_id = str(node.get("id", ""))
        node_type = str(node.get("type", ""))
        owner = str(node.get("owner", ""))
        description = str(node.get("description", ""))
        inputs = [str(item) for item in _as_list(node.get("inputs"))]
        outputs = [str(item) for item in _as_list(node.get("outputs"))]

        if node_type == "load_input" and ("file_path" in inputs or "file" in description.lower()):
            input_mode = "file_path"
        if node_type in {"extract", "normalize", "classify"}:
            for output in outputs:
                if output not in {"log_text", "chunks", "final_report"}:
                    _append_unique(entities, output)
        if owner in deterministic_owners or node_type in deterministic_types:
            _append_unique(deterministic_operations, node_id)
        if owner in residual_owners or node_type in residual_types:
            _append_unique(residual_reasoning, node_id)
        if node_type == "report":
            for output in outputs:
                _append_unique(report_sections, output)

    if not report_sections:
        report_sections = ["summary", "timeline", "root_cause_analysis", "recommendations"]

    return {
        "input_mode": input_mode,
        "report_sections": report_sections,
        "entities": entities,
        "deterministic_operations": deterministic_operations,
        "residual_reasoning": residual_reasoning,
        "failure_modes": [
            "file not found",
            "invalid flow graph",
            "missing required extracted evidence",
            "low-confidence deterministic extraction",
        ],
    }


class LLMClient:
    def complete_json(self, pass_name: str, prompt: str) -> dict[str, Any]:
        raise NotImplementedError


class MockLLMClient(LLMClient):
    def __init__(self, directory: Path):
        self.directory = directory
        self.calls = 0

    def complete_json(self, pass_name: str, prompt: str) -> dict[str, Any]:
        self.calls += 1
        candidates = [
            self.directory / f"{self.calls:02d}_{pass_name}.json",
            self.directory / f"{self.calls:02d}.json",
        ]
        for path in candidates:
            if path.exists():
                return json.loads(read_text(path))
        raise FileNotFoundError(f"missing mock LLM response for call {self.calls} pass {pass_name}: {candidates[0]}")


class OpenAICompatibleClient(LLMClient):
    def __init__(self, base_url: str, api_key: str, model: str, extra_headers: dict[str, str] | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.extra_headers = extra_headers or {}

    def complete_json(self, pass_name: str, prompt: str) -> dict[str, Any]:
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Return only valid JSON. No markdown."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                **self.extra_headers,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        return json.loads(content)


class AnthropicClient(LLMClient):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def complete_json(self, pass_name: str, prompt: str) -> dict[str, Any]:
        body = json.dumps({
            "model": self.model,
            "max_tokens": 8192,
            "temperature": 0,
            "messages": [{"role": "user", "content": "Return only valid JSON. No markdown.\n\n" + prompt}],
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = "".join(part.get("text", "") for part in payload.get("content", []) if part.get("type") == "text")
        return json.loads(content)


@dataclass
class CompileConfig:
    skill: Path
    samples: list[Path]
    out: Path
    name: str
    max_repair_rounds: int


def build_client(args: argparse.Namespace) -> LLMClient:
    if args.mock_llm:
        return MockLLMClient(Path(args.mock_llm))
    provider = args.provider
    model = args.model
    if provider == "openai":
        key = args.api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise SystemExit("OPENAI_API_KEY or --api-key is required for --provider openai")
        return OpenAICompatibleClient("https://api.openai.com/v1", key, model)
    if provider == "openrouter":
        key = args.api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise SystemExit("OPENROUTER_API_KEY or --api-key is required for --provider openrouter")
        return OpenAICompatibleClient(
            "https://openrouter.ai/api/v1",
            key,
            model,
            {"HTTP-Referer": "https://github.com/wsjq5477/SkVM-OPS", "X-Title": "Text Skill Compiler"},
        )
    if provider == "local":
        if not args.base_url:
            raise SystemExit("--base-url is required for --provider local")
        key = args.api_key or os.environ.get("LOCAL_LLM_API_KEY") or "local"
        return OpenAICompatibleClient(args.base_url, key, model)
    if provider == "anthropic":
        key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise SystemExit("ANTHROPIC_API_KEY or --api-key is required for --provider anthropic")
        normalized = model.split("/", 1)[1] if model.startswith("anthropic/") else model
        return AnthropicClient(key, normalized)
    raise SystemExit(f"unsupported provider: {provider}")


def prompt_extract_flow_graph(skill_text: str, sample_texts: list[str]) -> str:
    return "\n".join([
        "Analyze this text-analysis skill/workflow and convert it into a SkillFlow execution graph.",
        "Return only JSON with keys: graph_id, entry_nodes, exit_nodes, nodes, edges.",
        "Each node must include: id, type, description, inputs, outputs, owner, determinism.",
        "Use node types such as load_input, chunk, extract, normalize, filter, aggregate, classify, decide, reason, report, validate, fallback.",
        "Use owner values such as script, script_candidate, hybrid, llm_required.",
        "Use edge kinds such as sequence, data_dependency, condition_true, condition_false, loop, fallback.",
        "Ground nodes in the source skill when possible using evidence_spans with source and quote.",
        "Skill/workflow:",
        skill_text[:30000],
        "Sample snippets:",
        "\n---\n".join(s[:4000] for s in sample_texts),
    ])


def normalize_flow_graph(response: dict[str, Any]) -> dict[str, Any]:
    graph = response.get("graph")
    if isinstance(graph, dict):
        return graph
    return response


def merge_contract_with_graph_defaults(contract: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    merged = derive_contract_from_graph(graph)
    for key, value in contract.items():
        if value not in (None, [], {}, ""):
            merged[key] = value
    return merged


def prompt_extract_contract(skill_text: str, sample_texts: list[str], flow_graph: dict[str, Any] | None = None) -> str:
    parts = [
        "Analyze this text-analysis skill/workflow and extract a JSON contract.",
        "Required keys: input_mode, report_sections, entities, deterministic_operations, residual_reasoning, failure_modes.",
    ]
    if flow_graph is not None:
        parts.extend([
            "Use this SkillFlow graph as the primary execution-flow source. Keep the contract compatible with the graph nodes.",
            json.dumps(flow_graph, ensure_ascii=False),
        ])
    parts.extend([
        "Skill/workflow:",
        skill_text[:30000],
        "Sample snippets:",
        "\n---\n".join(s[:4000] for s in sample_texts),
    ])
    return "\n".join(parts)


def prompt_find_solidification(contract: dict[str, Any], skill_text: str, flow_graph: dict[str, Any] | None = None) -> str:
    parts = [
        "Classify which graph nodes and text-analysis operations can be solidified into Python.",
        "Return JSON with key candidates: array of {id, kind, description, outputs}. kind is python_ready, hybrid, or llm_only.",
        "Prefer node IDs from the SkillFlow graph when available.",
        "Contract:",
        json.dumps(contract, ensure_ascii=False),
    ]
    if flow_graph is not None:
        parts.extend([
            "SkillFlow graph:",
            json.dumps(flow_graph, ensure_ascii=False),
        ])
    parts.extend([
        "Skill/workflow:",
        skill_text[:30000],
    ])
    return "\n".join(parts)


def prompt_generate_artifacts(
    name: str,
    contract: dict[str, Any],
    solidification: dict[str, Any],
    flow_graph: dict[str, Any] | None = None,
) -> str:
    parts = [
        "Generate a complete optimized Claude skill bundle for this text-analysis skill.",
        "Return JSON with key files, mapping relative path to full file content.",
        "Required files: SKILL.md, scripts/analyze_text.py, references/report-format.md, references/analysis-contract.md, tests/test_analyze_text.py.",
        "The generated skill should run deterministic Python first and leave residual graph nodes to Claude.",
        f"Skill name: {name}",
        "Contract:",
        json.dumps(contract, ensure_ascii=False),
        "Solidification:",
        json.dumps(solidification, ensure_ascii=False),
    ]
    if flow_graph is not None:
        parts.extend([
            "SkillFlow graph:",
            json.dumps(flow_graph, ensure_ascii=False),
        ])
    return "\n".join(parts)


def prompt_repair(files: dict[str, str], validation: dict[str, Any]) -> str:
    return "\n".join([
        "The generated text-analysis skill failed validation. Return a replacement JSON with key files mapping paths to full file contents.",
        "You may replace only files that need repair, or return all files.",
        "Validation:",
        json.dumps(validation, ensure_ascii=False),
        "Current files:",
        json.dumps(files, ensure_ascii=False)[:40000],
    ])


def copy_samples(samples: list[Path], out: Path) -> list[Path]:
    dest_dir = out / "samples"
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for sample in samples:
        target = dest_dir / sample.name
        shutil.copyfile(sample, target)
        copied.append(target)
    return copied


def write_generated_files(out: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        if rel.startswith("/") or ".." in Path(rel).parts:
            raise ValueError(f"unsafe generated path: {rel}")
        write_text(out / rel, content)


def run_command(command: list[str], cwd: Path) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "elapsed_ms": round(elapsed_ms, 3),
    }


def validate_output(out: Path, sample: Path) -> dict[str, Any]:
    tests = run_command([sys.executable, "-m", "unittest", "discover", "-s", "tests"], out)
    analyzer = out / "scripts" / "analyze_text.py"
    analysis = run_command([sys.executable, str(analyzer), str(sample), "--handoff"], out)
    status = "passed" if tests["exit_code"] == 0 and analysis["exit_code"] == 0 else "failed"
    parsed: dict[str, Any] | None = None
    if analysis["exit_code"] == 0:
        try:
            parsed = json.loads(analysis["stdout"])
        except json.JSONDecodeError:
            status = "failed"
    return {"status": status, "tests": tests, "analysis": analysis, "analysis_json": parsed}


def evaluate_output(skill_text: str, sample_text: str, out: Path, analysis_json: dict[str, Any], analyzer_elapsed_ms: float) -> dict[str, Any]:
    optimized_context = read_text(out / "SKILL.md")
    report_ref = out / "references" / "report-format.md"
    if report_ref.exists():
        optimized_context += "\n\n" + read_text(report_ref)
    optimized_context += "\n\n" + json.dumps(analysis_json, ensure_ascii=False, separators=(",", ":"))
    baseline_tokens = estimate_tokens(skill_text + "\n\n" + sample_text)
    optimized_tokens = estimate_tokens(optimized_context)
    summary = analysis_json.get("summary", {}) if isinstance(analysis_json, dict) else {}
    comparison = {
        "baseline_estimated_input_tokens": baseline_tokens,
        "optimized_estimated_input_tokens": optimized_tokens,
        "estimated_token_reduction_percent": round(100 * (1 - optimized_tokens / baseline_tokens), 1) if baseline_tokens else 0,
        "optimized_analyzer_elapsed_ms": analyzer_elapsed_ms,
        "token_estimation_method": "round(characters / 4)",
        "live_llm_execution": False,
    }
    return {
        "comparison": comparison,
        "result_summary": {
            "fault_type": summary.get("fault_type", ""),
            "crash_thread": summary.get("crash_thread", ""),
            "crash_cpu": summary.get("crash_cpu", ""),
        },
    }


def write_evaluation(out: Path, evaluation: dict[str, Any]) -> None:
    eval_dir = out / "evaluation"
    write_json(eval_dir / "baseline-vs-optimized.json", evaluation)
    c = evaluation["comparison"]
    r = evaluation["result_summary"]
    write_text(
        eval_dir / "baseline-vs-optimized.md",
        "\n".join([
            "# Baseline vs Optimized Evaluation",
            "",
            f"- Fault type: `{r.get('fault_type', '')}`",
            f"- Crash thread: `{r.get('crash_thread', '')}`",
            f"- Optimized analyzer elapsed: `{c['optimized_analyzer_elapsed_ms']} ms`",
            f"- Baseline estimated input tokens: `{c['baseline_estimated_input_tokens']}`",
            f"- Optimized estimated input tokens: `{c['optimized_estimated_input_tokens']}`",
            f"- Estimated token reduction: `{c['estimated_token_reduction_percent']}%`",
            "",
            "Token counts are local estimates, not provider billing.",
        ]),
    )


def compile_skill(config: CompileConfig, client: LLMClient) -> dict[str, Any]:
    config.out.mkdir(parents=True, exist_ok=True)
    sample_copies = copy_samples(config.samples, config.out)
    skill_text = read_text(config.skill)
    sample_texts = [read_text(p) for p in config.samples]
    compiled = config.out / "compiled"

    raw_flow_graph = client.complete_json("extract_flow_graph", prompt_extract_flow_graph(skill_text, sample_texts))
    write_json(compiled / "flow_graph.raw.json", raw_flow_graph)
    flow_graph = normalize_flow_graph(raw_flow_graph)
    write_json(compiled / "flow_graph.json", flow_graph)
    graph_validation = validate_flow_graph(flow_graph)
    write_json(compiled / "graph_validation.json", graph_validation)
    if graph_validation["status"] != "passed":
        raise SystemExit("flow graph validation failed; see compiled/graph_validation.json")

    extracted_contract = client.complete_json("extract_contract", prompt_extract_contract(skill_text, sample_texts, flow_graph))
    contract = merge_contract_with_graph_defaults(extracted_contract, flow_graph)
    write_json(compiled / "contract.json", contract)
    solidification = client.complete_json("find_solidification", prompt_find_solidification(contract, skill_text, flow_graph))
    write_json(compiled / "solidification.json", solidification)
    generation = client.complete_json("generate_artifacts", prompt_generate_artifacts(config.name, contract, solidification, flow_graph))
    write_json(compiled / "generation.json", generation)
    files = generation.get("files")
    if not isinstance(files, dict):
        raise ValueError("generate_artifacts response must contain object key 'files'")
    write_generated_files(config.out, files)

    repair_rounds = 0
    validation = validate_output(config.out, sample_copies[0])
    while validation["status"] != "passed" and repair_rounds < config.max_repair_rounds:
        repair_rounds += 1
        repair = client.complete_json("repair", prompt_repair(files, validation))
        repair_files = repair.get("files")
        if not isinstance(repair_files, dict):
            raise ValueError("repair response must contain object key 'files'")
        files.update(repair_files)
        write_generated_files(config.out, repair_files)
        validation = validate_output(config.out, sample_copies[0])
    validation["repair_rounds"] = repair_rounds
    write_json(compiled / "validation.json", validation)
    if validation["status"] != "passed":
        raise SystemExit("validation failed; see compiled/validation.json")

    analysis_json = validation["analysis_json"] or {}
    evaluation = evaluate_output(skill_text, sample_texts[0], config.out, analysis_json, validation["analysis"]["elapsed_ms"])
    write_evaluation(config.out, evaluation)
    return {"status": "compiled", "out": str(config.out), "evaluation": evaluation}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile a text-analysis skill into an optimized Claude skill.")
    parser.add_argument("--skill", required=True, help="Path to source SKILL.md or workflow file.")
    parser.add_argument("--sample", action="append", required=True, help="Path to a sample text/log file. Repeatable.")
    parser.add_argument("--out", required=True, help="Output skill directory.")
    parser.add_argument("--name", required=True, help="Optimized skill name.")
    parser.add_argument("--mock-llm", help="Directory of numbered mock JSON responses.")
    parser.add_argument("--provider", default="openrouter", choices=["openai", "openrouter", "anthropic", "local"], help="Live LLM provider.")
    parser.add_argument("--model", default="openrouter/anthropic/claude-sonnet-4.6", help="Model id for live providers.")
    parser.add_argument("--base-url", help="OpenAI-compatible base URL for --provider local, for example http://127.0.0.1:8000/v1.")
    parser.add_argument("--api-key", help="API key override. Optional for --provider local; defaults to LOCAL_LLM_API_KEY or 'local'.")
    parser.add_argument("--max-repair-rounds", type=int, default=2)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    config = CompileConfig(
        skill=Path(args.skill).resolve(),
        samples=[Path(p).resolve() for p in args.sample],
        out=Path(args.out).resolve(),
        name=args.name,
        max_repair_rounds=args.max_repair_rounds,
    )
    result = compile_skill(config, build_client(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
