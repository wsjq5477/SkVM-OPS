---
name: hm-kernel-logs-optimized
description: Analyze Hongmeng kernel log files from a file path. Use this skill when the user provides a Hongmeng/OpenHarmony kernel klog file path and asks for panic, ESR, Hungtask, memory-corruption, deadlock, or root-cause analysis. This optimized skill must run the bundled Python analyzer first, then use Claude only for residual reasoning and the final fixed-format report.
---

# Hongmeng Kernel Log Analysis

Analyze one English Hongmeng kernel log file path. Do not accept pasted log content as the primary input. If the user gives an object-like argument, use its `logPath` value.

## Required Workflow

1. Normalize the input to a single log file path.
2. Run the deterministic analyzer:

```bash
python scripts/analyze_hm_kernel_log.py "<log-path>" --handoff --pretty
```

3. Read the compact handoff JSON output.
4. If the script reports a file error, missing crash, or low-confidence fields, say what is missing and ask for a better log file.
5. Use the script output as the factual base. Do not re-read the full log unless the JSON is incomplete or contradictory.
6. Write the final report using the required five-section format in `references/report-format.md`.

## Reasoning Boundary

Treat these as script facts:

- Panic category/type, crash thread, crash CPU.
- ESR/FAR/ELR and decoded ESR fields.
- Key logs, timeline rows, stack frames.
- Snapshot/base-time/deadlock/hungtask markers when present.

Use Claude reasoning for:

- Root-cause likelihood and uncertainty.
- Whether memory corruption or DDR jump evidence is sufficient.
- How to phrase the engineering actions.
- Any explicit caveat when evidence is weak.

Always separate facts, inference, and uncertainty in section 4.

## References

- Full output contract, only when debugging the analyzer: `references/analysis-contract.md`
- Required report template: `references/report-format.md`
