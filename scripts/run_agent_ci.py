"""运行与 GitHub Actions 相同的 Agent 测试及 20 条工作流验收。"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=PROJECT_ROOT / "evaluation/week4/ci-runs/local")
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                   "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                   "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    commands = [
        ("agent_tests", [sys.executable, "-m", "pytest", "tests", "-q",
                         "-p", "no:cacheprovider", "--ignore=tests/test_api.py",
                         "--ignore=tests/test_llm.py",
                         f"--junitxml={output / 'pytest.xml'}"]),
        ("workflow_acceptance", [sys.executable, "scripts/run_agent_acceptance.py",
                                 "--output-dir", str(output / "acceptance")]),
    ]
    results = {}
    for name, command in commands:
        print(f"\n运行 {name}", flush=True)
        result = subprocess.run(command, cwd=PROJECT_ROOT, env=environment)
        results[name] = result.returncode
    (output / "ci_summary.json").write_text(json.dumps({
        "scope": "Agent tests and 20 workflow cases; excludes legacy RAG API/LLM tests",
        "exit_codes": results,
        "passed": all(code == 0 for code in results.values()),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("报告目录：", output, flush=True)
    return 0 if all(code == 0 for code in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
