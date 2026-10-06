"""STKG normalization and the Position Provider.

Everything downstream sees exactly two things, and never learns where they came
from -- CSV row, position table, or static registry:

    get_facts()                -> [(s, r, o, t), ...]
    get_position(entity, at)   -> (east, north) | None

Position sources, in priority order (spec §2.2):

    direct    ≻  registry  ≻  anchor derivation  ≻  None

`direct` is the entity's own observation track. `registry` is a supplied static
coordinate. `anchor` derives a static entity's position from the subject positions
where edges pointing at it TERMINATE -- a normalization fallback for datasets with
no registry, not spatial inference: every coordinate it uses is one that was
actually observed.

Two invariants this module exists to enforce:

  * `get_position(e, at)` NEVER returns an observation later than `at`. Putting the
    cutoff here means no feature or candidate code downstream can leak the future
    by forgetting to pass `obs`.
  * Anchors are derived only from observations at or before `anchor_cutoff`, so a
    model fitted on a training window cannot be handed a landmark position that was
    computed from test-window movement.

This module does NOT compute d or v_d -- that is spatial.py's job.
"""
import bisect
import csv
import math
import random
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "tools")))
from build_vrforces_dataset import EnuFrame  # noqa: E402,F401  (re-exported)

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

REQUIRED = ("subject", "predicate", "object", "timestamp", "latitude", "longitude")


def normalise_id(entity_id):
    """Registry ids carry hyphens (EN-FP-001); STKG ids do not (ENFP001)."""
    return entity_id.replace("-", "")


def to_epoch(stamp):
    return int(dt.datetime.fromisoformat(stamp).timestamp())


class PositionProvider:
    """Answers `where was this entity at or before `at`?` from any source."""

    def __init__(self, frame, tracks, registry=None, anchors=None):
        self.frame = frame
        self._tracks = {}
        for ent, series in tracks.items():
            times = sorted(series)
            self._tracks[ent] = (times, [series[t] for t in times])
        self._registry = dict(registry or {})
        self._anchors = dict(anchors or {})

    def get_position(self, entity, at):
        """(east, north) in metres, or None. Never from an observation after `at`."""
        track = self._tracks.get(entity)
        if track is not None:
            times, points = track
            i = bisect.bisect_right(times, at) - 1
            if i >= 0:
                return points[i]
            # observed, but not yet by `at` -- fall through to a static source
        if entity in self._registry:
            return self._registry[entity]
        if entity in self._anchors:
            return self._anchors[entity]
        return None

    def source_of(self, entity, at):
        """Which rung of the priority ladder answered: direct|registry|anchor|None."""
        track = self._tracks.get(entity)
        if track is not None and bisect.bisect_right(track[0], at) - 1 >= 0:
            return "direct"
        if entity in self._registry:
            return "registry"
        if entity in self._anchors:
            return "anchor"
        return None

    def recent_times(self, entity, at, k=2):
        """The k most recent observation times at or before `at`, newest first.

        Static sources have no observation times and return []. spatial.py uses this
        to set δ per query rather than as a global constant -- see spec §3.3.
        """
        track = self._tracks.get(entity)
        if track is None:
            return []
        times = track[0]
        i = bisect.bisect_right(times, at)
        return list(reversed(times[max(0, i - k):i]))

    def entities_with_position(self, at):
        """Every entity groundable at `at` -- the spatial universe for one query."""
        out = set(self._registry) | set(self._anchors)
        for ent, (times, _) in self._tracks.items():
            if times and times[0] <= at:
                out.add(ent)
        return out


class STKG:
    """Normalised graph: temporal facts plus a Position Provider."""

    def __init__(self, facts, positions):
        self._facts = facts
        self.positions = positions

    def get_facts(self):
        return list(self._facts)

    def get_position(self, entity, at):
        return self.positions.get_position(entity, at)

    def source_of(self, entity, at):
        return self.positions.source_of(entity, at)

    def entities_with_position(self, at):
        return self.positions.entities_with_position(at)


