import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPILER = ROOT / "doc-skill-ops" / "compiler" / "text_skill_compiler.py"
EXAMPLE = ROOT / "doc-skill-ops" / "examples" / "hm-kernel-logs"

sys.path.insert(0, str(ROOT / "doc-skill-ops" / "compiler"))
from text_skill_compiler import OpenAICompatibleClient, build_client  # noqa: E402


class TextSkillCompilerTests(unittest.TestCase):
    def test_local_provider_uses_openai_compatible_base_url(self):
        client = build_client(Namespace(
            mock_llm=None,
            provider="local",
            model="qwen-local",
            base_url="http://127.0.0.1:8000/v1",
            api_key=None,
        ))

        self.assertIsInstance(client, OpenAICompatibleClient)
        self.assertEqual(client.base_url, "http://127.0.0.1:8000/v1")
        self.assertEqual(client.model, "qwen-local")
        self.assertEqual(client.api_key, "local")

    def test_local_provider_requires_base_url(self):
        with self.assertRaises(SystemExit) as ctx:
            build_client(Namespace(
                mock_llm=None,
                provider="local",
                model="qwen-local",
                base_url=None,
                api_key=None,
            ))

        self.assertIn("--base-url is required", str(ctx.exception))

    def test_mock_llm_compile_creates_optimized_skill_and_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "hm-kernel-logs-optimized"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(COMPILER),
                    "--skill",
                    str(EXAMPLE / "workflow.js"),
                    "--sample",
                    str(EXAMPLE / "test_log.txt"),
                    "--out",
                    str(out),
                    "--name",
                    "hm-kernel-logs-optimized",
                    "--mock-llm",
                    str(EXAMPLE / "mock_llm"),
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            self.assertIn("compiled", completed.stdout)
            self.assertTrue((out / "SKILL.md").exists())
            self.assertTrue((out / "scripts" / "analyze_text.py").exists())
            self.assertTrue((out / "references" / "report-format.md").exists())
            self.assertTrue((out / "compiled" / "contract.json").exists())
            self.assertTrue((out / "compiled" / "validation.json").exists())
            self.assertTrue((out / "evaluation" / "baseline-vs-optimized.md").exists())
            evaluation = json.loads((out / "evaluation" / "baseline-vs-optimized.json").read_text(encoding="utf-8"))
            self.assertEqual(evaluation["result_summary"]["crash_thread"], "ufs_eh_worker")
            self.assertGreater(evaluation["comparison"]["estimated_token_reduction_percent"], 0)

    def test_validation_failure_uses_repair_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            mock = Path(tmp) / "mock"
            shutil.copytree(EXAMPLE / "mock_llm", mock)
            generation = json.loads((mock / "03_generate_artifacts.json").read_text(encoding="utf-8"))
            generation["files"]["scripts/analyze_text.py"] = "raise SystemExit(7)\n"
            (mock / "03_generate_artifacts.json").write_text(json.dumps(generation), encoding="utf-8")
            repair = json.loads((EXAMPLE / "mock_llm" / "03_generate_artifacts.json").read_text(encoding="utf-8"))
            (mock / "04_repair.json").write_text(json.dumps(repair), encoding="utf-8")
            out = Path(tmp) / "repaired"

            subprocess.run(
                [
                    sys.executable,
                    str(COMPILER),
                    "--skill",
                    str(EXAMPLE / "workflow.js"),
                    "--sample",
                    str(EXAMPLE / "test_log.txt"),
                    "--out",
                    str(out),
                    "--name",
                    "hm-kernel-logs-optimized",
                    "--mock-llm",
                    str(mock),
                    "--max-repair-rounds",
                    "1",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            validation = json.loads((out / "compiled" / "validation.json").read_text(encoding="utf-8"))
            self.assertEqual(validation["status"], "passed")
            self.assertEqual(validation["repair_rounds"], 1)


if __name__ == "__main__":
    unittest.main()
