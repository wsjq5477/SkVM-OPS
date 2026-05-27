# HM Kernel Log Skill Evaluation

## Result Summary

- Panic type: `KERNEL_UNIMPLEMENTED_EXCEPTION` (KERNEL)
- Crash thread: `ufs_eh_worker` on CPU `1`
- Registers: ESR `f2000800`, FAR `0000000000000000`, ELR `00000005f46acc18`
- ESR fault type: `BRK instruction`; likely cause: Intentional breakpoint/BUG_ON style exception.
- Memory corruption detected by deterministic script: `False` (none)
- Hungtask detected by deterministic script: `False`
- Deadlock detected by deterministic script: `False`

## Speed

- Optimized analyzer median runtime: `3.182 ms` over 15 local runs.
- Optimized analyzer min/max runtime: `2.837 / 5.944 ms`.
- Baseline text-only skill has no local deterministic runtime; it requires a live Claude run over the full workflow and log.

## Token Footprint Estimate

- Baseline estimated input tokens: `3411`.
- Optimized estimated input tokens: `1805`.
- Estimated reduction: `47.1%`.

Token counts are local estimates using `chars / 4`; they are for apples-to-apples comparison, not provider billing.

## Quality Notes

- The optimized script extracts stable facts before Claude writes the report.
- Claude still owns root-cause wording, uncertainty, and engineering recommendations.
- For this sample, deterministic evidence points to a BRK-style exception in `ufs_eh_worker`, with stack frames in the UFS reset/error-handler path.
