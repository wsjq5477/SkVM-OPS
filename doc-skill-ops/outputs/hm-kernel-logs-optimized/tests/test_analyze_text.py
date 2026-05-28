import json, subprocess, sys, unittest
from pathlib import Path

OUT=Path(__file__).resolve().parents[1]
SCRIPT=OUT/'scripts'/'analyze_text.py'
SAMPLE=OUT/'samples'/'test_log.txt'

class GeneratedAnalyzerTest(unittest.TestCase):
    def test_sample_log(self):
        out=subprocess.check_output([sys.executable, str(SCRIPT), str(SAMPLE), '--handoff'], text=True)
        data=json.loads(out)
        self.assertEqual(data['summary']['crash_thread'], 'ufs_eh_worker')
        self.assertEqual(data['registers']['esr'], 'f2000800')
        self.assertEqual(data['esr']['fault_type'], 'BRK instruction')
        self.assertGreaterEqual(len(data['key_logs']), 3)

if __name__=='__main__': unittest.main()
