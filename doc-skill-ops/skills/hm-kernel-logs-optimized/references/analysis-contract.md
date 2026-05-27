# Analysis Contract

The analyzer emits a JSON object with these top-level keys:

- `input`: log path, line count, byte count, crash line numbers.
- `log_info`: crash facts, panic type, registers, reboot codes, key logs, call stack.
- `snapshot_info`: snapshot/thread data when present.
- `base_time_info`: baseline mono time when present.
- `hungtask_analysis`: deterministic Hungtask markers and scenario hints.
- `esr_analysis`: decoded ESR fields and fault classification.
- `memory_corruption`: deterministic memory-corruption indicators.
- `deadlock_analysis`: deterministic deadlock indicators and chain data.
- `report_data`: report-ready facts, timeline, root-cause candidates, and recommendations.
- `metrics`: elapsed time and size metrics.

Use `report_data` for the final report whenever possible. If a value is missing, say `N/A` or explain the uncertainty in section 4.

Do not treat script-generated `root_cause_candidates` as final truth. They are candidates for Claude to assess.
