"""Looks somebody saved: kept, shared, and never destroyed by accident."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import looks
import picture


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A looks folder of its own, so a test never touches the real one."""
    monkeypatch.setattr(looks, "folder", lambda: tmp_path / "Picture Looks")
    return tmp_path / "Picture Looks"


A_LOOK = {"background": "white", "walls": "custom", "wall_colour": "#f2efe9",
          "lettering": "follow", "gridlines": "follow"}


# --------------------------------------------------------------------------
# The ready-made ones
# --------------------------------------------------------------------------

def test_every_ready_made_look_is_a_complete_answer():
    """A look that sets the background but not the lettering leaves somebody
    with pale grey on white, which is the fault these exist to prevent."""
    for key, label, why, values in picture.LOOKS:
        assert label and why, key
        if values is None:                    # "My own settings"
            assert key == "custom"
            continue
        if not values:                        # "As it looks on screen"
            assert key == "screen"
            continue
        assert "background" in values, key
        assert "lettering" in values, key


def test_a_cut_out_look_never_leaves_the_lettering_to_follow_nothing():
    """There is nothing behind a cut-out picture to follow, so both of them
    have to name a colour outright — and the two differ only in that."""
    light = picture.look("cutout-light")
    dark = picture.look("cutout-dark")
    assert light["background"] == dark["background"] == "transparent"
    assert light["lettering"] == "dark" and dark["lettering"] == "light"


def test_the_looks_that_choose_a_background_let_the_lettering_follow_it():
    for key in ("document", "report", "slide"):
        assert picture.look(key)["lettering"] == "follow"


# --------------------------------------------------------------------------
# Saving, sharing, removing
# --------------------------------------------------------------------------

def test_a_saved_look_comes_back_exactly(store):
    looks.save("Our white reports", A_LOOK)
    got = looks.load_all()
    assert len(got) == 1
    assert got[0]["name"] == "Our white reports"
    assert got[0]["look"] == A_LOOK


def test_a_look_is_one_ordinary_file_so_it_can_simply_be_sent(store):
    where = looks.save("Dark slides", A_LOOK)
    assert where.exists()
    assert where.suffix == ".json"
    data = json.loads(where.read_text(encoding="utf-8"))
    assert data["name"] == "Dark slides"
    assert data["look"]["background"] == "white"


def test_a_look_dropped_into_the_folder_is_picked_up_with_no_import(store):
    """Sharing has to be "put the file there", or it is not sharing."""
    store.mkdir(parents=True)
    (store / f"From a colleague{looks.SUFFIX}").write_text(json.dumps(
        {"name": "From a colleague", "look": {"background": "black",
                                              "lettering": "light"}}),
        encoding="utf-8")
    got = looks.load_all()
    assert [e["name"] for e in got] == ["From a colleague"]


def test_only_the_things_a_look_is_allowed_to_carry_are_kept(store):
    """A look is about how it looks. Letting it carry the length of a moving
    picture would mean one saved for a document quietly changed how long the
    next loop ran for."""
    looks.save("Mixed", dict(A_LOOK, seconds=11, fps=60, format="gif",
                             moving_width=600))
    kept = looks.load_all()[0]["look"]
    assert set(kept) <= set(looks.FIELDS)
    assert "seconds" not in kept and "format" not in kept


def test_removing_a_look_keeps_the_file(store):
    """A look can be an afternoon of matching a house style. It must not be
    one click away from gone."""
    looks.save("Careful work", A_LOOK)
    moved = looks.remove("Careful work")
    assert looks.load_all() == []
    assert moved.exists(), "the file was destroyed rather than put away"
    assert "old" in moved.parts
    assert json.loads(moved.read_text(encoding="utf-8"))["look"] == A_LOOK


def test_saving_over_a_look_keeps_the_one_it_replaced(store):
    looks.save("House style", A_LOOK)
    looks.save("House style", {"background": "black", "lettering": "light"})
    current = looks.load_all()
    assert len(current) == 1
    assert current[0]["look"]["background"] == "black"
    kept = list((store / "old").rglob(f"*{looks.SUFFIX}"))
    assert kept, "the version being replaced was not kept anywhere"
    assert json.loads(kept[0].read_text(encoding="utf-8"))["look"]["background"] \
        == "white"


def test_removing_something_that_is_not_there_says_so(store):
    with pytest.raises(looks.LookProblem):
        looks.remove("never existed")


def test_a_look_with_no_name_is_refused_with_a_reason(store):
    with pytest.raises(looks.LookProblem) as complaint:
        looks.save("   ", A_LOOK)
    assert "name" in str(complaint.value).lower()


def test_a_name_with_slashes_in_it_still_makes_one_file(store):
    """People name things after clients and dates, and both bring slashes."""
    where = looks.save("Acme 12/06 <final>", A_LOOK)
    assert where.parent == store
    assert "/" not in where.name.replace(looks.SUFFIX, "")
    assert looks.load_all()[0]["look"] == A_LOOK


def test_one_unreadable_file_does_not_take_the_others_with_it(store):
    """Hand-edited, half-copied, or written by something else entirely — one
    bad file must not empty the list."""
    looks.save("Good one", A_LOOK)
    looks.save("Another good one", A_LOOK)
    (store / f"broken{looks.SUFFIX}").write_text("{not json at all",
                                                 encoding="utf-8")
    (store / f"empty{looks.SUFFIX}").write_text("{}", encoding="utf-8")
    names = sorted(e["name"] for e in looks.load_all())
    assert names == ["Another good one", "Good one"]


def test_a_look_from_a_later_version_brings_across_what_is_understood(store):
    """Forwards compatibility: a field this version has never heard of is
    ignored rather than turning the whole look into an error."""
    store.mkdir(parents=True)
    (store / f"future{looks.SUFFIX}").write_text(json.dumps(
        {"name": "future", "look": {"background": "white",
                                    "shadow_softness": "very"}}),
        encoding="utf-8")
    got = looks.load_all()
    assert got[0]["look"] == {"background": "white"}


def test_there_is_no_folder_until_one_is_needed(store):
    assert not store.exists()
    assert looks.load_all() == []
    looks.save("First", A_LOOK)
    assert store.exists()


def test_the_folder_sits_beside_chromiqs_own_presets(monkeypatch):
    """Two applications from the same family putting shareable presets in two
    different places is how somebody loses an afternoon."""
    root = looks.presets_root()
    assert root.name == "presets"
    assert "ChromIQ" in str(root)
    assert looks.folder().parent == root


def test_a_saved_look_is_described_in_words_rather_than_in_settings(store):
    looks.save("Ours", A_LOOK)
    said = looks.describe(looks.load_all()[0])
    assert "white background" in said
    assert "follows" in said
    assert "background" in said and "as-shown" not in said
