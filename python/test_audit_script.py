"""The release audit's own tables, checked against the real controls.

WHY THIS EXISTS. ``scripts/audit.py`` gates a release: it presses every
control and fails the run if one does nothing. Three of its tables name
controls by string —

    WINDOW_ACTIONS   controls that are ALLOWED to change nothing, with a
                     reason for each
    NEEDS            controls that must have a parent switched on first
    OPPOSITES        page controls that step, and what steps back

— and a name in any of them is a claim about a control that exists somewhere
else. Rename that control and nothing breaks, nothing raises, and the audit
goes on passing: an excused control that no longer exists is simply never
matched, so a real fault in its replacement is reported as a genuine finding
nobody expected, or — worse the other way — a control that quietly inherits
an excused name is never really tested again.

That is the exact failure this whole audit was written to catch, so it should
not be possible to commit it in the audit itself.

WHY IT READS SOURCE RATHER THAN BUILDING A WINDOW. Constructing ``GamutApp``
inside pytest brings up a QWebEngineView and aborts the run — see the note at
the top of ``test_chart_panel.py``. ``_persisted()`` is a plain table of
literals, so it can be read without running it, and that is what happens here.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
AUDIT = ROOT / "scripts" / "audit.py"
APP = ROOT / "python" / "gamut_app.py"
PAGES = ROOT / "python" / "ti3gamut.py"


@pytest.fixture(scope="module")
def audit():
    """The audit module, imported without Qt — its Qt imports are all local."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_audit_under_test", AUDIT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def window_keys():
    """Every key ``_persisted()`` and ``_shape_controls()`` hand out.

    Read out of the source as literals. If either table stops being a literal
    table this fixture returns too few names and the tests below fail loudly,
    which is the right way round: the check going quiet is the thing that
    must not happen.
    """
    text = APP.read_text(encoding="utf-8")
    body = text[text.index("def _persisted"):]
    body = body[:body.index("\n    def ", 10)]
    keys = set(re.findall(r'\(\s*"([a-z_]+)",\s*self\.(?:_[a-z_]+|None)',
                          body))
    shape = text[text.index("def _shape_controls"):]
    shape = shape[:shape.index("\n    def ", 10)]
    keys |= set(re.findall(r'"([a-z_]+)":\s*\(', shape))
    assert len(keys) > 30, f"only found {len(keys)} settings — has the table "\
                           f"stopped being a table of literals?"
    return keys


@pytest.fixture(scope="module")
def page_controls():
    """Every ``data-cq`` name the page writer can put on a button."""
    text = PAGES.read_text(encoding="utf-8")
    # TWO WAYS A BUTTON IS MADE, and missing the second one made this check
    # report a real button ("notes") as a name nobody has. `button()` writes
    # the element; `row()` writes a labelled line with a `button()` in it.
    names = set(re.findall(r'\brow\("([a-z-]+)"', text))
    names |= set(re.findall(r'\bbutton\("([a-z-]+)"', text))
    # Built by joining a stem to a value, so the literal is only the stem.
    names |= {f"look-{v}" for v in ("above", "front", "side", "angle")}
    names |= {f"shape-{w}-" for w in ("fainter", "stronger", "wires", "grey")}
    assert len(names) > 20, f"only found {len(names)} page buttons"
    return names


@pytest.fixture(scope="module")
def page_readouts():
    """Every ``data-cq`` name the page writes a value into."""
    text = PAGES.read_text(encoding="utf-8")
    return set(re.findall(r'say\("([a-z-]+)"', text))


def test_every_excused_window_control_exists(audit, window_keys):
    """A reason given for a control nobody has is a reason for nothing."""
    unknown = sorted(set(audit.WINDOW_ACTIONS) - window_keys)
    assert not unknown, (
        f"WINDOW_ACTIONS excuses {unknown}, which the window no longer has. "
        f"An excuse that matches nothing means the control that replaced it "
        f"is being judged by the ordinary rule, or not at all.")


def test_every_parent_switch_exists(audit, window_keys):
    """Both halves of NEEDS: the control, and the thing it needs."""
    unknown = sorted(set(audit.NEEDS) - window_keys)
    assert not unknown, f"NEEDS names {unknown}, which the window has not"
    for child, parent in sorted(audit.NEEDS.items()):
        if parent.startswith("_"):
            # A widget rather than a stored setting -- named as an attribute,
            # so check the window really has one.
            assert f"self.{parent} " in APP.read_text(encoding="utf-8") or \
                   f"self.{parent}=" in APP.read_text(encoding="utf-8") or \
                   f"self.{parent}." in APP.read_text(encoding="utf-8"), \
                   f"{child} is said to need {parent}, which does not exist"
        else:
            assert parent in window_keys, (
                f"{child} is said to need {parent}, which is not a setting")


def test_a_control_is_not_both_excused_and_given_a_parent(audit):
    """The two say opposite things, and the run would apply only the excuse.

    WINDOW_ACTIONS says "this is not expected to move the picture"; NEEDS
    says "this moves the picture once its parent is on". A control in both
    gets its parent switched on and is then excused whatever it does, which
    is a test that runs and cannot fail.
    """
    both = sorted(set(audit.WINDOW_ACTIONS) & set(audit.NEEDS))
    assert not both, f"{both} are both excused and given a parent"


