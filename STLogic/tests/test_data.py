"""Tests for mycode/data.py — STKG normalization and the Position Provider.

The contract these pin down:
  get_facts()                    -> [(s, r, o, t), ...]
  get_position(entity, at)       -> (x, y) | None, never from after `at`
  source_of(entity, at)          -> direct | registry | anchor | None
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "mycode"))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

from data import load_vrforces, PositionProvider, EnuFrame  # noqa: E402

HEADER = ("subject,predicate,object,timestamp,latitude,longitude,"
          "obj_lat,obj_lon,source,Heading,CurrentSpeed,EntityType,Force\r\n")


def row(sub, pred, obj, ts, lat, lon, hd="0", sp="0"):
    return ("{},{},{},{},{},{},,,GROUND_TRUTH,{},{},1:1:1:1:0:0:0,1\r\n"
            .format(sub, pred, obj, ts, lat, lon, hd, sp))


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(HEADER)
        for r in rows:
            f.write(r)


def tiny_scene():
    """Two movers and one landmark, three ticks apart."""
    tmp = tempfile.mkdtemp()
    csv_path = os.path.join(tmp, "gt.csv")
    write_csv(csv_path, [
        row("ENA001", "move to", "LOC_목표A", "2026-09-11T13:00:00", "21.380", "-157.750"),
        row("ENA001", "move to", "LOC_목표A", "2026-09-11T13:00:10", "21.381", "-157.750"),
        row("ENA001", "move to", "LOC_목표A", "2026-09-11T13:00:20", "21.382", "-157.750"),
        row("FRB002", "move to", "LOC_목표B", "2026-09-11T13:00:00", "21.390", "-157.740"),
        row("FRB002", "move to", "LOC_목표B", "2026-09-11T13:00:20", "21.391", "-157.740"),
    ])
    reg_path = os.path.join(tmp, "layout.json")
    with open(reg_path, "w", encoding="utf-8") as f:
        json.dump({"locations": {
            "LOC_목표A": {"lat": 21.3830, "lon": -157.7500, "alt": 0, "src": "golden"},
            "LOC_목표B": {"lat": 21.3920, "lon": -157.7400, "alt": 0, "src": "golden"},
        }, "static_targets": {"EN-FP-001": "LOC_목표A"}}, f, ensure_ascii=False)
    return csv_path, reg_path


def ts(s):
    import datetime as dt
    return int(dt.datetime.fromisoformat("2026-09-11T" + s).timestamp())


# --------------------------------------------------------------- facts

def test_get_facts_returns_quadruples():
    csv_path, reg = tiny_scene()
    g = load_vrforces([csv_path], registry_path=reg)
    facts = g.get_facts()
    assert len(facts) == 5
    s, r, o, t = facts[0]
    assert (s, r, o) == ("ENA001", "move to", "LOC_목표A")
    assert isinstance(t, int)


def test_rows_without_object_are_dropped():
    tmp = tempfile.mkdtemp(); p = os.path.join(tmp, "gt.csv")
    write_csv(p, [row("ENA001", "none", "", "2026-09-11T13:00:00", "21.38", "-157.75")])
    g = load_vrforces([p])
    assert g.get_facts() == []
    # ...but the position track keeps the row: the track is metadata, not graph content
    assert g.get_position("ENA001", ts("13:00:00")) is not None


# --------------------------------------------------------------- dynamic lookup

def test_dynamic_position_is_latest_at_or_before():
    csv_path, reg = tiny_scene()
    g = load_vrforces([csv_path], registry_path=reg)
    at_10 = g.get_position("ENA001", ts("13:00:10"))
    at_15 = g.get_position("ENA001", ts("13:00:15"))
    at_20 = g.get_position("ENA001", ts("13:00:20"))
    assert at_10 == at_15, "13:00:15 must fall back to the 13:00:10 observation"
    assert at_20 != at_10


def test_never_returns_a_future_position():
    """The cutoff is enforced here so no downstream feature code can leak."""
    csv_path, reg = tiny_scene()
    g = load_vrforces([csv_path], registry_path=reg)
    first = g.get_position("ENA001", ts("13:00:00"))
    for later in ("13:00:10", "13:00:20"):
        assert g.get_position("ENA001", ts("13:00:00")) == first
        assert g.get_position("ENA001", ts(later)) != first or later == "13:00:00"
    assert g.get_position("ENA001", ts("12:59:59")) is None, "before first observation"


def test_source_is_direct_for_movers():
    csv_path, reg = tiny_scene()
    g = load_vrforces([csv_path], registry_path=reg)
    assert g.source_of("ENA001", ts("13:00:10")) == "direct"


# --------------------------------------------------------------- registry

def test_static_location_comes_from_registry():
    csv_path, reg = tiny_scene()
    g = load_vrforces([csv_path], registry_path=reg)
    p = g.get_position("LOC_목표A", ts("13:00:00"))
    assert p is not None
    assert g.source_of("LOC_목표A", ts("13:00:00")) == "registry"


def test_static_position_is_time_independent():
    csv_path, reg = tiny_scene()
    g = load_vrforces([csv_path], registry_path=reg)
    a = g.get_position("LOC_목표A", ts("13:00:00"))
    b = g.get_position("LOC_목표A", ts("13:00:20"))
    assert a == b


def test_static_target_alias_resolves_to_its_location():
    """static_targets maps an entity id onto a landmark; ids lose their hyphens."""
    csv_path, reg = tiny_scene()
    g = load_vrforces([csv_path], registry_path=reg)
    assert g.get_position("ENFP001", ts("13:00:00")) == g.get_position("LOC_목표A", ts("13:00:00"))
    assert g.source_of("ENFP001", ts("13:00:00")) == "registry"


# --------------------------------------------------------------- anchor fallback

def test_anchor_derivation_when_registry_absent():
    """No registry: a landmark's position is the subject position where its edge ends."""
    csv_path, _ = tiny_scene()
    g = load_vrforces([csv_path], registry_path=None, derive_anchors=True)
    p = g.get_position("LOC_목표A", ts("13:00:20"))
    assert p is not None
    assert g.source_of("LOC_목표A", ts("13:00:20")) == "anchor"
    # ENA001's last tick on that order is 13:00:20, so the anchor sits there
    assert p == g.get_position("ENA001", ts("13:00:20"))


