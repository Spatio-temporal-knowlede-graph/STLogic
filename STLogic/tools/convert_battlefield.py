#!/usr/bin/env python
"""Convert the Hill-395 (백마고지) observation STKG into a TLogic-style dataset.

Output (in --dst), mirroring the TLogic data layout but with ONE extra column:

    train.txt / valid.txt / test.txt   # head \t relation \t tail \t timestamp \t location
    entity2id.json  relation2id.json  ts2id.json
    landmarks.tsv                      # landmark_name \t easting \t northing
    stats.yaml

`location` is the HEAD entity's coordinate "easting,northing" at that timestamp.
Baseline TLogic's grapher reads only columns 0-3 (it ignores the 5th), so the same
file serves both baseline TLogic and the STLogic spatial extension.

See docs/superpowers/specs/2026-07-16-battlefield-stkg-to-tlogic-converter-design.md
"""
import argparse
import json
import os
import re
from collections import OrderedDict

# ---- paths -------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SRC = os.path.normpath(os.path.join(
    HERE, "..", "..", "dataset", "백마고지 데이터셋", "battlefield_hill395_large"))
DEFAULT_DST = os.path.normpath(os.path.join(HERE, "..", "data", "battlefield_hill395"))

SPLIT_FILES = OrderedDict([("train", "train.txt"),
                           ("valid", "dev.txt"),   # TLogic calls it valid; source split is 'dev'
                           ("test", "test.txt")])

_LM_RE = re.compile(r'^<[^>]*/(lm_[^/>]+)>\s+<[^>]*/(easting|northing)>\s+"([^"]+)"')
_TOPKEY_RE = re.compile(r'^([A-Za-z]\w*):')


def load_ontology_relations(src):
    """Top-level predicate keys from ontology/relations.yaml (no yaml dep)."""
    path = os.path.join(src, "ontology", "relations.yaml")
    rels = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith((" ", "\t", "#")):
                continue
            m = _TOPKEY_RE.match(line)
            if m:
                rels.add(m.group(1))
    return rels


def read_split_sectors(src, source_split):
    """Ordered sector ids listed in splits/<source_split>.txt."""
    path = os.path.join(src, "splits", f"{source_split}.txt")
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


def parse_landmarks(sector_dir, sector):
    """{namespaced_landmark: (easting, northing)} from a sector's stkg.nt."""
    lm = {}
    path = os.path.join(sector_dir, "stkg.nt")
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = _LM_RE.match(line)
            if m:
                name, key, val = m.groups()
                lm.setdefault(f"{sector}/{name}", {})[key] = val
    out = {}
    for name, d in lm.items():
        if "easting" in d and "northing" in d:
            out[name] = (d["easting"], d["northing"])
    return out


