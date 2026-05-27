import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "doc-skill-ops"
BASELINE = WORK / "skills" / "hm-kernel-logs-baseline" / "SKILL.md"
OPT_DIR = WORK / "skills" / "hm-kernel-logs-optimized"
OPT_SKILL = OPT_DIR / "SKILL.md"
REPORT_FORMAT = OPT_DIR / "references" / "report-format.md"
ANALYZER = OPT_DIR / "scripts" / "analyze_hm_kernel_log.py"


class SkillArtifactTests(unittest.TestCase):
    def test_baseline_skill_is_text_conversion_of_workflow(self):
        text = BASELINE.read_text(encoding="utf-8")

        for phase in [
            "Read log",
            "Parse log",
            "Snapshot deduplication",
            "Base time",
            "Hungtask scenario",
            "ESR deep analysis",
            "Memory corruption analysis",
            "Deadlock chain tracing",
            "Final report",
        ]:
            self.assertIn(phase, text)

    def test_optimized_skill_uses_standard_claude_skill_structure(self):
        self.assertTrue(OPT_SKILL.exists())
        self.assertTrue((OPT_DIR / "scripts").is_dir())
        self.assertTrue((OPT_DIR / "references").is_dir())
        self.assertTrue(ANALYZER.exists())
        skill = OPT_SKILL.read_text(encoding="utf-8")
        self.assertIn("python scripts/analyze_hm_kernel_log.py", skill)
        self.assertIn("--handoff", skill)

    def test_report_format_has_exact_required_headings(self):
        text = REPORT_FORMAT.read_text(encoding="utf-8")

        headings = [line for line in text.splitlines() if line.startswith("# ")]

        self.assertEqual(
            headings,
            ["# Report Format", "# 1、故障摘要", "# 2、关键日志", "# 3、时间线", "# 4、根因分析", "# 5、建议排查方向"],
        )


if __name__ == "__main__":
    unittest.main()
