import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "doc-skill-ops" / "skills" / "hm-kernel-logs-optimized" / "scripts" / "analyze_hm_kernel_log.py"
LOG = ROOT / "doc-skill-ops" / "test_log.txt"


def load_analyzer():
    spec = importlib.util.spec_from_file_location("analyze_hm_kernel_log", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AnalyzeHmKernelLogTests(unittest.TestCase):
    def test_extracts_core_panic_facts_from_sample_log(self):
        analyzer = load_analyzer()

        result = analyzer.analyze_log_file(LOG)

        self.assertTrue(result["log_info"]["has_crash"])
        self.assertEqual(result["log_info"]["panic_category"], "KERNEL")
        self.assertEqual(result["log_info"]["panic_type"], "KERNEL_UNIMPLEMENTED_EXCEPTION")
        self.assertEqual(result["log_info"]["crash_thread"], "ufs_eh_worker")
        self.assertEqual(result["log_info"]["crash_cpu"], "1")
        self.assertEqual(result["log_info"]["registers"]["esr"], "f2000800")
        self.assertEqual(result["log_info"]["registers"]["far"], "0000000000000000")
        self.assertEqual(result["log_info"]["registers"]["elr"], "00000005f46acc18")
        self.assertGreaterEqual(len(result["log_info"]["call_stack"]), 5)
        self.assertGreaterEqual(len(result["report_data"]["key_logs"]), 3)
        self.assertGreaterEqual(len(result["report_data"]["timeline"]), 3)

    def test_classifies_esr_and_memory_corruption_candidate(self):
        analyzer = load_analyzer()

        result = analyzer.analyze_log_file(LOG)

        self.assertEqual(result["esr_analysis"]["esr_ec"], "0x3c")
        self.assertEqual(result["esr_analysis"]["fault_type"], "BRK instruction")
        self.assertFalse(result["esr_analysis"]["is_null_pointer"])
        self.assertFalse(result["memory_corruption"]["has_memory_corruption"])
        self.assertEqual(result["memory_corruption"]["corruption_type"], "none")

    def test_cli_emits_json_with_report_sections_and_metrics(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), str(LOG), "--pretty"],
            check=True,
            capture_output=True,
            text=True,
        )

        result = json.loads(completed.stdout)

        self.assertIn("metrics", result)
        self.assertGreater(result["metrics"]["elapsed_ms"], 0)
        self.assertEqual(
            result["report_data"]["required_sections"],
            ["故障摘要", "关键日志", "时间线", "根因分析", "建议排查方向"],
        )
        self.assertIn("ufs_eh_worker", result["report_data"]["summary"]["crash_thread"])


if __name__ == "__main__":
    unittest.main()
