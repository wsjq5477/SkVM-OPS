---
name: hm-kernel-logs-optimized
description: Analyze Hongmeng kernel log files from a path. Run scripts/analyze_text.py first, then write the fixed five-section report.
---

# HM Kernel Logs Optimized

Run:

```bash
python scripts/analyze_text.py "<log-path>" --handoff --pretty
```

Use the JSON facts to write the five-section report in references/report-format.md.
