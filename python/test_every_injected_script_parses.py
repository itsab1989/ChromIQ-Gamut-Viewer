"""Every script this application injects has to be JavaScript that parses.

A SYNTAX ERROR IN AN INJECTED SCRIPT IS SILENT. The page still draws: the
browser throws on that one <script> and carries on, so the picture looks
right and only the thing the script was for is missing. That is the same
shape as every fault that cost a day this week — a measurement, or a fix,
that cannot see its own subject.

There is no JavaScript engine in the test venv, so this uses `node --check`
when a node is on the path and skips when there is not one. A skip says so;
it does not pass quietly.
"""
import pathlib
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

_NODE = shutil.which("node")


def _scripts():
    import ti3gamut
    out = {}
    for name in dir(ti3gamut):
        if not (name.endswith("_JS") or name.endswith("_SCRIPT")):
            continue
        value = getattr(ti3gamut, name)
        if isinstance(value, str) and value.strip():
            out[name] = value
    return out


def test_there_are_scripts_to_check():
    """A LIST THAT QUIETLY CAME BACK EMPTY would make every check below pass."""
    found = _scripts()
    assert len(found) >= 6, (
        f"only {sorted(found)} — this test can no longer see what the pages "
        f"carry, and would pass on anything")
    assert "_DEPTH_JS" in found and "_ORDER_JS" in found


@pytest.mark.skipif(_NODE is None, reason="no node on the path to parse with")
@pytest.mark.parametrize("name", sorted(_scripts()) if _NODE else ["none"])
def test_each_injected_script_parses(name, tmp_path):
    body = _scripts()[name]
    where = tmp_path / f"{name}.js"
    where.write_text(body)
    done = subprocess.run([_NODE, "--check", str(where)],
                          capture_output=True, text=True)
    assert done.returncode == 0, (
        f"{name} is not JavaScript that parses, and a page carrying it would "
        f"draw perfectly while doing none of what it is for:\n"
        f"{done.stderr.strip()[:600]}")


@pytest.mark.skipif(_NODE is None, reason="no node on the path to parse with")
def test_a_broken_script_would_be_caught(tmp_path):
    """AND THE CHECK ITSELF WORKS. `node --check` accepts a surprising amount;
    this proves it rejects the kind of damage an edit here would do."""
    where = tmp_path / "broken.js"
    where.write_text("(function () { var a = ; })();")
    done = subprocess.run([_NODE, "--check", str(where)],
                          capture_output=True, text=True)
    assert done.returncode != 0, (
        "node --check accepted a syntax error, so the checks above prove "
        "nothing")
