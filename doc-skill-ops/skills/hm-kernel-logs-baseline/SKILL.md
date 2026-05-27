---
name: hm-kernel-logs-baseline
description: Text-only Claude skill converted from hm-kernel-logs.js for Hongmeng kernel log file analysis. Use when the user provides a Hongmeng/OpenHarmony kernel klog file path and asks for panic, ESR, Hungtask, memory-corruption, deadlock, or root-cause analysis. This baseline skill performs the workflow in natural language without bundled parser scripts.
---

# Hongmeng Kernel Log Analysis Baseline

Analyze one English Hongmeng kernel log file path. The workflow is a text conversion of `doc-skill-ops/hm-kernel-logs.js`.

## Input

Accept a single file path, or an object-like request with `logPath`. Read the file with shell tools. If the file is large, inspect the first 2000 lines, then extract windows around `PANIC`, `ESR=`, `FAR=`, and `ELR=`.

## Workflow Phases

1. **Read log**
   - Read the log file.
   - Record full log size and crash-related line numbers.

2. **Parse log**
   - Confirm crash with `KERNEL UNIMPLEMENTED EXCEPTION` or `PANIC`.
   - Extract ELR, ESR, FAR.
   - Extract reboot reason and reboot code.
   - Extract crash thread fields: tid, name, state, priority, run queue, CPU.
   - Find key logs including `trigger hungry warn`, `hguard-worker thread is abnormal`, `trigger locked`, `HGUARD_DEADLOCK`, and `__dlist_bug`.
   - Extract stack backtrace or kernel call stack.

3. **Snapshot deduplication**
   - If snapshot content exists in the log, keep the first complete transaction from `transaction start` to `transaction end`.
   - Ensure the selected transaction contains the hungry or crash thread.
   - Extract thread tid, name, state, priority, run queue, sctime, `actv_cref`, and `lock_wait`.

4. **Base time**
   - Extract mono time from `transaction start` as baseline `T`.
   - Use `T - sctime` to judge 90s / 120s timeout thresholds.

5. **Hungtask scenario**
   - Apply the six-scenario decision tree:
   - READY realtime task, `rq=7`, timeout > 90s, and high-priority same-affinity runner means scenario 1.
   - READY non-realtime task, `rq=6`, and READY/RUNNING count > 1000 means scenario 2.
   - BLOCK with `lock_wait` means scenario 3 and requires lock-chain tracing.
   - Otherwise classify as scenario 4 unless a lock-owner state refines it to scenario 5 or 6.

6. **ESR deep analysis**
   - Decode ARM64 ESR fields: EC, IL, ISS, DFSC.
   - Recognize EC 0x0, 0x15, 0x1C, 0x20, 0x21, 0x24, 0x25, 0x2F, and 0x3C.
   - Use FAR to judge null pointer and possible DDR bit jump.

7. **Memory corruption analysis**
   - Check ESR 0x0, 0x96-family translation faults, SError, and `__dlist_bug`.
   - For dlist logs, compare expected and actual values; 1-2 bit difference is direct memory jump evidence.

8. **Deadlock chain tracing**
   - If `HGUARD_DEADLOCK` appears, trace `lock_wait` owner to another thread's `actv_cref`.
   - Build `tid -> owner -> tid` chains and detect ABBA cycles.

9. **Final report**
   - Produce exactly the five required sections below.

## Required Report Format

# 1、故障摘要

Include fault type, crash process/thread, reboot reason, fault code, trigger time, and a one- or two-sentence conclusion.

# 2、关键日志

Include 3 to 8 directly relevant crash logs.

| 时间 | 日志内容 |
|---|---|

# 3、时间线

At most 10 rows, sorted by time.

| 时间 | 真实日志 | 简介描述 |
|---|---|---|

# 4、根因分析

Separate facts, inference, and uncertainty. Provide 1 to 3 root-cause candidates. Each candidate includes likelihood, evidence, uncertainty, and validation method.

# 5、建议排查方向

Provide 3 to 6 prioritized engineering actions.

| 优先级 | 目标 | 动作 | 预期结果 |
|---|---|---|---|

## Prohibitions

- Do not output `<think>` or `</textarea>`.
- Do not output JSON as the final answer.
- Do not wrap the whole report in a code block.
- Do not add extra level-1 headings.
- Do not output more than 8 recommendations.
- Do not add explanation before or after the report.
