"""D1-TEST-5: svdb stands alone -- importing it pulls in neither Sphinx nor pyslang."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2] / "src"


def test_svdb_imports_neither_sphinx_nor_pyslang():
    code = (
        "import sys\n"
        "import sphinx_systemverilog.svdb.cli, sphinx_systemverilog.svdb.database\n"
        "bad = sorted(m for m in sys.modules if m.split('.')[0] in ('sphinx', 'pyslang'))\n"
        "print(','.join(bad))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={"PYTHONPATH": str(SRC)}, check=True)
    assert out.stdout.strip() == ""
