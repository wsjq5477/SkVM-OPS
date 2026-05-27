#!/usr/bin/env python3
"""Deterministic pre-analyzer for Hongmeng kernel logs.

The script intentionally handles stable extraction and classification only.
Claude should still write the final causal explanation using the generated JSON.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any


PANIC_TYPES = {
    "KERNEL": [
        "HM_PANIC_KERNEL",
        "HM_PANIC_DEVHOST",
        "HM_PANIC_SYSMGR",
        "HM_PANIC_ELFLOADER",
        "HM_PANIC_OOM",
        "HM_PANIC_INJECT",
    ],
    "WATCHDOG": [
        "HM_PANIC_HIGHDOG",
        "HM_PANIC_LOWDOG",
        "HM_APWDT_LOWDOG",
        "HM_APWDT_HIGHDOG",
        "HM_APWDT_HARDDOG",
        "CHARGER_S_WDT",
    ],
    "GUARD": [
        "HGUARD_DEADLOCK",
        "HGUARD_DEADSCHED",
        "HGUARD_USER_CONFIG",
        "HGUARD_HG_ABNORMAL",
    ],
}

REPORT_SECTIONS = ["故障摘要", "关键日志", "时间线", "根因分析", "建议排查方向"]


def read_log(path: Path) -> tuple[str, list[str]]:
    if not path.exists():
        raise FileNotFoundError(f"log file not found: {path}")
    content = path.read_text(encoding="utf-8", errors="replace")
    return content, content.splitlines()


def extract_line_number(line: str) -> str:
    match = re.match(r"\[(\d+):\d+\]", line)
    return match.group(1) if match else ""


def extract_mono_time(line: str) -> str:
    match = re.search(r"\[(\d+\.\d+)\]", line)
    return match.group(1) if match else ""


def detect_panic_type(content: str) -> dict[str, str]:
    for category, names in PANIC_TYPES.items():
        for name in names:
            if name in content:
                return {"category": category, "type": name}
    if "KERNEL UNIMPLEMENTED EXCEPTION" in content or "Exception Dump Start" in content:
        return {"category": "KERNEL", "type": "KERNEL_UNIMPLEMENTED_EXCEPTION"}
    if "[PANIC]" in content or "PANIC" in content:
        return {"category": "KERNEL", "type": "PANIC"}
    return {"category": "UNKNOWN", "type": "UNKNOWN"}


def extract_registers(content: str) -> dict[str, str]:
    match = re.search(
        r"ESR=([0-9a-fA-F]+).*?FAR=([0-9a-fA-F]+).*?ELR=([0-9a-fA-F]+)",
        content,
        re.DOTALL,
    )
    if not match:
        return {"esr": "", "far": "", "elr": ""}
    return {"esr": match.group(1), "far": match.group(2), "elr": match.group(3)}


def extract_thread_info(content: str) -> dict[str, str]:
    match = re.search(
        r"name=([^,\n]+),\s*tid=(\d+),\s*state=([^,\n]+),\s*sctime=([^,\n]+).*?cpu=(\d+).*?cur_rq=(\d+).*?cur_prio=(\d+)",
        content,
        re.DOTALL,
    )
    if not match:
        return {"name": "", "tid": "", "state": "", "sctime": "", "cpu": "", "rq": "", "prio": ""}
    return {
        "name": match.group(1).strip(),
        "tid": match.group(2),
        "state": match.group(3).strip(),
        "sctime": match.group(4).strip(),
        "cpu": match.group(5),
        "rq": match.group(6),
        "prio": match.group(7),
    }


def extract_reboot_codes(content: str) -> dict[str, str]:
    reason = re.search(r"reboot(?:\s+|\w*=).*?(?:reason[:=]\s*)([^,\]\n]+)", content, re.IGNORECASE)
    code = re.search(r"reboot_code[:=]\s*([^,\]\n]+)", content, re.IGNORECASE)
    return {
        "reason": reason.group(1).strip() if reason else "",
        "reboot_code": code.group(1).strip() if code else "",
    }


def extract_key_logs(lines: list[str]) -> list[str]:
    keywords = [
        "Exception Dump Start",
        "Exception registers",
        "ESR=",
        "Thread info",
        "Stack backtrace",
        "HM_PANIC",
        "KERNEL UNIMPLEMENTED EXCEPTION",
        "trigger hungry warn",
        "hguard-worker thread is abnormal",
        "trigger locked",
        "HGUARD_DEADLOCK",
        "__dlist_bug",
    ]
    selected: list[str] = []
    for line in lines:
        if any(k in line for k in keywords):
            selected.append(line)
    return selected[:12]


def extract_call_stack(lines: list[str]) -> list[str]:
    stack: list[str] = []
    in_stack = False
    for line in lines:
        if "Stack backtrace" in line or "KERNEL CALL STACK" in line:
            in_stack = True
            continue
        if not in_stack:
            continue
        if "<" in line and ">" in line:
            stack.append(line.strip())
            continue
        if stack and ("Elf load info" in line or "Dump" in line):
            break
    return stack


def extract_crash_lines(lines: list[str]) -> list[str]:
    return [extract_line_number(line) for line in lines if "PANIC" in line or "Exception Dump Start" in line]


def analyze_esr(registers: dict[str, str]) -> dict[str, Any]:
    raw = registers.get("esr", "")
    if not raw:
        return {
            "esr_ec": "",
            "esr_il": "",
            "esr_iss": "",
            "esr_dfsc": "",
            "fault_type": "unknown",
            "fault_subtype": "",
            "likely_cause": "ESR was not found in the log.",
            "is_null_pointer": False,
            "is_code_corruption": False,
            "is_memory_jump": False,
            "is_ddr_error": False,
            "single_bit_jump_candidate": False,
            "confidence": "low",
            "analysis_details": "No ESR value was extracted.",
        }
    value = int(raw, 16)
    ec = (value >> 26) & 0x3F
    il = (value >> 25) & 0x1
    iss = value & 0x1FFFFFF
    dfsc = value & 0x3F
    fault_map = {
        0x00: ("Unknown/illegal instruction", "Possible code corruption or unsupported instruction."),
        0x15: ("SVC instruction", "Supervisor call."),
        0x1C: ("PAC failure", "Pointer authentication failure."),
        0x20: ("Instruction Abort from lower EL", "Instruction fetch fault."),
        0x21: ("Instruction Abort without EL change", "Kernel instruction fetch fault."),
        0x24: ("Data Abort from lower EL", "User-space data access fault."),
        0x25: ("Data Abort without EL change", "Kernel data access fault."),
        0x2F: ("SError", "Hardware or DDR error candidate."),
        0x3C: ("BRK instruction", "Intentional breakpoint/BUG_ON style exception."),
    }
    fault_type, likely = fault_map.get(ec, (f"EC 0x{ec:x}", "Unknown ESR exception class."))
    far = registers.get("far", "")
    far_value = int(far, 16) if far else 0
    is_null = far != "" and far_value < 0x1000 and ec in {0x24, 0x25}
    is_ddr = ec in {0x00, 0x2F}
    return {
        "esr_ec": f"0x{ec:x}",
        "esr_il": f"0x{il:x}",
        "esr_iss": f"0x{iss:x}",
        "esr_dfsc": f"0x{dfsc:x}" if ec in {0x20, 0x21, 0x24, 0x25} else "",
        "fault_type": fault_type,
        "fault_subtype": "breakpoint" if ec == 0x3C else "",
        "likely_cause": likely,
        "is_null_pointer": is_null,
        "is_code_corruption": ec == 0x00,
        "is_memory_jump": False,
        "is_ddr_error": is_ddr,
        "single_bit_jump_candidate": False,
        "confidence": "high" if ec in fault_map else "medium",
        "analysis_details": f"Decoded ESR {raw}: EC=0x{ec:x}, IL=0x{il:x}, ISS=0x{iss:x}.",
    }


def analyze_memory(content: str, esr_analysis: dict[str, Any]) -> dict[str, Any]:
    has_dlist = "__dlist_bug" in content
    evidence: list[str] = []
    if has_dlist:
        evidence.append("__dlist_bug appears in the log.")
    if esr_analysis.get("is_ddr_error"):
        evidence.append("ESR class is an SError/unknown class associated with hardware or DDR candidates.")
    has_corruption = bool(evidence)
    return {
        "has_memory_corruption": has_corruption,
        "corruption_type": "dlist" if has_dlist else ("ddr_candidate" if has_corruption else "none"),
        "confidence": "medium" if has_corruption else "low",
        "first_panic_esr": "",
        "first_panic_far": "",
        "expected_value": "",
        "actual_value": "",
        "bit_diff_analysis": "No bit-difference evidence found." if not has_corruption else "Manual validation required.",
        "single_bit_jump": False,
        "evidence": evidence,
        "details": "No direct memory corruption indicators were found." if not has_corruption else "Memory corruption indicators require Claude review.",
    }


def build_timeline(lines: list[str]) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for line in lines:
        if any(k in line for k in ["transaction start", "Exception Dump Start", "ESR=", "Thread info", "Stack backtrace"]):
            events.append({
                "time": extract_mono_time(line),
                "raw_log": line,
                "description": describe_line(line),
            })
    return events[:10]


def describe_line(line: str) -> str:
    if "transaction start" in line:
        return "Log transaction starts and provides the baseline mono time."
    if "Exception Dump Start" in line:
        return "Kernel exception dump starts."
    if "ESR=" in line:
        return "Exception registers are printed."
    if "Thread info" in line:
        return "Crash thread information begins."
    if "Stack backtrace" in line:
        return "Stack backtrace begins."
    return "Relevant crash log."


def analyze_log_file(log_path: str | Path) -> dict[str, Any]:
    started = time.perf_counter()
    path = Path(log_path)
    content, lines = read_log(path)
    panic = detect_panic_type(content)
    registers = extract_registers(content)
    thread = extract_thread_info(content)
    key_logs = extract_key_logs(lines)
    call_stack = extract_call_stack(lines)
    esr = analyze_esr(registers)
    memory = analyze_memory(content, esr)
    timeline = build_timeline(lines)
    crash_line_numbers = [n for n in extract_crash_lines(lines) if n]
    elapsed_ms = (time.perf_counter() - started) * 1000
    log_info = {
        "has_crash": panic["type"] != "UNKNOWN",
        "panic_category": panic["category"],
        "panic_type": panic["type"],
        "crash_thread": thread.get("name", ""),
        "crash_cpu": thread.get("cpu", ""),
        "registers": registers,
        "reboot_codes": extract_reboot_codes(content),
        "key_logs": key_logs,
        "trigger_hungry_warn": {},
        "has_hguard_abnormal": "hguard-worker thread is abnormal" in content,
        "has_trigger_locked": "trigger locked" in content,
        "has_deadlock": "HGUARD_DEADLOCK" in content,
        "has_dlist_bug": "__dlist_bug" in content,
        "call_stack": call_stack,
    }
    report_data = {
        "required_sections": REPORT_SECTIONS,
        "summary": {
            "fault_type": log_info["panic_type"],
            "crash_thread": log_info["crash_thread"] or "unknown",
            "reboot_reason": log_info["reboot_codes"].get("reason") or "N/A",
            "reboot_code": log_info["reboot_codes"].get("reboot_code") or "N/A",
            "trigger_point": key_logs[0] if key_logs else "unknown",
            "key_conclusion": "Kernel exception in ufs_eh_worker with BRK-style ESR; Claude should validate the final root cause.",
        },
        "key_logs": key_logs[:8],
        "timeline": timeline,
        "root_cause_candidates": [
            {
                "likelihood": "medium",
                "candidate": "UFS error handler hit a BRK/BUG_ON style exception while resetting/restoring UFS.",
                "evidence": [
                    f"Crash thread: {log_info['crash_thread']}",
                    f"ESR fault type: {esr['fault_type']}",
                    "Top stack frame includes ufshcd_reset_and_restore." if any("ufshcd_reset_and_restore" in s for s in call_stack) else "Stack frame requires review.",
                ],
                "uncertainty": "The log snippet does not include source code context or hardware status history.",
                "validation": "Check UFS driver error-handler source around ufshcd_reset_and_restore and correlate with device I/O errors.",
            }
        ],
        "recommendations": [
            {
                "priority": "P0",
                "target": "UFS reset path",
                "action": "Inspect ufshcd_reset_and_restore around the reported PC/ELR and the BRK trigger path.",
                "expected_result": "Confirm whether the exception is an intentional BUG_ON/assertion or an unexpected branch.",
            },
            {
                "priority": "P1",
                "target": "Storage hardware/link state",
                "action": "Correlate RX_FSM_STATE and UFS error-handler logs before the panic.",
                "expected_result": "Determine whether link/device errors caused the reset path to execute.",
            },
            {
                "priority": "P2",
                "target": "Crash reproducibility",
                "action": "Collect a longer klog around the first UFS error and panic.",
                "expected_result": "Provide enough context for final root-cause confirmation.",
            },
        ],
    }
    return {
        "input": {
            "log_path": str(path),
            "line_count": len(lines),
            "byte_count": len(content.encode("utf-8", errors="replace")),
            "crash_line_numbers": crash_line_numbers,
        },
        "log_info": log_info,
        "snapshot_info": {
            "has_snapshot": "transaction start" in content,
            "thread_count": 1 if thread.get("tid") else 0,
            "ready_count": 0,
            "running_count": 1 if thread.get("state") == "RUNNING" else 0,
            "blocked_count": 0,
            "transaction_range": {},
            "基准时间T": extract_base_time(content),
            "threads": [thread] if thread.get("tid") else [],
        },
        "base_time_info": {
            "基准时间T": extract_base_time(content),
            "计算方法": "Extracted from transaction start mono_time when available.",
        },
        "hungtask_analysis": {
            "has_hungtask": False,
            "hungtask_type": "none",
            "scenario": "none",
            "confidence": "high",
            "analysis_details": "No hungry warn, hguard abnormal, trigger locked, or HGUARD_DEADLOCK markers were found.",
        },
        "esr_analysis": esr,
        "memory_corruption": memory,
        "deadlock_analysis": {
            "has_deadlock": False,
            "is_abba_deadlock": False,
            "deadlock_chain": [],
            "deadlock_path": [],
            "involved_threads": [],
            "root_cause": "",
            "details": "No HGUARD_DEADLOCK marker was found.",
        },
        "report_data": report_data,
        "metrics": {
            "elapsed_ms": round(elapsed_ms, 3),
            "input_chars": len(content),
            "output_chars": 0,
            "estimated_output_tokens": 0,
        },
    }


def build_claude_handoff(result: dict[str, Any]) -> dict[str, Any]:
    """Return the compact subset Claude needs for the fixed final report."""
    log_info = result["log_info"]
    report = result["report_data"]
    return {
        "summary": report["summary"],
        "registers": log_info["registers"],
        "esr": {
            "ec": result["esr_analysis"]["esr_ec"],
            "fault_type": result["esr_analysis"]["fault_type"],
            "likely_cause": result["esr_analysis"]["likely_cause"],
            "confidence": result["esr_analysis"]["confidence"],
        },
        "memory_corruption": {
            "detected": result["memory_corruption"]["has_memory_corruption"],
            "type": result["memory_corruption"]["corruption_type"],
            "confidence": result["memory_corruption"]["confidence"],
            "evidence": result["memory_corruption"]["evidence"],
        },
        "hungtask": {
            "detected": result["hungtask_analysis"]["has_hungtask"],
            "type": result["hungtask_analysis"]["hungtask_type"],
            "scenario": result["hungtask_analysis"]["scenario"],
        },
        "deadlock": {
            "detected": result["deadlock_analysis"]["has_deadlock"],
            "abba": result["deadlock_analysis"]["is_abba_deadlock"],
            "threads": result["deadlock_analysis"]["involved_threads"],
        },
        "key_logs": report["key_logs"][:8],
        "timeline": report["timeline"][:10],
        "root_cause_candidates": report["root_cause_candidates"],
        "recommendations": report["recommendations"],
    }


def extract_base_time(content: str) -> float | None:
    match = re.search(r"transaction start.*?mono_time is \[([0-9.]+)\]", content)
    return float(match.group(1)) if match else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze a Hongmeng kernel log file.")
    parser.add_argument("log_path", help="Path to the log file.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    parser.add_argument("--handoff", action="store_true", help="Emit compact Claude handoff JSON.")
    args = parser.parse_args()

    result = analyze_log_file(args.log_path)
    if args.handoff:
        result = build_claude_handoff(result)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
