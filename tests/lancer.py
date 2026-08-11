#!/usr/bin/env python3
"""Lance tout : les propriétés, leur mise à l'épreuve, et l'interface."""
import os
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
SUITES = ["test_traceur.py", "verifier_les_tests.py", "test_pupitre.py"]

code = 0
for suite in SUITES:
    print(f"\n=== {suite} " + "=" * (56 - len(suite)))
    r = subprocess.run([sys.executable, os.path.join(ICI, suite)],
                       env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    code |= r.returncode
print("\n" + ("TOUT PASSE." if code == 0 else "DES TESTS ONT ÉCHOUÉ."))
sys.exit(code)