def test_anchor_derivation_respects_its_cutoff():
    """Anchors fitted on a training window must not see later observations."""
    csv_path, _ = tiny_scene()
    early = load_vrforces([csv_path], registry_path=None, derive_anchors=True,
                          anchor_cutoff=ts("13:00:10"))
    late = load_vrforces([csv_path], registry_path=None, derive_anchors=True)
    assert early.get_position("LOC_목표A", ts("13:00:20")) != \
        late.get_position("LOC_목표A", ts("13:00:20"))


def test_registry_beats_anchor():
    csv_path, reg = tiny_scene()
    g = load_vrforces([csv_path], registry_path=reg, derive_anchors=True)
    assert g.source_of("LOC_목표A", ts("13:00:20")) == "registry"


# --------------------------------------------------------------- absence

def test_unknown_entity_returns_none():
    csv_path, reg = tiny_scene()
    g = load_vrforces([csv_path], registry_path=reg)
    assert g.get_position("NOSUCH", ts("13:00:00")) is None
    assert g.source_of("NOSUCH", ts("13:00:00")) is None


# --------------------------------------------------------------- frame

def test_enu_is_consistent_across_lookups():
    csv_path, reg = tiny_scene()
    g = load_vrforces([csv_path], registry_path=reg)
    a = g.get_position("ENA001", ts("13:00:10"))
    b = g.get_position("ENA001", ts("13:00:10"))
    assert a == b
    assert all(abs(v) < 1e7 for v in a), "metres, not degrees"


def test_one_frame_is_shared_by_dynamic_and_static():
    """A landmark and a unit at the same lat/lon must land on the same point."""
    tmp = tempfile.mkdtemp(); p = os.path.join(tmp, "gt.csv")
    write_csv(p, [row("ENA001", "move to", "LOC_X", "2026-09-11T13:00:00",
                      "21.3830", "-157.7500")])
    reg = os.path.join(tmp, "l.json")
    with open(reg, "w", encoding="utf-8") as f:
        json.dump({"locations": {"LOC_X": {"lat": 21.3830, "lon": -157.7500}}}, f)
    g = load_vrforces([p], registry_path=reg)
    ent = g.get_position("ENA001", ts("13:00:00"))
    loc = g.get_position("LOC_X", ts("13:00:00"))
    assert abs(ent[0] - loc[0]) < 1e-6 and abs(ent[1] - loc[1]) < 1e-6


# --------------------------------------------------------------- observers

def test_gt_and_uav_expose_the_same_interface():
    tmp = tempfile.mkdtemp()
    gt = os.path.join(tmp, "gt.csv"); uav = os.path.join(tmp, "uav.csv")
    write_csv(gt, [row("ENA001", "move to", "LOC_A", "2026-09-11T13:00:00", "21.38", "-157.75"),
                   row("FRB002", "move to", "LOC_A", "2026-09-11T13:00:00", "21.39", "-157.74")])
    write_csv(uav, [row("ENA001", "move to", "LOC_A", "2026-09-11T13:00:00", "21.38", "-157.75")])
    a, b = load_vrforces([gt]), load_vrforces([uav])
    for g in (a, b):
        assert callable(g.get_facts) and callable(g.get_position)
    assert b.get_position("FRB002", ts("13:00:00")) is None, "UAV never saw it"
    assert a.get_position("FRB002", ts("13:00:00")) is not None


def test_several_observers_merge_into_one_view():
    tmp = tempfile.mkdtemp()
    u1 = os.path.join(tmp, "u1.csv"); u2 = os.path.join(tmp, "u2.csv")
    write_csv(u1, [row("ENA001", "move to", "LOC_A", "2026-09-11T13:00:00", "21.38", "-157.75")])
    write_csv(u2, [row("FRB002", "move to", "LOC_A", "2026-09-11T13:00:00", "21.39", "-157.74")])
    g = load_vrforces([u1, u2])
    assert g.get_position("ENA001", ts("13:00:00")) is not None
    assert g.get_position("FRB002", ts("13:00:00")) is not None


if __name__ == "__main__":
    import traceback
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("PASS " + name)
            except Exception:
                failures += 1; print("FAIL " + name); traceback.print_exc()
    print("\n%d failed" % failures if failures else "\nall passed")
    sys.exit(1 if failures else 0)