def test_stepping_controls_step_back(audit):
    """OPPOSITES has to be symmetric or the audit cannot undo what it did."""
    for one, other in sorted(audit.OPPOSITES.items()):
        assert other in audit.OPPOSITES, f"{one} steps to {other}, which "\
                                         f"steps back to nothing"
        assert audit.OPPOSITES[other] == one, (
            f"{one} → {other} → {audit.OPPOSITES[other]}: pressing the "
            f"opposite would not put the picture back")


def test_the_per_shape_pairs_undo_each_other(audit):
    """The − and + beside a shape's strength, for any number of shapes."""
    assert audit.opposite_of("shape-fainter-2") == "shape-stronger-2"
    assert audit.opposite_of("shape-stronger-0") == "shape-fainter-0"
    # And a switch is not mistaken for one half of a pair.
    assert audit.opposite_of("shape-wires-1") is None
    assert audit.opposite_of("shape-grey-1") is None


def test_every_excused_page_control_exists(audit, page_controls):
    """Same claim, on the page side.

    ACTIONS is where somebody records that a button is not supposed to change
    the picture. Left naming a button that no longer exists, it excuses
    nothing while looking as though it excuses something.
    """
    unknown = sorted(
        name for name in audit.ACTIONS
        if name not in page_controls
        and not any(p.startswith(name) for p in page_controls))
    assert not unknown, (
        f"ACTIONS excuses {unknown}, which no page button is called. Either "
        f"the button was renamed, or the excuse was never true.")


def test_every_readout_is_one_the_page_actually_writes(audit, page_readouts):
    """A control judged by a number needs the number to be kept up to date.

    `zoomed` looks exactly like the others — it is a `data-cq` span sitting
    beside the zoom buttons — and nothing ever writes to it; it is a static
    label reading "zoom". Judging the zoom buttons by it would have passed
    them for ever, whatever they did.
    """
    unwritten = sorted(set(audit.READOUTS.values()) - page_readouts)
    assert not unwritten, (
        f"{unwritten} are never written to, so a control judged by one "
        f"would report 'does nothing' whatever it did")


def test_a_control_with_a_readout_can_be_put_back(audit):
    """The readout check presses the opposite, so there has to be one."""
    for what in sorted(audit.READOUTS):
        assert audit.opposite_of(what) is not None, (
            f"{what} is judged by its readout, and the check presses the "
            f"opposite to see the number come back — but it has none")


def test_a_control_is_not_both_excused_and_read(audit):
    """An excuse wins over a real check, which is the wrong way round."""
    both = sorted(set(audit.ACTIONS) & set(audit.READOUTS))
    assert not both, f"{both} are excused AND have a number to check"


def test_the_view_presets_are_real_buttons(audit, page_controls):
    unknown = sorted(set(audit.PRESETS) - page_controls)
    assert not unknown, f"PRESETS names {unknown}, which are not buttons"


def test_a_finding_is_not_sold_as_a_verdict(audit):
    """What this audit claims about itself has to stay modest.

    It was shipped once with a finding it could not explain, and the first
    fix was to write down what it gets wrong rather than keep quiet. The
    cause was found later — a camera put back on screen but not in the
    layout — so the paragraph describing that limitation is gone, correctly,
    because the limitation is gone.

    What must NOT go with it is the claim's modesty. This presses controls
    and compares pictures; it cannot tell "wrong" from "different", and a
    file that starts promising verdicts is one somebody will believe over
    their own eyes.
    """
    doc = audit.__doc__ or ""
    assert "a reason to go and look rather than a verdict" in doc, (
        "the audit must keep saying that a finding is a reason to look")
    # And it must go on teaching the traps it learned, whatever they are now.
    assert "learned by this" in doc or "GETS WRONG" in doc or \
           "used to get wrong" in doc.lower(), (
        "the audit must keep a record of how it has been wrong before")


def test_the_camera_is_put_back_where_a_redraw_will_keep_it(audit):
    """setCamera moves the screen; the layout keeps the old angle.

    That was the whole of a finding this carried for several releases:
    turning the shape leaves it at a new angle on purpose, the restore
    between controls looked like it worked, and the first relayout inside the
    next control's test re-applied the stored angle. "spin_on" and "grid_on"
    reported the identical 314,313 pixels — one difference measured twice.
    """
    source = AUDIT.read_text(encoding="utf-8")
    assert '"scene.camera.eye"' in source, (
        "the camera must be put back through relayout, which sets the stored "
        "one as well as the drawn one")
    assert "s._scene.setCamera" not in source, (
        "setCamera alone leaves the layout holding the old angle")


def test_the_listing_and_the_run_choose_the_same_controls(audit):
    """One function decides, so `--list` cannot promise what a run skips.

    `--list` printed the twenty-two ⓘ explanation folds, which the run has
    always skipped on purpose — a third of the listing naming work that was
    never going to happen. Both now go through ``window_controls``.
    """
    source = AUDIT.read_text(encoding="utf-8")
    assert source.count("window_controls(w)") >= 2, (
        "the listing and the run must both take their names from "
        "window_controls(), or they can disagree again")
    assert "for key, widget, kind, _d in w._persisted()" not in source, (
        "--list is walking _persisted() itself again")
