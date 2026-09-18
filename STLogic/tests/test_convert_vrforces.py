"""Tests for tools/convert_vrforces.py."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

from convert_vrforces import convert_file  # noqa: E402

# A miniature VR-Forces export: the 8 leading columns the converter cares about
# plus one trailing column, to prove the extra 50+ columns are simply dropped.
HEADER = ("subject,predicate,object,timestamp,latitude,longitude,"
          "obj_lat,obj_lon,source,StateResolution\r\n")
ROWS = (
    # normal row, Korean object
    "ENM1A2003,move to,LOC_중앙계곡,2026-09-11T13:21:42,"
    "21.37337840,-157.74310685,,,UAV 1,RESOLVED_DIRECT_API\r\n"
    # empty object -> dropped
    "FRM901001,none,,2026-09-11T13:21:42,"
    "21.39239887,-157.74004512,,,UAV 1,RESOLVED_DIRECT_API\r\n"
    # missing coordinates -> kept, location left blank
    "ENINF037,Wait-Duration,30,2026-09-11T13:21:43,"
    ",,,,UAV 1,RESOLVED_DIRECT_API\r\n"
    # obj_lat/obj_lon present (Fire-Weapon) -> ignored, subject coords used
    "ENBTR60001,Fire-Weapon,FRINF027,2026-09-11T13:21:44,"
    "21.36000000,-157.75000000,21.38,-157.73,UAV 1,RESOLVED_DIRECT_API\r\n"
)

def run_convert(rows=ROWS, header=HEADER):
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "in.csv")
    dst = os.path.join(tmp, "out.csv")
    with open(src, "w", encoding="utf-8", newline="") as f:
        f.write(header)
        f.write(rows)
    stats = convert_file(src, dst)
    with open(dst, "rb") as f:
        return f.read(), stats


def test_converted_bytes_are_exact():
    data, _ = run_convert()
    expected = (
        "subject,predicate,object,timestamp,location\n"
        'ENM1A2003,move to,LOC_중앙계곡,2026-09-11T13:21:42,'
        '"(21.37337840, -157.74310685)"\n'
        "ENINF037,Wait-Duration,30,2026-09-11T13:21:43,\n"
        'ENBTR60001,Fire-Weapon,FRINF027,2026-09-11T13:21:44,'
        '"(21.36000000, -157.75000000)"\n'
    ).encode("utf-8")
    assert data == expected


def test_line_endings_are_lf_only():
    data, _ = run_convert()
    assert b"\r" not in data


def test_stats():
    _, stats = run_convert()
    assert stats["read"] == 4
    assert stats["written"] == 3
    assert stats["skipped_empty_object"] == 1
    assert stats["missing_location"] == 1


def test_header_column_order_is_not_assumed():
    """Columns are looked up by name, not position."""
    header = "timestamp,longitude,subject,object,latitude,predicate\r\n"
    rows = "2026-09-11T13:21:42,-157.74310685,ENM1A2003,LOC_중앙계곡,21.37337840,move to\r\n"
    data, _ = run_convert(rows=rows, header=header)
    expected = (
        "subject,predicate,object,timestamp,location\n"
        'ENM1A2003,move to,LOC_중앙계곡,2026-09-11T13:21:42,'
        '"(21.37337840, -157.74310685)"\n'
    ).encode("utf-8")
    assert data == expected


if __name__ == "__main__":
    import traceback
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception:
                failures += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    sys.exit(1 if failures else 0)
