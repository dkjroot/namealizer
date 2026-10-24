"""Quiet local checks: show diagnostics only when something fails."""

import io
import sys
import unittest

if __name__ == "__main__":
    output = io.StringIO()
    suite = unittest.defaultTestLoader.discover("tests")
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    if result.wasSuccessful():
        print(f"PASS: {result.testsRun} tests")
    else:
        print(output.getvalue())
    sys.exit(0 if result.wasSuccessful() else 1)