def build_sector_rows(sector_dir, sector):
    """Return (rows, sorted_tokens, landmarks) for one sector.

    rows: list of (head, relation, tail, ts_token, location)
    sorted_tokens: ts tokens of this sector in ascending time order (for contiguous id assignment)
    landmarks: {namespaced_landmark: (easting, northing)}
    """
    obs_path = os.path.join(sector_dir, "observations.jsonl")
    records = []
    times = set()
    with open(obs_path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                r = json.loads(ln)
                records.append(r)
                times.add(r["time"])

    # ts tokens in ascending time order (global ids assigned contiguously by caller)
    sorted_tokens = [f"{sector}@{t}" for t in sorted(times)]

    rows = []
    ent_types = []  # (namespaced_entity, type) observations, aggregated by caller
    for r in records:
        head = f"{sector}/{r['local_entity_id']}"
        loc = f"{r['location']['easting']},{r['location']['northing']}"
        token = f"{sector}@{r['time']}"
        ent_types.append((head, r.get("type", "UNKNOWN")))
        for rel in r.get("relations", []):
            tail = f"{sector}/{rel['target_ref']}"
            rows.append((head, rel["predicate"], tail, token, loc))

    landmarks = parse_landmarks(sector_dir, sector)
    return rows, sorted_tokens, landmarks, ent_types


def convert(src, dst):
    ontology_rels = load_ontology_relations(src)
    os.makedirs(dst, exist_ok=True)

    rows_by_split = {s: [] for s in SPLIT_FILES}
    ts2id = {}
    landmarks = {}
    seen_pred = set()
    ent_type_counts = {}  # {namespaced_entity: {type: count}}

    # Global timestamp ids are assigned CONTIGUOUSLY in time order, per-sector block
    # (train sectors first, then dev, then test). This keeps ids small (fit np.uint16
    # used downstream in get_walks) while preserving within-sector time order — the
    # same rank-based timestamp scheme TLogic uses on ICEWS. Cross-sector leakage is
    # already prevented structurally: entities are namespaced per sector, so no walk or
    # rule grounding can span sectors regardless of timestamp adjacency.
    global_ts = 0
    for split, source_split in [("train", "train"), ("valid", "dev"), ("test", "test")]:
        sectors = read_split_sectors(src, source_split)
        for sector in sectors:
            sector_dir = os.path.join(src, "sectors", sector)
            rows, sorted_tokens, lm, ent_types = build_sector_rows(sector_dir, sector)
            for token in sorted_tokens:
                ts2id[token] = global_ts
                global_ts += 1
            rows_by_split[split].extend(rows)
            landmarks.update(lm)
            for ent, typ in ent_types:
                ent_type_counts.setdefault(ent, {})
                ent_type_counts[ent][typ] = ent_type_counts[ent].get(typ, 0) + 1
            for _, pred, _, _, _ in rows:
                seen_pred.add(pred)

    # validate predicates against the ontology
    unknown = seen_pred - ontology_rels
    if unknown:
        raise ValueError(f"Predicates not in ontology/relations.yaml: {sorted(unknown)}")

    # de-duplicate rows per split (keep first location) and collect nodes
    entities = set()
    for split in rows_by_split:
        seen = set()
        deduped = []
        for head, pred, tail, token, loc in rows_by_split[split]:
            key = (head, pred, tail, token)
            if key in seen:
                continue
            seen.add(key)
            deduped.append((head, pred, tail, token, loc))
            entities.add(head)
            entities.add(tail)
        rows_by_split[split] = deduped

    # id maps (sorted → deterministic)
    entity2id = {e: i for i, e in enumerate(sorted(entities))}
    relation2id = {r: i for i, r in enumerate(sorted(seen_pred))}
    ts2id = dict(sorted(ts2id.items(), key=lambda kv: kv[1]))

    # ---- write outputs -------------------------------------------------------
    for split, deduped in rows_by_split.items():
        out = os.path.join(dst, split + ".txt")
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            for head, pred, tail, token, loc in deduped:
                f.write(f"{head}\t{pred}\t{tail}\t{token}\t{loc}\n")

    for name, obj in [("entity2id.json", entity2id),
                      ("relation2id.json", relation2id),
                      ("ts2id.json", ts2id)]:
        with open(os.path.join(dst, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    with open(os.path.join(dst, "landmarks.tsv"), "w", encoding="utf-8", newline="\n") as f:
        for name in sorted(landmarks):
            e, n = landmarks[name]
            f.write(f"{name}\t{e}\t{n}\n")

    # entity_types.tsv: modal type per entity, preferring a non-UNKNOWN label.
    with open(os.path.join(dst, "entity_types.tsv"), "w", encoding="utf-8", newline="\n") as f:
        for ent in sorted(ent_type_counts):
            counts = ent_type_counts[ent]
            known = {t: c for t, c in counts.items() if t != "UNKNOWN"}
            pool = known if known else counts
            typ = max(pool.items(), key=lambda kv: (kv[1], kv[0]))[0]
            f.write(f"{ent}\t{typ}\n")

    stats = {
        "n_entities": len(entity2id),
        "n_relations": len(relation2id),
        "n_timestamps": len(ts2id),
        "n_landmarks": len(landmarks),
        "ts_scheme": "contiguous_per_sector_block",
        "max_ts_id": len(ts2id) - 1,
        "rows": {split: len(rows_by_split[split]) for split in rows_by_split},
        "relations": sorted(relation2id),
    }
    with open(os.path.join(dst, "stats.yaml"), "w", encoding="utf-8") as f:
        f.write("# battlefield_hill395 conversion stats\n")
        for k, v in stats.items():
            if isinstance(v, dict):
                f.write(f"{k}:\n")
                for kk, vv in v.items():
                    f.write(f"  {kk}: {vv}\n")
            elif isinstance(v, list):
                f.write(f"{k}: [{', '.join(v)}]\n")
            else:
                f.write(f"{k}: {v}\n")
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--dst", default=DEFAULT_DST)
    args = ap.parse_args()
    print(f"src = {args.src}")
    print(f"dst = {args.dst}")
    stats = convert(args.src, args.dst)
    print("done. stats:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