def _read_rows(paths):
    """[(epoch, subject, predicate, object, lat, lon)] over every observer file."""
    out = []
    for p in paths:
        with open(p, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
            if missing:
                raise ValueError("%s: missing column(s) %s" % (p, ", ".join(missing)))
            for r in reader:
                lat, lon = r["latitude"].strip(), r["longitude"].strip()
                out.append((to_epoch(r["timestamp"]),
                            r["subject"].strip(), r["predicate"].strip(),
                            r["object"].strip(),
                            float(lat) if lat else None,
                            float(lon) if lon else None))
    out.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
    return out


def _load_registry(path):
    """(name -> (lat, lon), alias_entity -> name) from a static spatial registry."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    coords = {name: (v["lat"], v["lon"]) for name, v in doc.get("locations", {}).items()}
    aliases = {normalise_id(k): v for k, v in doc.get("static_targets", {}).items()}
    return coords, aliases


def _spans(rows, frame, cutoff):
    """{(relation, object): [(start_xy, end_xy), ...]} per contiguous edge."""
    spans = {}
    current = {}
    for t, sub, pred, obj, lat, lon in rows:
        if cutoff is not None and t > cutoff:
            break
        if not obj or lat is None:
            continue
        xy = frame.to_enu(lat, lon)
        key = (sub, pred)
        held = current.get(key)
        if held is None:
            current[key] = (obj, xy, xy)
        elif held[0] != obj:
            spans.setdefault((pred, held[0]), []).append((held[1], held[2]))
            current[key] = (obj, xy, xy)
        else:
            current[key] = (obj, held[1], xy)
    for (sub, pred), (obj, start, end) in current.items():
        spans.setdefault((pred, obj), []).append((start, end))
    return spans


def _derive_anchors(rows, frame, cutoff, min_samples):
    """{object: (east, north)} for entities a relation CONVERGES on.

    A `(s, r, o)` edge ending at tick t puts s somewhere; if s was travelling toward
    o, that somewhere estimates o. But not every relation converges -- a unit that
    shells a location fires from its gun line and never approaches the target, so its
    position says nothing about where the target is.

    Spread alone cannot tell the two apart: on VR-Forces, `FFE-on-Location` has the
    TIGHTEST termination spread of any relation (4 m -- gun lines are consistent) and
    is the most wrong (2,697 m off). What separates them is whether subjects closed
    the distance:

        relation                      spread   convergence   error
        move to                        103 m       616 m      54 m   -> anchor
        Provide-Suppressive-Fire-Loc   533 m         0 m   1,350 m   -> rejected
        FFE-on-Location                  4 m         0 m   2,697 m   -> rejected

    So a (relation, object) pair anchors only when its subjects moved toward the
    estimate by more than the estimate's own scatter. No domain knowledge involved --
    positions decide.
    """
    out = {}
    for (pred, obj), sp in _spans(rows, frame, cutoff).items():
        if len(sp) < min_samples:
            continue
        ends = [e for _, e in sp]
        cx = sum(p[0] for p in ends) / len(ends)
        cy = sum(p[1] for p in ends) / len(ends)
        spread = (sum((p[0]-cx)**2 + (p[1]-cy)**2 for p in ends) / len(ends)) ** 0.5
        closed = sorted(math.dist(s, (cx, cy)) - math.dist(e, (cx, cy)) for s, e in sp)
        if closed[len(closed)//2] <= spread:
            continue                            # subjects did not converge -> not an anchor
        prev = out.get(obj)
        if prev is None or len(sp) > prev[1]:
            out[obj] = ((cx, cy), len(sp))      # keep the best-supported relation
    return {o: xy for o, (xy, _) in out.items()}


def observation_patterns(csv_paths):
    """Per-entity sets of observation times, one donor pattern per entity.

    Sampling from a *gap histogram* does not reproduce a sensor's cadence: 90% of
    the UAV gaps are 1 s because a UAV also logs at 1 Hz while a target is in view.
    What separates it from ground truth is the burst structure -- long stretches of
    nothing between periods of continuous view -- and the coverage that follows from
    it (UAV ≈ 18% of ticks per entity, GT ≈ 97%). Borrowing whole patterns keeps
    both intact.
    """
    times = {}
    for t, sub, pred, obj, lat, lon in _read_rows(csv_paths):
        if lat is not None:
            times.setdefault(sub, set()).add(t)
    return [frozenset(v) for v in times.values() if v]


def thin_positions(stkg, patterns, seed=0):
    """A copy of `stkg` whose tracks are restricted to donor observation patterns.

    This is the GT-Sparse-δ control. It answers one question and must not answer any
    other: *the same entities are still there, just observed less often.* So every
    entity keeps a track (never dropped, never emptied -- the first observation is
    always retained) and only the TIMESTAMPS thin out. Facts, registry and anchors
    pass through untouched, so the temporal graph is unchanged and the
    sampling-interval effect stays separated from entity and edge loss.
    """
    if not patterns:
        return stkg
    rng = random.Random(seed)
    pp = stkg.positions
    thinned = {}
    for ent in sorted(pp._tracks):                      # sorted -> seed reproducible
        times, points = pp._tracks[ent]
        donor = patterns[rng.randrange(len(patterns))]
        keep = {t: p for t, p in zip(times, points) if t in donor}
        if not keep:
            keep = {times[0]: points[0]}                # coverage is never lost
        thinned[ent] = keep
    return STKG(stkg.get_facts(),
                PositionProvider(pp.frame, thinned, pp._registry, pp._anchors))


def load_vrforces(csv_paths, registry_path=None, derive_anchors=False,
                  anchor_cutoff=None, anchor_min_samples=1):
    """Build an STKG from one or more VR-Forces observer exports.

    csv_paths          one file per observer; several are merged into one view
    registry_path      optional static spatial registry (battlefield_layout.json)
    derive_anchors     fall back to observed-anchor derivation where no registry entry
    anchor_cutoff      epoch; anchors see nothing after it (None = whole file)
    anchor_min_samples drop an anchor estimated from fewer arrivals than this
    """
    if isinstance(csv_paths, str):
        csv_paths = [csv_paths]
    rows = _read_rows(csv_paths)
    if not rows:
        raise ValueError("no rows read from %s" % ", ".join(csv_paths))

    reg_ll, aliases = ({}, {})
    if registry_path:
        reg_ll, aliases = _load_registry(registry_path)

    # One frame for everything, so a unit and a landmark at the same lat/lon land on
    # the same point. Built before anchors, which are derived in this frame.
    lats = [r[4] for r in rows if r[4] is not None]
    lons = [r[5] for r in rows if r[5] is not None]
    lats += [v[0] for v in reg_ll.values()]
    lons += [v[1] for v in reg_ll.values()]
    if not lats:
        raise ValueError("no coordinates found; cannot build a frame")
    frame = EnuFrame(sum(lats)/len(lats), sum(lons)/len(lons))

    tracks = {}
    facts = []
    for t, sub, pred, obj, lat, lon in rows:
        if lat is not None and lon is not None:
            tracks.setdefault(sub, {})[t] = frame.to_enu(lat, lon)
        if obj:                                # no object -> not a triple
            facts.append((sub, pred, obj, t))

    registry = {name: frame.to_enu(*ll) for name, ll in reg_ll.items()}
    for alias, name in aliases.items():        # static_targets: entity -> landmark
        if name in registry:
            registry[alias] = registry[name]

    anchors = {}
    if derive_anchors:
        for obj, xy in _derive_anchors(rows, frame, anchor_cutoff,
                                       anchor_min_samples).items():
            if obj not in registry:            # registry wins
                anchors[obj] = xy

    return STKG(facts, PositionProvider(frame, tracks, registry, anchors))
