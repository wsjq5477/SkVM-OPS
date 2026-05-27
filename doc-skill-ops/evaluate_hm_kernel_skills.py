#!/usr/bin/env python3
"""Evaluate baseline and optimized HM kernel log skills locally.

This does not call Claude. It measures deterministic script behavior and
estimates prompt/token footprint for the two skill shapes.
"""

from __future__ import annotations

import importlib.util
import json
import statistics
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "doc-skill-ops"
LOG = WORK / "test_log.txt"
BASELINE_SKILL = WORK / "skills" / "hm-kernel-logs-baseline" / "SKILL.md"
OPT_SKILL = WORK / "skills" / "hm-kernel-logs-optimized" / "SKILL.md"
OPT_REFS = [
    WORK / "skills" / "hm-kernel-logs-optimized" / "references" / "report-format.md",
    WORK / "skills" / "hm-kernel-logs-optimized" / "references" / "analysis-contract.md",
]
ANALYZER = WORK / "skills" / "hm-kernel-logs-optimized" / "scripts" / "analyze_hm_kernel_log.py"
OUT_DIR = WORK / "evaluation"


def load_analyzer():
    spec = importlib.util.spec_from_file_location("analyze_hm_kernel_log", ANALYZER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def estimate_tokens(text: str) -> int:
    # Conservative, model-agnostic estimate for mixed English/code/log text.
    # This is not a provider bill; it is a consistent local comparison metric.
    return max(1, round(len(text) / 4))


def compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def measure_script(runs: int = 15) -> tuple[dict[str, Any], list[float]]:
    analyzer = load_analyzer()
    timings: list[float] = []
    result: dict[str, Any] | None = None
    for _ in range(runs):
        started = time.perf_counter()
        result = analyzer.analyze_log_file(LOG)
        timings.append((time.perf_counter() - started) * 1000)
    assert result is not None
    return result, timings


def build_markdown_report(evaluation: dict[str, Any]) -> str:
    result = evaluation["optimized_result"]
    log_info = result["log_info"]
    esr = result["esr_analysis"]
    mem = result["memory_corruption"]
    metrics = evaluation["comparison"]
    return "\n".join([
        "# HM Kernel Log Skill Evaluation",
        "",
        "## Result Summary",
        "",
        f"- Panic type: `{log_info['panic_type']}` ({log_info['panic_category']})",
        f"- Crash thread: `{log_info['crash_thread']}` on CPU `{log_info['crash_cpu']}`",
        f"- Registers: ESR `{log_info['registers']['esr']}`, FAR `{log_info['registers']['far']}`, ELR `{log_info['registers']['elr']}`",
        f"- ESR fault type: `{esr['fault_type']}`; likely cause: {esr['likely_cause']}",
        f"- Memory corruption detected by deterministic script: `{mem['has_memory_corruption']}` ({mem['corruption_type']})",
        f"- Hungtask detected by deterministic script: `{result['hungtask_analysis']['has_hungtask']}`",
        f"- Deadlock detected by deterministic script: `{result['deadlock_analysis']['has_deadlock']}`",
        "",
        "## Speed",
        "",
        f"- Optimized analyzer median runtime: `{metrics['optimized_script_median_ms']:.3f} ms` over {metrics['script_runs']} local runs.",
        f"- Optimized analyzer min/max runtime: `{metrics['optimized_script_min_ms']:.3f} / {metrics['optimized_script_max_ms']:.3f} ms`.",
        "- Baseline text-only skill has no local deterministic runtime; it requires a live Claude run over the full workflow and log.",
        "",
        "## Token Footprint Estimate",
        "",
        f"- Baseline estimated input tokens: `{metrics['baseline_estimated_input_tokens']}`.",
        f"- Optimized estimated input tokens: `{metrics['optimized_estimated_input_tokens']}`.",
        f"- Estimated reduction: `{metrics['estimated_token_reduction_percent']:.1f}%`.",
        "",
        "Token counts are local estimates using `chars / 4`; they are for apples-to-apples comparison, not provider billing.",
        "",
        "## Quality Notes",
        "",
        "- The optimized script extracts stable facts before Claude writes the report.",
        "- Claude still owns root-cause wording, uncertainty, and engineering recommendations.",
        "- For this sample, deterministic evidence points to a BRK-style exception in `ufs_eh_worker`, with stack frames in the UFS reset/error-handler path.",
        "",
    ])


def build_draft_final_report(handoff: dict[str, Any]) -> str:
    summary = handoff["summary"]
    registers = handoff["registers"]
    esr = handoff["esr"]
    mem = handoff["memory_corruption"]
    hungtask = handoff["hungtask"]
    deadlock = handoff["deadlock"]
    key_rows = "\n".join(
        f"| {extract_time(row)} | {escape_cell(row)} |" for row in handoff["key_logs"][:8]
    )
    timeline_rows = "\n".join(
        f"| {item.get('time') or 'N/A'} | {escape_cell(item.get('raw_log', ''))} | {escape_cell(item.get('description', ''))} |"
        for item in handoff["timeline"][:10]
    )
    candidate = handoff["root_cause_candidates"][0]
    rec_rows = "\n".join(
        f"| {rec['priority']} | {escape_cell(rec['target'])} | {escape_cell(rec['action'])} | {escape_cell(rec['expected_result'])} |"
        for rec in handoff["recommendations"]
    )
    return "\n".join([
        "# 1、故障摘要",
        "",
        f"- 故障类型: {summary['fault_type']}",
        f"- 崩溃进程/线程: {summary['crash_thread']}",
        f"- 重启原因: {summary['reboot_reason']}",
        f"- 故障编码: {summary['reboot_code']}",
        f"- 触发时间点: {summary['trigger_point']}",
        f"- 关键结论: {summary['key_conclusion']}",
        "",
        "# 2、关键日志",
        "",
        "| 时间 | 日志内容 |",
        "|---|---|",
        key_rows,
        "",
        "# 3、时间线",
        "",
        "| 时间 | 真实日志 | 简介描述 |",
        "|---|---|---|",
        timeline_rows,
        "",
        "# 4、根因分析",
        "",
        "事实:",
        f"- 崩溃线程为 `{summary['crash_thread']}`，ESR=`{registers['esr']}`，FAR=`{registers['far']}`，ELR=`{registers['elr']}`。",
        f"- ESR 解码为 `{esr['fault_type']}`，置信度 `{esr['confidence']}`。",
        f"- 内存损坏脚本检测结果为 `{mem['detected']}`，类型 `{mem['type']}`。",
        f"- Hungtask 检测结果为 `{hungtask['detected']}`，死锁检测结果为 `{deadlock['detected']}`。",
        "",
        "推理:",
        f"- 可能性: {candidate['likelihood']}",
        f"- 根因候选: {candidate['candidate']}",
        f"- 判断依据: {'; '.join(candidate['evidence'])}",
        "",
        "不确定点:",
        f"- {candidate['uncertainty']}",
        f"- 验证方式: {candidate['validation']}",
        "",
        "# 5、建议排查方向",
        "",
        "| 优先级 | 目标 | 动作 | 预期结果 |",
        "|---|---|---|---|",
        rec_rows,
        "",
    ])


def escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def extract_time(line: str) -> str:
    start = line.find("[", line.find("]") + 1)
    if start == -1:
        return "N/A"
    end = line.find("]", start)
    return line[start + 1:end] if end != -1 else "N/A"


def main() -> int:
    result, timings = measure_script()
    analyzer = load_analyzer()
    handoff = analyzer.build_claude_handoff(result)
    log_text = read_text(LOG)
    baseline_prompt = read_text(BASELINE_SKILL) + "\n\n" + log_text
    optimized_context = (
        read_text(OPT_SKILL)
        + "\n\n"
        + read_text(OPT_REFS[0])
        + "\n\n"
        + compact_json(handoff)
    )
    baseline_tokens = estimate_tokens(baseline_prompt)
    optimized_tokens = estimate_tokens(optimized_context)
    reduction = 100 * (1 - optimized_tokens / baseline_tokens)
    evaluation = {
        "inputs": {
            "log": str(LOG),
            "baseline_skill": str(BASELINE_SKILL),
            "optimized_skill": str(OPT_SKILL),
            "analyzer": str(ANALYZER),
        },
        "comparison": {
            "script_runs": len(timings),
            "optimized_script_median_ms": round(statistics.median(timings), 3),
            "optimized_script_min_ms": round(min(timings), 3),
            "optimized_script_max_ms": round(max(timings), 3),
            "baseline_estimated_input_tokens": baseline_tokens,
            "optimized_estimated_input_tokens": optimized_tokens,
            "estimated_token_reduction_percent": round(reduction, 1),
            "token_estimation_method": "round(characters / 4)",
            "live_claude_execution": False,
        },
        "optimized_result": result,
        "optimized_claude_handoff": handoff,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "hm-kernel-log-evaluation.json").write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUT_DIR / "hm-kernel-log-evaluation.md").write_text(
        build_markdown_report(evaluation),
        encoding="utf-8",
    )
    (OUT_DIR / "hm-kernel-log-optimized-draft-report.md").write_text(
        build_draft_final_report(handoff),
        encoding="utf-8",
    )
    print(json.dumps(evaluation["comparison"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
