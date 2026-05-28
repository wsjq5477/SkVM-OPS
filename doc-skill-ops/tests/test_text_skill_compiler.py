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
from text_skill_compiler import (  # noqa: E402
    OpenAICompatibleClient,
    build_client,
    derive_contract_from_graph,
    validate_flow_graph,
)


class TextSkillCompilerTests(unittest.TestCase):
    def test_validate_flow_graph_accepts_reachable_execution_flow(self):
        graph = {
            "graph_id": "sample-log-analysis",
            "entry_nodes": ["load_input"],
            "exit_nodes": ["write_report"],
            "nodes": [
                {
                    "id": "load_input",
                    "type": "load_input",
                    "description": "Read the input log file.",
                    "inputs": ["file_path"],
                    "outputs": ["log_text"],
                    "owner": "script",
                    "determinism": "high",
                },
                {
                    "id": "extract_fault",
                    "type": "extract",
                    "description": "Extract fault code and crash thread.",
                    "inputs": ["log_text"],
                    "outputs": ["fault_code", "crash_thread"],
                    "owner": "script_candidate",
                    "determinism": "high",
                },
                {
                    "id": "write_report",
                    "type": "report",
                    "description": "Write the final incident report.",
                    "inputs": ["fault_code", "crash_thread"],
                    "outputs": ["final_report"],
                    "owner": "llm_required",
                    "determinism": "low",
                },
            ],
            "edges": [
                {"from": "load_input", "to": "extract_fault", "kind": "data_dependency"},
                {"from": "extract_fault", "to": "write_report", "kind": "data_dependency"},
            ],
        }

        validation = validate_flow_graph(graph)

        self.assertEqual(validation["status"], "passed")
        self.assertEqual(validation["node_count"], 3)
        self.assertEqual(validation["edge_count"], 2)
        self.assertEqual(validation["errors"], [])

    def test_validate_flow_graph_rejects_unknown_edge_endpoint(self):
        graph = {
            "graph_id": "bad-log-analysis",
            "entry_nodes": ["load_input"],
            "exit_nodes": ["write_report"],
            "nodes": [
                {
                    "id": "load_input",
                    "type": "load_input",
                    "description": "Read the input log file.",
                    "inputs": ["file_path"],
                    "outputs": ["log_text"],
                    "owner": "script",
                    "determinism": "high",
                },
                {
                    "id": "write_report",
                    "type": "report",
                    "description": "Write the final incident report.",
                    "inputs": ["facts"],
                    "outputs": ["final_report"],
                    "owner": "llm_required",
                    "determinism": "low",
                },
            ],
            "edges": [
                {"from": "load_input", "to": "missing_extract", "kind": "data_dependency"},
            ],
        }

        validation = validate_flow_graph(graph)

        self.assertEqual(validation["status"], "failed")
        self.assertTrue(any("missing_extract" in error for error in validation["errors"]))

    def test_derive_contract_from_graph_returns_v1_compatible_contract(self):
        graph = {
            "graph_id": "sample-log-analysis",
            "entry_nodes": ["load_input"],
            "exit_nodes": ["write_report"],
            "nodes": [
                {
                    "id": "load_input",
                    "type": "load_input",
                    "description": "Read the user-provided log file path.",
                    "inputs": ["file_path"],
                    "outputs": ["log_text"],
                    "owner": "script",
                    "determinism": "high",
                },
                {
                    "id": "extract_fault",
                    "type": "extract",
                    "description": "Extract panic type, crash thread, and registers.",
                    "inputs": ["log_text"],
                    "outputs": ["panic_type", "crash_thread", "registers"],
                    "owner": "script_candidate",
                    "determinism": "high",
                },
                {
                    "id": "infer_root_cause",
                    "type": "reason",
                    "description": "Infer likely root cause and uncertainty.",
                    "inputs": ["panic_type", "crash_thread", "registers"],
                    "outputs": ["root_cause_hypothesis"],
                    "owner": "llm_required",
                    "determinism": "low",
                },
                {
                    "id": "write_report",
                    "type": "report",
                    "description": "Write incident summary, timeline, root cause, and recommendations.",
                    "inputs": ["root_cause_hypothesis"],
                    "outputs": ["final_report"],
                    "owner": "llm_required",
                    "determinism": "low",
                },
            ],
            "edges": [
                {"from": "load_input", "to": "extract_fault", "kind": "data_dependency"},
                {"from": "extract_fault", "to": "infer_root_cause", "kind": "data_dependency"},
                {"from": "infer_root_cause", "to": "write_report", "kind": "data_dependency"},
            ],
        }

        contract = derive_contract_from_graph(graph)

        self.assertEqual(contract["input_mode"], "file_path")
        for key in [
            "report_sections",
            "entities",
            "deterministic_operations",
            "residual_reasoning",
            "failure_modes",
        ]:
            self.assertIn(key, contract)
        self.assertIn("panic_type", contract["entities"])
        self.assertIn("extract_fault", contract["deterministic_operations"])
        self.assertIn("infer_root_cause", contract["residual_reasoning"])

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
            self.assertTrue((out / "compiled" / "flow_graph.raw.json").exists())
            self.assertTrue((out / "compiled" / "flow_graph.json").exists())
            self.assertTrue((out / "compiled" / "graph_validation.json").exists())
            self.assertTrue((out / "compiled" / "contract.json").exists())
            self.assertTrue((out / "compiled" / "validation.json").exists())
            self.assertTrue((out / "evaluation" / "baseline-vs-optimized.md").exists())
            graph_validation = json.loads((out / "compiled" / "graph_validation.json").read_text(encoding="utf-8"))
            self.assertEqual(graph_validation["status"], "passed")
            evaluation = json.loads((out / "evaluation" / "baseline-vs-optimized.json").read_text(encoding="utf-8"))
            self.assertEqual(evaluation["result_summary"]["crash_thread"], "ufs_eh_worker")
            self.assertGreater(evaluation["comparison"]["estimated_token_reduction_percent"], 0)

    def test_validation_failure_uses_repair_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            mock = Path(tmp) / "mock"
            shutil.copytree(EXAMPLE / "mock_llm", mock)
            generation = json.loads((mock / "04_generate_artifacts.json").read_text(encoding="utf-8"))
            generation["files"]["scripts/analyze_text.py"] = "raise SystemExit(7)\n"
            (mock / "04_generate_artifacts.json").write_text(json.dumps(generation), encoding="utf-8")
            repair = json.loads((EXAMPLE / "mock_llm" / "04_generate_artifacts.json").read_text(encoding="utf-8"))
            (mock / "05_repair.json").write_text(json.dumps(repair), encoding="utf-8")
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
