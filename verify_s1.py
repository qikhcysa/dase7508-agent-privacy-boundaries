"""Run repository checks and archive a fresh S1 component demonstration."""

from datetime import datetime
import json
from pathlib import Path
import platform
import sys
import unittest
from uuid import uuid4

from agent_privacy.s1_demo import run_demo
from contracts.validate import ROOT, load_json, validate


def main():
    root = Path(__file__).resolve().parent
    directory = root / "artifacts" / ("s1review" + datetime.now().strftime("%Y%m%d%H%M%S") + uuid4().hex[:6])
    suite = unittest.defaultTestLoader.discover(str(root / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    for example in sorted((ROOT / "examples").glob("*.json")):
        validate("bundle", load_json(example))
    report = run_demo(directory)
    report["tests"] = {"count": result.testsRun, "failures": len(result.failures), "errors": len(result.errors)}
    report["python"] = platform.python_version()
    (directory / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
