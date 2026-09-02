"""A build that runs on a worker thread does not read the window's controls.

⚠ REACHABLE WITH TWO ORDINARY GESTURES, and it was made worse by routing
`_build_one` through the one door.

`_build_patiently` runs `_build_one` on a worker thread and then sits in a
`while thread.is_alive(): QApplication.processEvents()` loop behind a
WindowModal progress dialog. Window modality blocks INPUT — the reader cannot
touch a control by hand — but it does NOT block the application's own timers.
Dragging Detail arms `_detail_soon`, a single-shot QTimer, so:

    drag Detail, then open a file slow to read

is enough for the timer to fire inside that loop while the worker is still
building. Driven:

    _settings   8.320  Thread-2 (work)   detail: 24     <- FIVE Qt widgets,
    ENTER       8.320  Thread-2 (work)   profile           off the GUI thread
    _settings   8.724  MainThread        detail: 24
    ENTER       8.724  MainThread        space          <- second build, while
    LEAVE      11.072  Thread-2 (work)   profile           the first runs

    _settings() calls OFF the GUI thread:  1     (0 with the slider untouched)

⚠ AND THE ROUTING WIDENED IT. Before `_build_one` went through the door, a
profile read TWO widgets on that thread and a measurement four. `_settings()`
reads FIVE — including `_detail`, which no file kind depends on and which
`shape_for` discards for every one of them. The one control the race is about
was being read off the GUI thread on every open of every file, for nothing.

After the fix: **0 calls off the GUI thread.**

WHAT THIS TEST DOES NOT CLAIM. Two builds still overlap — that is what
`processEvents()` is for, and the progress dialog exists to keep the window
answering. What is closed is the widget reading and the stale snapshot: the
shape is now built under what the controls held when the reader pressed Open,
not under whatever they held when the worker got round to them.
"""
import ast
import inspect
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

#: Reading any of these is reading a Qt widget.
WIDGETS = ("_white", "_mode", "_relative", "_detail", "_space")


def _worker_body():
    """The `work()` closure inside `_build_patiently`, as a syntax tree."""
    import gamut_app
    src = inspect.getsource(gamut_app.GamutApp._build_patiently)
    tree = ast.parse(src.strip())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "work":
            return node
    raise AssertionError(
        "`work()` is gone from `_build_patiently` — either the thread was "
        "removed or this test has stopped watching it")


def test_the_worker_reads_no_control_and_takes_no_snapshot():
    """⚠ THE RULE, NOT THE ONE READ THAT WAS WRONG."""
    node = _worker_body()
    guilty = []
    for inner in ast.walk(node):
        if isinstance(inner, ast.Attribute) and isinstance(inner.value, ast.Name):
            if inner.value.id == "self" and inner.attr in WIDGETS:
                guilty.append(f"self.{inner.attr}")
            if inner.value.id == "self" and inner.attr in ("_settings",
                                                           "_build_space"):
                guilty.append(f"self.{inner.attr}()")
    assert not guilty, (
        "the worker thread reads the window's controls: "
        f"{sorted(set(guilty))} — read them on the GUI thread before "
        "`thread.start()` and hand the snapshot over")


def test_the_snapshot_is_taken_in_the_method_and_not_in_the_worker():
    """⚠ THIS TEST WAS WRITTEN WRONG FIRST, AND ITS OWN CONTROL SAID SO.

    It asked whether `self._settings()` appears at a LINE NUMBER before
    `thread.start()`. It does — and so does a snapshot taken INSIDE `work()`,
    because the closure is defined above the `start()` call. The control that
    put the read back inside the worker left this assertion passing while the
    fault was fully present; only the sibling test above caught it. Line
    order cannot tell "before the thread starts" from "inside the thread".

    So the question is asked about the SYNTAX TREE instead: the snapshot must
    be a statement of `_build_patiently` itself, not of any function nested
    inside it.
    """
    import gamut_app
    src = inspect.getsource(gamut_app.GamutApp._build_patiently)
    tree = ast.parse(src.strip())
    outer = tree.body[0]
    assert isinstance(outer, ast.FunctionDef), outer

    def takes_a_snapshot(node):
        return any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "_settings"
            and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"
            for n in ast.walk(node))

    at_top = [st for st in outer.body if takes_a_snapshot(st)]
    assert at_top, (
        "`_build_patiently` never snapshots the controls in its own body, so "
        "the worker builds under whatever they hold when it gets round to "
        "reading them — which is not the moment the reader pressed Open")

    # and it is not merely the `work()` definition being counted
    assert not all(isinstance(st, ast.FunctionDef) for st in at_top), (
        "the only snapshot is inside a nested function — that is the worker, "
        "and reading the controls there is the fault this closes")


def test_build_one_accepts_a_snapshot_from_its_caller():
    """The door into the fix: without this parameter there is nowhere to put
    a snapshot taken somewhere safer."""
    import gamut_app
    params = inspect.signature(gamut_app.GamutApp._build_one).parameters
    assert "settings" in params, (
        "`_build_one` cannot be handed a snapshot, so every caller on a "
        "worker thread has to read the widgets itself")
    assert params["settings"].default is None, (
        "the snapshot must be optional, or every main-thread caller has to "
        "make one it does not need")
