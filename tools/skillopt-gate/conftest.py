"""Pytest conftest: make ``skillopt_gate`` importable from any cwd.

Pytest imports this module before collecting tests, so inserting this
directory (the package root) onto ``sys.path`` lets
``tests/*.py`` do ``import skillopt_gate`` even when pytest is
invoked from the repo root (``pytest tools/skillopt-gate/tests``).
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
