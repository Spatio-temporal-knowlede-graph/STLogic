# new_VTMAK 파이프라인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `scenario_v3.txt` 하나를 입력받아 VR-Forces 4.9 `.scnx` 시나리오 파일 하나를 결정적으로 생성한다.

**Architecture:** 원문 → 템플릿 파서 → 이벤트 JSONL → 타임테이블 → 확정 스펙 → `.scnx`. 좌표는 golden 앵커링 대신 시나리오 기하를 로컬 미터 좌표로 선언한 `battlefield_layout.json`에서 나온다. `.scnx` 저작 백엔드(golden 레코드 복제)는 선행 프로젝트 `VTMAK/`에서 이식한다.

**Tech Stack:** Python 3.13, pytest 8.4, 표준 라이브러리만 (csv/json/re/math/hashlib/zipfile/dataclasses). 외부 의존성 없음.

## Global Constraints

- 설계 스펙: `docs/superpowers/specs/2026-08-02-new-vtmak-scnx-pipeline-design.md`. 충돌 시 스펙이 우선.
- 작업 루트: `new_VTMAK/`. 경로에 공백과 한글이 있으므로 셸 명령에서 항상 따옴표로 감쌀 것.
- **파이프라인이 읽는 시나리오 입력은 `new_VTMAK/scenario_original/scenario_v3.txt` 단독.** `시나리오_원문.md`와 PNG는 참고 자료이며 코드가 절대 참조하지 않는다.
- 모든 변환은 결정적이어야 한다. 같은 입력이면 항상 같은 산출물. 난수·시각·딕셔너리 순서 의존 금지. 정렬이 필요하면 명시적으로 `sorted()`.
- `VTMAK/`는 읽기 전용 참조. 수정하지 않는다.
- 어휘를 코드에 하드코딩하지 않는다. 지명·모델명·사거리·술어 매핑은 전부 `new_VTMAK/config/`의 CSV/JSON에서 온다.
- 정규화 함수는 프로젝트 전체에서 하나만 쓴다: `norm(s) = re.sub(r"[\s\-]+", "", s or "").lower()`. 모델명 매칭(`T-72 MBT` ↔ `T 72 MBT`)이 여기에 의존한다.
- 좌표계: `battlefield_layout`은 로컬 미터(북 = +y, 동 = +x) → WGS84 위경도 → `.scnx` 기록 시 ECEF geocentric 미터.
- 고도는 전부 0. VR-Forces의 Ground Clamping에 맡긴다.
- 테스트는 `new_VTMAK/tests/`에 두고 `pytest`로 돌린다. `conftest.py`가 `sys.path`에 패키지 루트를 주입한다(경로에 공백이 있어 설치 방식을 쓰지 않는다).
- 커밋 메시지는 한국어, `feat(new_vtmak):` / `test(new_vtmak):` / `chore(new_vtmak):` 접두사.

---

## File Structure

```
new_VTMAK/
├─ config/
│  ├─ battlefield_layout.json     신규 — 지명 27개 로컬 좌표 + 정적객체 바인딩
│  ├─ weapon_ranges.csv           신규 — entity_class → 직접/간접 사거리
│  ├─ pattern_map.csv             신규 — 템플릿·이동행동 → 술어 + task_kind
│  ├─ entity_class_map.csv        신규 — entity_class → type_group + 무기명
│  ├─ dis_catalog.csv             VTMAK에서 복사 (26종)
│  └─ task_catalog.csv            VTMAK에서 복사 (33행)
├─ vtmak/
│  ├─ __init__.py
│  ├─ norm.py                     정규화 함수 하나
│  ├─ geometry.py                 Coord + BattlefieldLayout
│  ├─ ranges.py                   WeaponRanges + 사거리 판정
│  ├─ parser.py                   원문 → Event (템플릿 21종)
│  ├─ registry.py                 Event → EntityDef/LocationDef 자동 생성
│  ├─ timetable.py                VTMAK에서 복사 (수정 없음)
│  ├─ gates.py                    G0/G1/G2
│  └─ scnx/
│     ├─ __init__.py
│     ├─ ids.py                   VTMAK 복사 (수정 없음)
│     ├─ catalog.py               VTMAK 복사 (수정 없음)
│     ├─ golden.py                VTMAK 복사 (수정 없음)
│     ├─ plan.py                  VTMAK 복사 + 사거리 검사 위임으로 변경
│     ├─ spec.py                  신규 작성 (플랜 보강 제거, layout 사용)
│     ├─ writer.py                VTMAK 복사 + golden 기본값 변경
│     └─ gates.py                 G3 — VTMAK 복사 + DIS 커버리지 검사 추가
├─ scripts/
│  ├─ 02_parse_events.py
│  ├─ 03_build_timetable.py
│  └─ 04_compile_scnx.py       (설계 스펙 §7의 harvest_golden.py는 만들지 않는다 —
│                               dis_catalog 26종이 이미 완성돼 수확할 것이 없다)
├─ tests/
│  ├─ conftest.py
│  ├─ test_geometry.py
│  ├─ test_ranges.py
│  ├─ test_parser.py
│  ├─ test_registry.py
│  ├─ test_gates.py
│  ├─ test_spec.py
│  └─ test_writer.py
├─ build/                         산출물 (gitignore)
└─ README.md
```

책임 분리 원칙: `geometry`는 좌표만, `ranges`는 사거리 판정만, `parser`는 문장→이벤트만, `registry`는 이벤트→사전만 안다. `gates`가 이들을 조합해 검증한다. `scnx/`는 이벤트·사전·좌표를 받아 파일을 쓴다.

---

### Task 1: 스캐폴딩과 정규화

**Files:**
- Create: `new_VTMAK/vtmak/__init__.py` (빈 파일)
- Create: `new_VTMAK/vtmak/scnx/__init__.py` (빈 파일)
- Create: `new_VTMAK/vtmak/norm.py`
- Create: `new_VTMAK/tests/conftest.py`
- Create: `new_VTMAK/.gitignore`
- Test: `new_VTMAK/tests/test_norm.py`

**Interfaces:**
- Consumes: 없음
- Produces: `vtmak.norm.norm(s: str) -> str` — 공백·하이픈 제거 후 소문자화. `vtmak.norm.loc_id(surface: str) -> str` — 지명 표면형 → `LOC_` 접두 id (공백만 제거, 대소문자·한글 보존).

- [ ] **Step 1: 디렉터리와 빈 파일 생성**

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK"
mkdir -p vtmak/scnx scripts tests config build
touch vtmak/__init__.py vtmak/scnx/__init__.py
```

- [ ] **Step 2: `.gitignore` 작성**

`new_VTMAK/.gitignore`:

```
build/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 3: `tests/conftest.py` 작성**

```python
import sys
from pathlib import Path

# 패키지 루트를 import 경로에 넣는다. 경로에 공백과 한글이 있어 설치 방식
# 대신 sys.path 주입을 쓴다(선행 프로젝트와 동일).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

- [ ] **Step 4: 실패하는 테스트 작성**

`new_VTMAK/tests/test_norm.py`:

```python
from vtmak.norm import loc_id, norm


def test_norm_makes_hyphen_and_space_variants_equal():
    # 원문은 'T-72 MBT', dis_catalog는 'T 72 MBT'로 적혀 있다.
    assert norm("T-72 MBT") == norm("T 72 MBT")
    assert norm("MO-120RT-61 Mortar") == norm("MO 120RT 61 Mortar")
    assert norm("US ArmyM4") == norm("US Army M4")


def test_norm_does_not_collide_across_distinct_models():
    assert norm("M901 Patriot Launcher") != norm("MIM-104 Patriot Launcher")
    assert norm("T-69 MBT") != norm("T-72 MBT")


def test_norm_handles_none_and_empty():
    assert norm(None) == ""
    assert norm("") == ""


def test_loc_id_prefixes_and_strips_spaces_only():
    assert loc_id("남측 제1방어선") == "LOC_남측제1방어선"
    assert loc_id("목표 A 남측") == "LOC_목표A남측"


def test_loc_id_is_idempotent():
    assert loc_id(loc_id("중앙 킬존")) == "LOC_중앙킬존"
```

- [ ] **Step 5: 테스트 실패 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_norm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtmak.norm'`

- [ ] **Step 6: 최소 구현**

`new_VTMAK/vtmak/norm.py`:

```python
"""문자열 정규화 — 프로젝트 전체가 이 두 함수만 쓴다.

원문·dis_catalog·task_catalog가 같은 모델을 다르게 적는다
('T-72 MBT' / 'T 72 MBT'). 매칭 키를 여기서 한 곳으로 모은다.
"""
from __future__ import annotations

import re


def norm(s: str | None) -> str:
    """모델명·클래스명 매칭 키. 공백과 하이픈을 지우고 소문자화."""
    return re.sub(r"[\s\-]+", "", s or "").lower()


def loc_id(surface: str | None) -> str:
    """지명 표면형 → LOC_ 접두 식별자. 공백만 지우고 원문자는 보존한다.

    사람이 config를 읽고 고칠 수 있어야 하므로 한글을 남긴다.
    이미 LOC_로 시작하면 그대로 돌려준다(멱등).
    """
    s = re.sub(r"\s+", "", surface or "")
    return s if s.startswith("LOC_") else f"LOC_{s}"
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_norm.py -v`
Expected: PASS (5 passed)

- [ ] **Step 8: 커밋**

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments"
git add new_VTMAK/vtmak new_VTMAK/tests new_VTMAK/.gitignore
git commit -m "feat(new_vtmak): 프로젝트 골격과 정규화 함수"
```

---

### Task 2: 좌표 엔진 — Coord와 BattlefieldLayout

**Files:**
- Create: `new_VTMAK/vtmak/geometry.py`
- Create: `new_VTMAK/config/battlefield_layout.json`
- Test: `new_VTMAK/tests/test_geometry.py`
- Reference: `VTMAK/vtmak/scnx/geometry.py:29-72` (Coord 클래스 — 그대로 이식)

**Interfaces:**
- Consumes: `vtmak.norm.loc_id`
- Produces:
  - `Coord(lat: float, lon: float, alt: float)` — `.as_tuple()`, `.is_zero()`, `.to_ecef() -> tuple[float,float,float]`, `Coord.from_ecef(x,y,z) -> Coord`
  - `BattlefieldLayout` — `.load(path) -> BattlefieldLayout`, `.terrain: str`, `.scale: float`, `.coord(location_id: str) -> Coord`, `.offset_coord(location_id, dx, dy) -> Coord`, `.local(location_id: str) -> tuple[float,float] | None`, `.location_ids() -> list[str]`, `.static_target(object_id: str) -> str | None`, `.static_ids() -> set[str]`, `.distance_m(a_id: str, b_id: str) -> float`
  - `ground_distance(a: Coord, b: Coord) -> float` — ECEF 직선거리

- [ ] **Step 1: 실패하는 테스트 작성**

`new_VTMAK/tests/test_geometry.py`:

```python
import math
from pathlib import Path

import pytest

from vtmak.geometry import BattlefieldLayout, Coord, ground_distance

CONFIG = Path(__file__).resolve().parents[1] / "config" / "battlefield_layout.json"


@pytest.fixture(scope="module")
def layout():
    return BattlefieldLayout.load(CONFIG)


def test_ecef_roundtrip():
    c = Coord(21.3860, -157.7420, 0.0)
    back = Coord.from_ecef(*c.to_ecef())
    assert abs(back.lat - c.lat) < 1e-9
    assert abs(back.lon - c.lon) < 1e-9
    assert abs(back.alt - c.alt) < 1e-3


def test_origin_maps_to_killzone():
    # 중앙 킬존이 로컬 원점이므로 layout origin과 같은 좌표여야 한다.
    lay = BattlefieldLayout.load(CONFIG)
    c = lay.coord("LOC_중앙킬존")
    assert abs(c.lat - 21.3860) < 1e-9
    assert abs(c.lon - (-157.7420)) < 1e-9


def test_local_meters_survive_projection(layout):
    # 로컬 좌표 차이가 실제 지표 거리로 1% 이내에서 보존되는가.
    for a, b, expect in [
        ("LOC_중앙킬존", "LOC_중앙킬존남측", 250.0),
        ("LOC_아군포병진지", "LOC_중앙킬존", 2807.0),
        ("LOC_적포병진지", "LOC_아군포병진지", 5600.0),
    ]:
        d = layout.distance_m(a, b)
        assert abs(d - expect) / expect < 0.01, f"{a}->{b}: {d} vs {expect}"


def test_all_27_locations_present(layout):
    ids = layout.location_ids()
    assert len(ids) == 27
    for must in ["LOC_남측제1방어선", "LOC_적북측집결지", "LOC_중앙킬존",
                 "LOC_아군포병진지", "LOC_적박격포진지", "LOC_동측측방접근로"]:
        assert must in ids


def test_unknown_location_returns_zero(layout):
    assert layout.coord("LOC_없는지명").is_zero()


def test_static_targets_bind_to_locations(layout):
    assert layout.static_target("EN-FP-001") == "LOC_적포병진지"
    assert layout.static_target("OBJ-009") == "LOC_중앙킬존"
    assert layout.static_target("FR-INF-001") is None


def test_scale_multiplies_distances():
    lay = BattlefieldLayout.load(CONFIG)
    base = lay.distance_m("LOC_아군포병진지", "LOC_중앙킬존")
    lay.scale = 0.5
    assert abs(lay.distance_m("LOC_아군포병진지", "LOC_중앙킬존") - base / 2) < 5.0


def test_deterministic(layout):
    a = [layout.coord(i).as_tuple() for i in layout.location_ids()]
    b = [layout.coord(i).as_tuple() for i in layout.location_ids()]
    assert a == b


def test_ground_distance_matches_flat_approximation():
    a = Coord(21.3860, -157.7420, 0.0)
    b = Coord(21.3860 + 1000 / 110574.0, -157.7420, 0.0)
    assert abs(ground_distance(a, b) - 1000.0) < 5.0
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_geometry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtmak.geometry'`

- [ ] **Step 3: `config/battlefield_layout.json` 작성**

좌표는 설계 스펙 §3.4 확정 레이아웃 그대로다. 사거리 제약 검증은 §3.5에 있다.

```json
{
  "layout_id": "scenario_v3_ala_moana_v1",
  "terrain": "..\\userData\\terrains\\Ala Moana.mtf",
  "note": "로컬 미터 좌표(북=+y, 동=+x). origin은 yewon_test 지형점 9개의 중심. 좌표는 시나리오 교전 사거리 제약에서 역산했다(설계 스펙 §3.5). scale을 0.71 미만으로 낮추면 M109 최소사거리 2km가 깨져 G0가 잡는다.",
  "origin": { "lat": 21.386, "lon": -157.742 },
  "bearing_deg": 0.0,
  "scale": 1.0,
  "default_alt": 0.0,
  "locations": {
    "LOC_적후방보급집결지":     { "x": -1500, "y": 3400 },
    "LOC_북측관측소":          { "x": 1400,  "y": 2900 },
    "LOC_적포병진지":          { "x": 200,   "y": 2800 },
    "LOC_적북측지휘소":        { "x": 900,   "y": 2600 },
    "LOC_적북측집결지":        { "x": -200,  "y": 2400 },
    "LOC_적박격포진지":        { "x": -900,  "y": 2400 },
    "LOC_적북측접근로":        { "x": 0,     "y": 1600 },
    "LOC_북측예비방어선":       { "x": 0,     "y": 1000 },
    "LOC_동측측방접근로":       { "x": 2200,  "y": 900 },
    "LOC_적전방방어선후방":     { "x": 0,     "y": 900 },
    "LOC_북측전방방어선":       { "x": 0,     "y": 700 },
    "LOC_중앙계곡북측":        { "x": 0,     "y": 200 },
    "LOC_중앙계곡":           { "x": 0,     "y": 100 },
    "LOC_중앙킬존":           { "x": 0,     "y": 0 },
    "LOC_남측제1방어선전방":    { "x": -100,  "y": -120 },
    "LOC_중앙킬존남측":        { "x": 0,     "y": -250 },
    "LOC_서측능선":           { "x": -1800, "y": -300 },
    "LOC_동측능선":           { "x": 1800,  "y": -300 },
    "LOC_목표A남측":          { "x": 700,   "y": -350 },
    "LOC_남측제1방어선":       { "x": 0,     "y": -500 },
    "LOC_남측제2방어선":       { "x": 0,     "y": -1000 },
    "LOC_남측고지관측소":       { "x": 1500,  "y": -1000 },
    "LOC_아군박격포진지":       { "x": -400,  "y": -2400 },
    "LOC_아군포병진지":        { "x": 200,   "y": -2800 },
    "LOC_포병진지또는방어선후방": { "x": 200,   "y": -3000 },
    "LOC_아군후방지휘소":       { "x": -300,  "y": -3400 },
    "LOC_아군후방보급집결지":    { "x": 1300,  "y": -3400 }
  },
  "static_targets": {
    "FR-FP-001": "LOC_아군포병진지",
    "FR-FP-002": "LOC_아군박격포진지",
    "FR-LN-001": "LOC_남측제1방어선",
    "EN-FP-001": "LOC_적포병진지",
    "EN-FP-002": "LOC_적박격포진지",
    "EN-RT-001": "LOC_적북측접근로",
    "OBJ-009":   "LOC_중앙킬존"
  }
}
```

- [ ] **Step 4: `vtmak/geometry.py` 구현**

`Coord` 클래스는 `VTMAK/vtmak/scnx/geometry.py:29-72`를 그대로 가져온다(검증된 ECEF 변환). `AutoPlacer`·`MapPack`·`_lcs_len`·`_anchor`·`_offset`은 가져오지 않는다 — 앵커링과 자동배치가 이 설계에서 사라졌다.

```python
"""좌표 — 로컬 미터 전장 좌표계 → WGS84 → ECEF.

선행 프로젝트는 golden에서 수확한 지형점에 지명을 이름으로 앵커링했다.
새 시나리오는 지명이 golden과 겹치지 않고 실제 거리도 반영되지 않아,
시나리오 기하를 직접 로컬 미터로 선언하는 방식으로 바꿨다.
근거는 설계 스펙 §3.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

ZERO = (0.0, 0.0, 0.0)

# WGS84 타원체 상수. .scnx의 (location X Y Z)는 ECEF geocentric 미터다.
_WGS84_A = 6378137.0
_WGS84_E2 = 6.69437999014e-3  # 이심률² = 2f - f²

# 1도당 미터. 등거리 근사 — 7km 범위에서 오차 1m 미만이다.
_M_PER_DEG_LAT = 110574.0
_M_PER_DEG_LON_EQ = 111320.0


@dataclass(frozen=True)
class Coord:
    lat: float
    lon: float
    alt: float

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.lat, self.lon, self.alt)

    def is_zero(self) -> bool:
        return self.as_tuple() == ZERO

    def to_ecef(self) -> tuple[float, float, float]:
        """WGS84 geodetic(도, m) → ECEF geocentric 미터."""
        lat, lon = math.radians(self.lat), math.radians(self.lon)
        sin_lat = math.sin(lat)
        n = _WGS84_A / math.sqrt(1.0 - _WGS84_E2 * sin_lat * sin_lat)
        x = (n + self.alt) * math.cos(lat) * math.cos(lon)
        y = (n + self.alt) * math.cos(lat) * math.sin(lon)
        z = (n * (1.0 - _WGS84_E2) + self.alt) * sin_lat
        return (x, y, z)

    @classmethod
    def from_ecef(cls, x: float, y: float, z: float) -> "Coord":
        """ECEF geocentric 미터 → WGS84 geodetic(도, m). Bowring 근사."""
        b = _WGS84_A * math.sqrt(1.0 - _WGS84_E2)
        ep2 = _WGS84_E2 / (1.0 - _WGS84_E2)
        p = math.hypot(x, y)
        if p == 0.0:  # 극점
            lat = math.copysign(math.pi / 2, z)
            return cls(math.degrees(lat), 0.0, abs(z) - b)
        th = math.atan2(z * _WGS84_A, p * b)
        lat = math.atan2(z + ep2 * b * math.sin(th) ** 3,
                         p - _WGS84_E2 * _WGS84_A * math.cos(th) ** 3)
        lon = math.atan2(y, x)
        n = _WGS84_A / math.sqrt(1.0 - _WGS84_E2 * math.sin(lat) ** 2)
        alt = p / math.cos(lat) - n
        return cls(math.degrees(lat), math.degrees(lon), alt)


def ground_distance(a: Coord, b: Coord) -> float:
    """두 좌표 사이 지표 거리(m). 사거리 판정의 유일한 거리 함수."""
    r = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(h))


class BattlefieldLayout:
    """지명 → 좌표. 로컬 미터로 선언하고 origin 기준으로 투영한다.

    없는 지명은 예외 대신 ZERO를 돌려준다. 커버리지 리포트가 한 곳(G0/G3)에서
    나와야 어떤 지명이 비었는지 한 번에 보이기 때문이다.
    """

    def __init__(self, data: dict) -> None:
        self.layout_id: str = data.get("layout_id", "")
        self.terrain: str = data.get("terrain", "")
        self.origin_lat: float = data["origin"]["lat"]
        self.origin_lon: float = data["origin"]["lon"]
        self.bearing_deg: float = float(data.get("bearing_deg", 0.0))
        self.scale: float = float(data.get("scale", 1.0))
        self.default_alt: float = float(data.get("default_alt", 0.0))
        self._local: dict[str, tuple[float, float]] = {
            k: (float(v["x"]), float(v["y"]))
            for k, v in (data.get("locations") or {}).items()
        }
        self._static: dict[str, str] = dict(data.get("static_targets") or {})

    @classmethod
    def load(cls, path) -> "BattlefieldLayout":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def location_ids(self) -> list[str]:
        return sorted(self._local)

    def local(self, location_id: str) -> tuple[float, float] | None:
        return self._local.get(location_id)

    def static_target(self, object_id: str) -> str | None:
        """정적 객체(포병진지·킬존 등) → 바인딩된 지명. 없으면 None."""
        return self._static.get(object_id)

    def static_ids(self) -> set[str]:
        """엔티티로 만들지 않는 정적 객체 id 집합."""
        return set(self._static)

    def coord(self, location_id: str) -> Coord:
        xy = self._local.get(location_id)
        if xy is None:
            return Coord(*ZERO)
        return self._project(xy[0] * self.scale, xy[1] * self.scale)

    def offset_coord(self, location_id: str, dx: float, dy: float) -> Coord:
        """지명 기준 로컬 오프셋 좌표. jitter가 쓴다."""
        xy = self._local.get(location_id)
        if xy is None:
            return Coord(*ZERO)
        return self._project(xy[0] * self.scale + dx, xy[1] * self.scale + dy)

    def distance_m(self, a_id: str, b_id: str) -> float:
        return ground_distance(self.coord(a_id), self.coord(b_id))

    def _project(self, x: float, y: float) -> Coord:
        """로컬 미터 → WGS84. bearing_deg는 +y축이 진북에서 시계방향으로
        돌아간 각도다(0이면 +y = 정북)."""
        b = math.radians(self.bearing_deg)
        east = x * math.cos(b) + y * math.sin(b)
        north = -x * math.sin(b) + y * math.cos(b)
        lat = self.origin_lat + north / _M_PER_DEG_LAT
        lon = self.origin_lon + east / (
            _M_PER_DEG_LON_EQ * max(0.1, math.cos(math.radians(self.origin_lat))))
        return Coord(lat, lon, self.default_alt)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_geometry.py -v`
Expected: PASS (9 passed)

- [ ] **Step 6: 커밋**

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments"
git add new_VTMAK/vtmak/geometry.py new_VTMAK/config/battlefield_layout.json new_VTMAK/tests/test_geometry.py
git commit -m "feat(new_vtmak): 로컬 미터 전장 좌표계와 지명 27개 레이아웃"
```

---

### Task 3: 사거리 표와 판정

**Files:**
- Create: `new_VTMAK/config/weapon_ranges.csv`
- Create: `new_VTMAK/vtmak/ranges.py`
- Test: `new_VTMAK/tests/test_ranges.py`

**Interfaces:**
- Consumes: `vtmak.norm.norm`, `vtmak.geometry.Coord`, `vtmak.geometry.ground_distance`
- Produces:
  - `RangeSpec(min_m: float | None, max_m: float | None)` — `min_m`/`max_m`가 둘 다 `None`이면 미확인 무기체계
  - `WeaponRanges.load(path) -> WeaponRanges`
  - `WeaponRanges.spec(entity_class: str, fire_kind: str) -> RangeSpec | None` — `fire_kind`는 `"direct"` 또는 `"indirect"`. 사격 능력이 없으면 `None`
  - `WeaponRanges.check(entity_class, fire_kind, distance_m) -> str` — `"OK"` / `"TOO_CLOSE"` / `"TOO_FAR"` / `"NO_WEAPON"` / `"UNVERIFIED"`
  - `WeaponRanges.classes() -> list[str]` (원문 표기 그대로)

- [ ] **Step 1: 실패하는 테스트 작성**

`new_VTMAK/tests/test_ranges.py`:

```python
from pathlib import Path

import pytest

from vtmak.ranges import WeaponRanges

CONFIG = Path(__file__).resolve().parents[1] / "config" / "weapon_ranges.csv"


@pytest.fixture(scope="module")
def wr():
    return WeaponRanges.load(CONFIG)


def test_covers_all_26_scenario_models(wr):
    assert len(wr.classes()) == 26


def test_hyphen_variants_resolve(wr):
    # 원문은 'T-72 MBT', dis_catalog는 'T 72 MBT'.
    assert wr.spec("T 72 MBT", "direct") is not None
    assert wr.spec("T-72 MBT", "direct") is not None


def test_rifle_direct_limits(wr):
    assert wr.check("US Army M4", "direct", 250.0) == "OK"
    assert wr.check("US Army M4", "direct", 700.0) == "TOO_FAR"
    assert wr.check("Russian Soldier AK47", "direct", 335.0) == "OK"
    assert wr.check("Russian Soldier AK47", "direct", 450.0) == "TOO_FAR"


def test_howitzer_minimum_range(wr):
    assert wr.check("M109 Howitzer", "indirect", 1500.0) == "TOO_CLOSE"
    assert wr.check("M109 Howitzer", "indirect", 2807.0) == "OK"
    assert wr.check("M109 Howitzer", "indirect", 20000.0) == "TOO_FAR"


def test_mortar_window(wr):
    assert wr.check("MO-120RT-61 Mortar", "indirect", 900.0) == "TOO_CLOSE"
    assert wr.check("MO-120RT-61 Mortar", "indirect", 2433.0) == "OK"
    assert wr.check("MO-120RT-61 Mortar", "indirect", 9000.0) == "TOO_FAR"


def test_truck_has_no_weapon(wr):
    assert wr.check("M35 Truck", "direct", 100.0) == "NO_WEAPON"
    assert wr.spec("M35 Truck", "direct") is None


def test_patriot_launchers_are_unverified(wr):
    # 설계 스펙 §8.3 — VR-Forces에서 Patriot의 지상 간접사격이 성립하는지
    # 확인되지 않았다. 조용히 통과시키지 않고 별도로 표시한다.
    assert wr.check("M901 Patriot Launcher", "indirect", 4405.0) == "UNVERIFIED"
    assert wr.check("MIM-104 Patriot Launcher", "indirect", 3306.0) == "UNVERIFIED"


def test_unknown_class_is_no_weapon(wr):
    assert wr.check("Imaginary Tank", "direct", 100.0) == "NO_WEAPON"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_ranges.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtmak.ranges'`

- [ ] **Step 3: `config/weapon_ranges.csv` 작성**

빈 칸은 "해당 사격 능력 없음". `unverified` 열이 `1`이면 사거리 값이 있어도 판정을 `UNVERIFIED`로 돌린다.

```csv
entity_class,direct_min_m,direct_max_m,indirect_min_m,indirect_max_m,unverified,note
US Army M4,0,500,,,0,M4 소총 유효사거리
Russian Soldier AK47,0,400,,,0,AK47 유효사거리
Russian Soldier SA7,0,500,,,0,MANPADS. 시나리오에서 사격하지 않음
Russian Soldier Sniper-127,0,1800,,,0,대물저격총
US Army XM107,0,1800,,,0,대물저격총
Turkish Soldier RPG,0,500,,,0,휴대용 RPG
US Army Javelin,65,2500,,,0,대전차 미사일 최소사거리 있음
T-69 MBT,0,2500,,,0,전차 주포 직접사격
T-72 MBT,0,2500,,,0,전차 주포 직접사격
T-80 MBT,0,2500,,,0,전차 주포 직접사격
M1A2 Abrams MBT,0,3000,,,0,전차 주포 직접사격
BTR-60 APC,0,1500,,,0,차재 기관총
BTR-80 APC,0,1500,,,0,차재 기관총
LAV III APC,0,1800,,,0,차재 기관총
M113 APC,0,1800,,,0,M2HB 기관총
ZPU-4 AA Gun,0,1400,,,0,대공기관포
GAZ-66 Truck,,,,,0,비무장 수송
M35 Truck,,,,,0,비무장 수송
M1028 FMTV Canvas Cargo Truck,,,,,0,비무장 수송
M1083A1 FMTV Flatbed Truck,,,,,0,비무장 수송
MO-120RT-61 Mortar,,,1100,8100,0,120mm 박격포
M109 Howitzer,,,2000,18000,0,155mm 자주포
AHS Krab Howitzer,,,2000,40000,0,155mm 자주포
CAESAR SP Howitzer,,,2000,42000,0,155mm 자주포
M901 Patriot Launcher,,,,,1,지상 간접사격 성립 여부 미확인 (설계 스펙 §8.3)
MIM-104 Patriot Launcher,,,,,1,지상 간접사격 성립 여부 미확인 (설계 스펙 §8.3)
```

- [ ] **Step 4: `vtmak/ranges.py` 구현**

```python
"""무기 사거리 표와 판정.

선행 프로젝트는 사거리 미달 간접사격을 조용히 스킵했다. 그 결과 '의도한
스킵'과 '레이아웃이 잘못됨'이 구분되지 않았다. 여기서는 판정 결과를
문자열로 돌려주고, 판단은 G0가 한다.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .norm import norm

OK = "OK"
TOO_CLOSE = "TOO_CLOSE"
TOO_FAR = "TOO_FAR"
NO_WEAPON = "NO_WEAPON"
UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class RangeSpec:
    min_m: float
    max_m: float


def _num(s: str) -> float | None:
    s = (s or "").strip()
    if not s:
        return None
    return float(s)


class WeaponRanges:
    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], RangeSpec] = {}
        self._unverified: set[str] = set()
        self._classes: list[str] = []

    @classmethod
    def load(cls, path) -> "WeaponRanges":
        wr = cls()
        with open(Path(path), encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                ecls = row["entity_class"].strip()
                if not ecls:
                    continue
                wr._classes.append(ecls)
                key = norm(ecls)
                if (row.get("unverified") or "").strip() == "1":
                    wr._unverified.add(key)
                for kind, lo_col, hi_col in (
                    ("direct", "direct_min_m", "direct_max_m"),
                    ("indirect", "indirect_min_m", "indirect_max_m"),
                ):
                    lo, hi = _num(row.get(lo_col)), _num(row.get(hi_col))
                    if lo is not None and hi is not None:
                        wr._by_key[(key, kind)] = RangeSpec(lo, hi)
        return wr

    def classes(self) -> list[str]:
        return list(self._classes)

    def spec(self, entity_class: str, fire_kind: str) -> RangeSpec | None:
        return self._by_key.get((norm(entity_class), fire_kind))

    def check(self, entity_class: str, fire_kind: str,
              distance_m: float) -> str:
        key = norm(entity_class)
        if key in self._unverified:
            return UNVERIFIED
        rs = self._by_key.get((key, fire_kind))
        if rs is None:
            return NO_WEAPON
        if distance_m < rs.min_m:
            return TOO_CLOSE
        if distance_m > rs.max_m:
            return TOO_FAR
        return OK
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_ranges.py -v`
Expected: PASS (8 passed)

- [ ] **Step 6: 커밋**

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments"
git add new_VTMAK/config/weapon_ranges.csv new_VTMAK/vtmak/ranges.py new_VTMAK/tests/test_ranges.py
git commit -m "feat(new_vtmak): 무기 사거리 표와 판정 (미확인 무기체계 별도 표시)"
```

---

### Task 4: 템플릿 파서

**Files:**
- Create: `new_VTMAK/config/pattern_map.csv`
- Create: `new_VTMAK/vtmak/parser.py`
- Test: `new_VTMAK/tests/test_parser.py`

**Interfaces:**
- Consumes: `vtmak.norm.loc_id`
- Produces:
  - `Event` 데이터클래스 — 필드: `event_id: str`, `time_s: int`, `line_no: int`, `predicate: str`, `template: str`, `actor: str`, `actor_class: str`, `actor_role: str`, `location: str`, `src: str`, `dst: str`, `target: str`, `target_class: str`, `target_role: str`, `source_obj: str`, `source_class: str`, `action_label: str`, `state_from: str`, `state_to: str`, `source_line: str`. `.to_json() -> dict`

`target_class`/`target_role`이 필요한 이유: 정적 객체 7개(`EN-FP-001` 등)는 사격 **목표로만** 등장한다. 그 모델명과 역할("적 자주포 사격진지")은 목표 언급에서만 나오므로, 여기서 잡지 않으면 Task 5의 레지스트리가 이들의 역할을 채울 수 없다.
  - `ParseResult` — `.events: list[Event]`, `.unmatched: list[tuple[int, str]]`, `.sentence_count: int`
  - `parse_scenario(text: str, pattern_map: PatternMap) -> ParseResult`
  - `PatternMap.load(path) -> PatternMap`, `.predicate(template: str, action_label: str = "") -> str`, `.task_kind(template: str, action_label: str = "") -> str`
  - `KNOWN_TRUNCATION: str` — 원문 마지막 절단 조각을 식별하는 상수 `"**M1028"`

**중요 — 템플릿 순서:** `moveTo` 정규식이 `directFireAt`/`aimAt`/`indirectFireAt` 문장을 삼킨다(`…을/를 향해 X을 수행한다` 형태가 같다). 사격 템플릿을 **반드시 먼저** 시도해야 한다. `TEMPLATES` 리스트 순서가 곧 우선순위다.

- [ ] **Step 1: 실패하는 테스트 작성**

`new_VTMAK/tests/test_parser.py`:

```python
from pathlib import Path

import pytest

from vtmak.parser import PatternMap, parse_scenario

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scenario_original" / "scenario_v3.txt"
PMAP = ROOT / "config" / "pattern_map.csv"


@pytest.fixture(scope="module")
def result():
    pm = PatternMap.load(PMAP)
    return parse_scenario(SRC.read_text(encoding="utf-8"), pm)


def test_matches_every_sentence_but_the_known_truncation(result):
    # 원문 PDF가 마지막 문장에서 끊겨 있다(변환 손실 아님).
    assert result.sentence_count == 3000
    assert len(result.unmatched) == 1
    line_no, frag = result.unmatched[0]
    assert line_no == 1295
    assert frag.startswith("**M1028")


def test_template_counts(result):
    from collections import Counter
    c = Counter(e.template for e in result.events)
    assert c["stateChange"] == 821
    assert c["moveTo"] == 571
    assert c["locatedAt"] == 328
    assert c["stateInit"] == 294
    assert c["stateHold"] == 178
    assert c["stopAt"] == 102
    assert c["directFireAt"] == 77
    assert c["hitBy"] == 77
    assert c["stayAt"] == 77
    assert c["aimAt"] == 21
    assert c["indirectFireAt"] == 21
    assert c["hitArea"] == 21


def test_fire_templates_are_not_swallowed_by_moveto(result):
    # moveTo 정규식이 '…을/를 향해 직접사격을 수행한다'도 매칭한다.
    # 사격 템플릿이 먼저 시도되지 않으면 이 테스트가 깨진다.
    fires = [e for e in result.events if e.template == "directFireAt"]
    assert len(fires) == 77
    assert all(e.target and e.target.startswith(("FR-", "EN-", "OBJ-"))
               for e in fires)
    assert all(not e.action_label for e in fires)


def test_actor_ids_are_explicit_not_inferred(result):
    e = next(e for e in result.events if e.template == "locatedAt")
    assert e.actor == "FR-INF-001"
    assert e.actor_class == "US Army M4"
    assert e.actor_role == "방어 보병 1"
    assert e.location == "LOC_남측제1방어선"
    assert e.time_s == 0


def test_second_mention_without_role_still_resolves(result):
    # '**US Army M4(FR-INF-001)**의 초기 상태는 …' — 역할이 빠진 2차 언급.
    inits = [e for e in result.events if e.template == "stateInit"]
    assert len(inits) == 294
    assert inits[0].actor == "FR-INF-001"
    assert inits[0].state_to == "대기"


def test_move_actions_map_to_distinct_predicates(result):
    by = {}
    for e in result.events:
        if e.template == "moveTo":
            by.setdefault(e.action_label, set()).add(e.predicate)
    assert by["후퇴 이동"] == {"retreatTo"}
    assert by["방어선 재편성 이동"] == {"defend"}
    assert by["공격 대형 이동"] == {"approach"}
    assert by["지상 이동"] == {"moveTo"}
    assert by["보급 이동 및 정차"] == {"transportTo"}


def test_locations_are_normalised_to_loc_ids(result):
    locs = {e.location for e in result.events if e.location}
    locs |= {e.src for e in result.events if e.src}
    locs |= {e.dst for e in result.events if e.dst}
    assert len(locs) == 27
    assert all(l.startswith("LOC_") for l in locs)
    assert "LOC_남측제1방어선" in locs
    assert "LOC_동측측방접근로" in locs


def test_time_range(result):
    times = [e.time_s for e in result.events]
    assert min(times) == 0
    assert max(times) == 6 * 60 + 56


def test_event_ids_are_unique_and_deterministic(result):
    ids = [e.event_id for e in result.events]
    assert len(ids) == len(set(ids))
    pm = PatternMap.load(PMAP)
    again = parse_scenario(SRC.read_text(encoding="utf-8"), pm)
    assert [e.event_id for e in again.events] == ids
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtmak.parser'`

- [ ] **Step 3: `config/pattern_map.csv` 작성**

```csv
key,kind,predicate,task_kind,note
locatedAt,template,locatedAt,noop,초기 배치로 흡수
moveTo,template,moveTo,move,행동별로 술어가 갈린다 (아래 move_action 행)
stopAt,template,stopAt,noop,정지 — wait task 없음
stayAt,template,occupy,noop,피격 후 잔류
directFireAt,template,directFireAt,fire_direct,
aimAt,template,aimAt,aim,포신 정렬
indirectFireAt,template,indirectFireAt,fire_indirect,
hitBy,template,hitBy,noop,피격 — 결과 상태로 표현
hitArea,template,hitArea,noop,주변 탄착
targetArea,template,hitArea,noop,직전 탄착 이벤트의 대상 구역
stateInit,template,stateChangedTo,noop,
stateChange,template,stateChangedTo,noop,
stateHold,template,stateChangedTo,noop,
noTask,template,noTask,noop,이후 이동·사격 task 금지 플래그
engAttacker,template,engagementPair,noop,교전기록 — 공격자/목표 확정
engSource,template,engagementSource,noop,교전기록 — 피격 원천 확정
후퇴 이동,move_action,retreatTo,move,
방어선 재편성 이동,move_action,defend,move,
공격 대형 이동,move_action,approach,move,
지상 이동,move_action,moveTo,move,
방어 위치 이동,move_action,defend,move,
감시 위치 이동 및 관측 방향 유지,move_action,moveTo,move,
보급 이동 및 정차,move_action,transportTo,move,
```

- [ ] **Step 4: `vtmak/parser.py` 구현**

```python
"""원문 → 이벤트. 문법 분석 없이 문장 템플릿을 fullmatch한다.

원문은 기계 생성 텍스트라 문장 템플릿이 유한하다(3,000문장 / 21 템플릿).
객체 ID가 문장에 명시되어 있어(**US Army M4(FR-INF-001, 방어 보병 1)**)
행위자·대상 판정이 추측이 아니다. 선행 프로젝트가 조사로 역할을 추측하다
겪은 '행위자와 대상이 뒤바뀜' 문제가 여기서는 발생하지 않는다.
"""
from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .norm import loc_id

# 원문 PDF가 마지막 문장에서 끊겨 있다(변환 손실 아님). 조용히 버리지 않고
# 선언된 예외로 둔다.
KNOWN_TRUNCATION = "**M1028"


def _ent(model: str, ident: str) -> str:
    """**모델명(ID, 역할)** 또는 **모델명(ID)** — 2차 언급엔 역할이 없다."""
    return (r"\*\*(?P<" + model + r">[^*(]+?)\("
            r"(?P<" + ident + r">[A-Z][A-Z0-9\-]+)"
            r"(?:,\s*(?P<" + ident + r"_role>[^)]*?))?\)\*\*")


_T = r"(?P<t>\d\d):(?P<s>\d\d)에 "
_L = r"[^*]+?"          # 지명 — 엔티티 마크업(**)을 넘지 않는다
_S = r"[^*]+?"          # 상태

# 순서가 우선순위다. moveTo가 사격 문장을 삼키므로 사격을 먼저 둔다.
TEMPLATES: list[tuple[str, str]] = [
    ("directFireAt",
     _T + _ent("m", "a") + r"은/는 (?P<src>" + _L + r")에서 "
     + _ent("tm", "tgt") + r"을/를 향해 직접사격을 수행한다"),
    ("aimAt",
     _T + _ent("m", "a") + r"은/는 (?P<src>" + _L + r")에서 "
     + _ent("tm", "tgt") + r"을/를 향해 포신 정렬 후 간접사격 준비을 수행한다"),
    ("indirectFireAt",
     _T + _ent("m", "a") + r"은/는 (?P<src>" + _L + r")에서 "
     + _ent("tm", "tgt") + r"을/를 향해 간접사격을 수행한다"),
    ("hitBy",
     _T + _ent("m", "a") + r"은/는 (?P<loc>" + _L + r")에서 "
     + _ent("sm", "srcobj") + r"의 직접사격에 피격된다"),
    ("hitArea",
     _T + _ent("m", "a") + r"은/는 " + _ent("sm", "srcobj")
     + r"의 사격으로 주변 탄착을 받는다"),
    ("moveTo",
     _T + _ent("m", "a") + r"은/는 (?P<src>" + _L + r")에서 (?P<dst>" + _L
     + r")을/를 향해 (?P<act>[^*]+?)을 수행한다"),
    ("locatedAt",
     _T + _ent("m", "a") + r"은/는 (?P<loc>" + _L + r")에 위치한다"),
    ("stopAt",
     _T + _ent("m", "a") + r"은/는 (?P<loc>" + _L + r")에 정지한다"),
    ("stayAt",
     _T + _ent("m", "a") + r"은/는 (?P<loc>" + _L + r")에 잔류한다"),
    ("targetArea", r"목표 구역은 (?P<loc>" + _L + r")이다"),
    ("stateInit",
     _ent("m", "a") + r"의 초기 상태는 (?P<s1>" + _S + r") 상태이다"),
    ("stateChange",
     _ent("m", "a") + r"은/는 (?P<s0>" + _S + r") 상태에서 (?P<s1>" + _S
     + r") 상태로 전환한다"),
    ("stateHold",
     _ent("m", "a") + r"은/는 (?P<s1>" + _S + r") 상태를 유지한다"),
    ("noTask",
     r"이후 (?P<a>[A-Z][A-Z0-9\-]+)에는 일반 이동·사격 task를 부여하지 않는다"),
    ("engAttacker",
     r"공격자 객체는 (?P<a>[A-Z][A-Z0-9\-]+)이고, "
     r"목표 객체는 (?P<tgt>[A-Z][A-Z0-9\-]+)이다"),
    ("engSource",
     r"피격 원천 객체는 (?P<srcobj>[A-Z][A-Z0-9\-]+)이고, "
     r"피격 대상 객체는 (?P<a>[A-Z][A-Z0-9\-]+)이다"),
]

_COMPILED = [(name, re.compile(pat)) for name, pat in TEMPLATES]


@dataclass
class Event:
    event_id: str
    time_s: int
    line_no: int
    predicate: str
    template: str
    actor: str = ""
    actor_class: str = ""
    actor_role: str = ""
    location: str = ""
    src: str = ""
    dst: str = ""
    target: str = ""
    target_class: str = ""
    target_role: str = ""
    source_obj: str = ""
    source_class: str = ""
    action_label: str = ""
    state_from: str = ""
    state_to: str = ""
    source_line: str = ""

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class ParseResult:
    events: list[Event] = field(default_factory=list)
    unmatched: list[tuple[int, str]] = field(default_factory=list)
    sentence_count: int = 0


class PatternMap:
    def __init__(self) -> None:
        self._tmpl: dict[str, tuple[str, str]] = {}
        self._move: dict[str, tuple[str, str]] = {}

    @classmethod
    def load(cls, path) -> "PatternMap":
        pm = cls()
        with open(Path(path), encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                key, kind = row["key"].strip(), row["kind"].strip()
                val = (row["predicate"].strip(), row["task_kind"].strip())
                if kind == "template":
                    pm._tmpl[key] = val
                elif kind == "move_action":
                    pm._move[key] = val
        return pm

    def predicate(self, template: str, action_label: str = "") -> str:
        if template == "moveTo" and action_label in self._move:
            return self._move[action_label][0]
        return self._tmpl.get(template, ("", ""))[0]

    def task_kind(self, template: str, action_label: str = "") -> str:
        if template == "moveTo" and action_label in self._move:
            return self._move[action_label][1]
        return self._tmpl.get(template, ("", "noop"))[1]


def _sentences(text: str):
    """(줄번호, 문장). 원문은 한 줄에 1~3문장이 '다. '로 이어진다."""
    for line_no, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        for part in re.split(r"(?<=다)\.\s*", line):
            part = part.strip().rstrip(".")
            if part:
                yield line_no, part


def parse_scenario(text: str, pattern_map: PatternMap) -> ParseResult:
    res = ParseResult()
    seq = 0
    carry_time = 0          # 시각 없는 문장(상태 서술)은 직전 시각을 잇는다
    for line_no, sent in _sentences(text):
        res.sentence_count += 1
        for name, rx in _COMPILED:
            m = rx.fullmatch(sent)
            if not m:
                continue
            seq += 1
            g = m.groupdict()
            if g.get("t") is not None:
                carry_time = int(g["t"]) * 60 + int(g["s"])
            act = (g.get("act") or "").strip()
            ev = Event(
                event_id=f"E{seq:05d}",
                time_s=carry_time,
                line_no=line_no,
                template=name,
                predicate=pattern_map.predicate(name, act),
                actor=g.get("a") or "",
                actor_class=(g.get("m") or "").strip(),
                actor_role=(g.get("a_role") or "").strip(),
                location=loc_id(g["loc"]) if g.get("loc") else "",
                src=loc_id(g["src"]) if g.get("src") else "",
                dst=loc_id(g["dst"]) if g.get("dst") else "",
                target=g.get("tgt") or "",
                target_class=(g.get("tm") or "").strip(),
                target_role=(g.get("tgt_role") or "").strip(),
                source_obj=g.get("srcobj") or "",
                source_class=(g.get("sm") or "").strip(),
                action_label=act,
                state_from=(g.get("s0") or "").strip(),
                state_to=(g.get("s1") or "").strip(),
                source_line=sent,
            )
            res.events.append(ev)
            break
        else:
            res.unmatched.append((line_no, sent))
    return res
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_parser.py -v`
Expected: PASS (9 passed)

정규식 그룹명 충돌(`a_role`)이나 템플릿 순서 문제로 실패하면, 실패한 카운트를 실제 값과 비교해 `TEMPLATES` 순서를 먼저 의심할 것.

- [ ] **Step 6: 커밋**

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments"
git add new_VTMAK/config/pattern_map.csv new_VTMAK/vtmak/parser.py new_VTMAK/tests/test_parser.py
git commit -m "feat(new_vtmak): 템플릿 파서 (3000문장 중 2999 매칭)"
```

---

### Task 5: 레지스트리 자동 생성

**Files:**
- Create: `new_VTMAK/config/entity_class_map.csv`
- Create: `new_VTMAK/vtmak/registry.py`
- Test: `new_VTMAK/tests/test_registry.py`
- Copy: `VTMAK/config/dis_catalog.csv` → `new_VTMAK/config/dis_catalog.csv`

**Interfaces:**
- Consumes: `vtmak.parser.Event`, `vtmak.norm.norm`
- Produces:
  - `EntityDef(object_id, entity_class, role, faction, type_group, weapons: tuple[str,...], initial_location: str, initial_state: str, taskable: bool)`
  - `ClassMap.load(path) -> ClassMap`, `.type_group(entity_class) -> str`, `.weapons(entity_class) -> tuple[str,...]`, `.known(entity_class) -> bool`
  - `build_registry(events: list[Event], class_map: ClassMap, static_ids: set[str]) -> dict[str, EntityDef]` — `object_id` → `EntityDef`, 키 정렬 순
  - `collect_locations(events: list[Event]) -> list[str]` — 등장 지명 LOC_id 정렬 목록
  - `faction_of(object_id: str) -> str` — `FR-` → `BLUE`, `EN-` → `RED`, 그 외 `NEUTRAL`

- [ ] **Step 1: dis_catalog 복사**

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments"
cp "VTMAK/config/dis_catalog.csv" "new_VTMAK/config/dis_catalog.csv"
```

- [ ] **Step 2: 실패하는 테스트 작성**

`new_VTMAK/tests/test_registry.py`:

```python
from pathlib import Path

import pytest

from vtmak.geometry import BattlefieldLayout
from vtmak.parser import PatternMap, parse_scenario
from vtmak.registry import ClassMap, build_registry, collect_locations, faction_of

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scenario_original" / "scenario_v3.txt"


@pytest.fixture(scope="module")
def ctx():
    pm = PatternMap.load(ROOT / "config" / "pattern_map.csv")
    res = parse_scenario(SRC.read_text(encoding="utf-8"), pm)
    lay = BattlefieldLayout.load(ROOT / "config" / "battlefield_layout.json")
    cm = ClassMap.load(ROOT / "config" / "entity_class_map.csv")
    static = {oid for oid in
              ["FR-FP-001", "FR-FP-002", "FR-LN-001", "EN-FP-001",
               "EN-FP-002", "EN-RT-001", "OBJ-009"]}
    return res, cm, lay, build_registry(res.events, cm, static)


def test_registry_has_335_objects(ctx):
    _, _, _, reg = ctx
    assert len(reg) == 335


def test_taskable_split_matches_scenario(ctx):
    _, _, _, reg = ctx
    taskable = [e for e in reg.values() if e.taskable]
    static = [e for e in reg.values() if not e.taskable]
    assert len(taskable) == 328
    assert len(static) == 7


def test_faction_from_id_prefix():
    assert faction_of("FR-INF-001") == "BLUE"
    assert faction_of("EN-T72-001") == "RED"
    assert faction_of("OBJ-009") == "NEUTRAL"


def test_every_taskable_class_is_known_to_class_map(ctx):
    _, cm, _, reg = ctx
    unknown = sorted({e.entity_class for e in reg.values()
                      if e.taskable and not cm.known(e.entity_class)})
    assert unknown == []


def test_class_map_covers_26_models(ctx):
    _, cm, _, reg = ctx
    classes = {e.entity_class for e in reg.values() if e.taskable}
    assert len(classes) == 26


def test_initial_location_and_state_captured(ctx):
    _, _, _, reg = ctx
    e = reg["FR-INF-001"]
    assert e.entity_class == "US Army M4"
    assert e.role == "방어 보병 1"
    assert e.initial_location == "LOC_남측제1방어선"
    assert e.initial_state == "대기"
    assert e.type_group == "보병 - 소총(M4 계열)"
    assert "M4 rifle" in e.weapons


def test_new_models_have_type_groups(ctx):
    _, _, _, reg = ctx
    assert reg["EN-M1A2-001"].type_group == "차량/장갑차 - M2HB 계열"
    assert reg["EN-SA7-001"].type_group == "보병 - RPG 계열"


def test_static_objects_have_no_class_but_keep_role(ctx):
    _, _, _, reg = ctx
    e = reg["EN-FP-001"]
    assert e.taskable is False
    assert e.role == "적 자주포 사격진지"


def test_all_27_locations_resolve_in_layout(ctx):
    res, _, lay, _ = ctx
    missing = [l for l in collect_locations(res.events) if lay.local(l) is None]
    assert missing == []


def test_registry_is_deterministic(ctx):
    res, cm, _, reg = ctx
    again = build_registry(res.events, cm, set(reg) - {o for o, e in reg.items()
                                                      if e.taskable})
    assert list(reg) == list(again)
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtmak.registry'`

- [ ] **Step 4: `config/entity_class_map.csv` 작성**

`type_group` 값은 `task_catalog.csv`의 `객체_타입_그룹` 컬럼과 **정확히 일치**해야 한다(템플릿 조회 키). 23종은 `VTMAK/config/entity_registry.csv`에서 확인된 값이고, M1A2·MIM-104·SA7 3종이 신규다.

```csv
entity_class,type_group,weapons,note
US Army M4,보병 - 소총(M4 계열),M4 rifle,
Russian Soldier AK47,보병 - 소총(M4 계열),M4 rifle,golden에서 AK47 무기명이 M4 rifle로 노출됨
Russian Soldier Sniper-127,보병 - 소총(M4 계열),M4 rifle,
US Army XM107,보병 - 소총(M4 계열),M4 rifle,
Turkish Soldier RPG,보병 - RPG 계열,Handheld RPG Launcher,
US Army Javelin,보병 - RPG 계열,Handheld RPG Launcher,
Russian Soldier SA7,보병 - RPG 계열,Handheld RPG Launcher,신규 — MANPADS를 휴대 발사기로 취급
T-69 MBT,차량/장갑차 - M2HB 계열,M2HB Machine Gun,
T-72 MBT,차량/장갑차 - M2HB 계열,M2HB Machine Gun,
T-80 MBT,차량/장갑차 - M2HB 계열,M2HB Machine Gun,
M1A2 Abrams MBT,차량/장갑차 - M2HB 계열,M2HB Machine Gun,신규
BTR-60 APC,차량/장갑차 - M2HB 계열,M2HB Machine Gun,
BTR-80 APC,차량/장갑차 - M2HB 계열,M2HB Machine Gun,
LAV III APC,차량/장갑차 - M2HB 계열,M2HB Machine Gun,
M113 APC,차량/장갑차 - M2HB 계열,M2HB Machine Gun,
ZPU-4 AA Gun,차량/장갑차 - M2HB 계열,M2HB Machine Gun,
GAZ-66 Truck,차량/장갑차 - M2HB 계열,,비무장
M35 Truck,차량/장갑차 - M2HB 계열,,비무장
M1028 FMTV Canvas Cargo Truck,차량/장갑차 - M2HB 계열,,비무장
M1083A1 FMTV Flatbed Truck,차량/장갑차 - M2HB 계열,,비무장
MO-120RT-61 Mortar,포병 - 박격포(m9333he 계열),Indirect-Fire-Gun:m9333he,
M109 Howitzer,포병 - 155mm 자주포,Indirect-Fire-Gun:M107-155mm,
AHS Krab Howitzer,포병 - 155mm 자주포,Indirect-Fire-Gun:M107-155mm,
CAESAR SP Howitzer,포병 - 155mm 자주포,Indirect-Fire-Gun:M107-155mm,
M901 Patriot Launcher,미분류,,무기체계 미확정 (설계 스펙 §8.3)
MIM-104 Patriot Launcher,미분류,,무기체계 미확정 (설계 스펙 §8.3)
```

- [ ] **Step 5: `vtmak/registry.py` 구현**

```python
"""이벤트 → 객체 사전.

선행 프로젝트는 원문에서 후보를 채굴해 사람이 CSV를 검토했다. 새 원문은
객체 ID·모델명·역할이 문장에 명시되어 있어 그 단계가 필요 없다.
사람이 관리하는 것은 entity_class → type_group 매핑뿐이다.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .norm import norm
from .parser import Event


def faction_of(object_id: str) -> str:
    """ID 접두사가 소속을 결정한다. FR- 아군, EN- 적군, 그 외 중립."""
    if object_id.startswith("FR-"):
        return "BLUE"
    if object_id.startswith("EN-"):
        return "RED"
    return "NEUTRAL"


@dataclass(frozen=True)
class EntityDef:
    object_id: str
    entity_class: str
    role: str
    faction: str
    type_group: str
    weapons: tuple[str, ...]
    initial_location: str
    initial_state: str
    taskable: bool


class ClassMap:
    def __init__(self) -> None:
        self._tg: dict[str, str] = {}
        self._w: dict[str, tuple[str, ...]] = {}

    @classmethod
    def load(cls, path) -> "ClassMap":
        cm = cls()
        with open(Path(path), encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                ecls = (row["entity_class"] or "").strip()
                if not ecls:
                    continue
                key = norm(ecls)
                cm._tg[key] = (row["type_group"] or "").strip()
                cm._w[key] = tuple(
                    w for w in (row.get("weapons") or "").split("|") if w.strip())
        return cm

    def known(self, entity_class: str) -> bool:
        return norm(entity_class) in self._tg

    def type_group(self, entity_class: str) -> str:
        return self._tg.get(norm(entity_class), "미분류")

    def weapons(self, entity_class: str) -> tuple[str, ...]:
        return self._w.get(norm(entity_class), ())


def collect_locations(events: list[Event]) -> list[str]:
    out: set[str] = set()
    for e in events:
        for v in (e.location, e.src, e.dst):
            if v:
                out.add(v)
    return sorted(out)


def build_registry(events: list[Event], class_map: ClassMap,
                   static_ids: set[str]) -> dict[str, EntityDef]:
    """등장 객체 전부를 사전으로. 시간순으로 처음 본 값을 채택한다."""
    cls_by_id: dict[str, str] = {}
    role_by_id: dict[str, str] = {}
    loc_by_id: dict[str, str] = {}
    state_by_id: dict[str, str] = {}

    for e in sorted(events, key=lambda x: (x.time_s, x.event_id)):
        for oid, ecls, role in _mentions(e):
            if not oid:
                continue
            # 2차 언급에는 역할이 없다. 처음 본 비어있지 않은 값을 남긴다.
            if ecls and oid not in cls_by_id:
                cls_by_id[oid] = ecls
            if role and oid not in role_by_id:
                role_by_id[oid] = role
        if e.actor:
            if e.template == "locatedAt" and e.location:
                loc_by_id.setdefault(e.actor, e.location)
            if e.template == "stateInit" and e.state_to:
                state_by_id.setdefault(e.actor, e.state_to)
            elif e.template == "stateChange" and e.state_from:
                state_by_id.setdefault(e.actor, e.state_from)

    out: dict[str, EntityDef] = {}
    for oid in sorted(set(cls_by_id) | set(role_by_id)):
        ecls = cls_by_id.get(oid, "")
        taskable = oid not in static_ids
        out[oid] = EntityDef(
            object_id=oid,
            entity_class=ecls,
            role=role_by_id.get(oid, ""),
            faction=faction_of(oid),
            type_group=class_map.type_group(ecls) if taskable else "정적",
            weapons=class_map.weapons(ecls) if taskable else (),
            initial_location=loc_by_id.get(oid, ""),
            initial_state=state_by_id.get(oid, "대기"),
            taskable=taskable,
        )
    return out


def _mentions(e: Event):
    """이벤트가 담고 있는 (객체id, 모델명, 역할) 언급 전부.

    정적 객체 7개는 사격 목표로만 등장하므로 target 쪽 언급이 유일한
    모델명·역할 출처다.
    """
    yield (e.actor, e.actor_class, e.actor_role)
    if e.target:
        yield (e.target, e.target_class, e.target_role)
    if e.source_obj:
        yield (e.source_obj, e.source_class, "")
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_registry.py tests/test_parser.py -v`
Expected: PASS (전체)

- [ ] **Step 7: 커밋**

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments"
git add new_VTMAK/config/entity_class_map.csv new_VTMAK/config/dis_catalog.csv new_VTMAK/vtmak/registry.py new_VTMAK/vtmak/parser.py new_VTMAK/tests/test_registry.py
git commit -m "feat(new_vtmak): 원문에서 객체 사전 자동 생성 (335객체, 수작업 사전 폐기)"
```

---

### Task 6: 게이트 G0·G1과 이벤트 스크립트

**Files:**
- Create: `new_VTMAK/vtmak/gates.py`
- Create: `new_VTMAK/scripts/02_parse_events.py`
- Test: `new_VTMAK/tests/test_gates.py`

**Interfaces:**
- Consumes: `vtmak.parser.ParseResult`, `vtmak.registry.EntityDef`, `vtmak.geometry.BattlefieldLayout`, `vtmak.ranges.WeaponRanges`
- Produces:
  - `Violation(gate: str, code: str, detail: str)` (frozen dataclass)
  - `check_g1(result: ParseResult, layout: BattlefieldLayout, registry: dict[str, EntityDef]) -> list[Violation]`
  - `engagement_pairs(events, registry, layout) -> list[tuple[str, str, str, float]]` — `(attacker_id, fire_kind, detail, distance_m)`
  - `check_g0(events, registry, layout, ranges) -> list[Violation]`

- [ ] **Step 1: 실패하는 테스트 작성**

`new_VTMAK/tests/test_gates.py`:

```python
from pathlib import Path

import pytest

from vtmak.gates import check_g0, check_g1, engagement_pairs
from vtmak.geometry import BattlefieldLayout
from vtmak.parser import PatternMap, parse_scenario
from vtmak.ranges import WeaponRanges
from vtmak.registry import ClassMap, build_registry

ROOT = Path(__file__).resolve().parents[1]
STATIC = {"FR-FP-001", "FR-FP-002", "FR-LN-001",
          "EN-FP-001", "EN-FP-002", "EN-RT-001", "OBJ-009"}


@pytest.fixture(scope="module")
def env():
    pm = PatternMap.load(ROOT / "config" / "pattern_map.csv")
    res = parse_scenario(
        (ROOT / "scenario_original" / "scenario_v3.txt").read_text(encoding="utf-8"), pm)
    lay = BattlefieldLayout.load(ROOT / "config" / "battlefield_layout.json")
    cm = ClassMap.load(ROOT / "config" / "entity_class_map.csv")
    wr = WeaponRanges.load(ROOT / "config" / "weapon_ranges.csv")
    reg = build_registry(res.events, cm, STATIC)
    return res, lay, cm, wr, reg


def test_g1_passes_on_real_scenario(env):
    res, lay, _, _, reg = env
    v = check_g1(res, lay, reg)
    assert v == [], [x.detail for x in v]


def test_g1_reports_unmatched_beyond_known_truncation(env):
    res, lay, _, _, reg = env
    res.unmatched.append((999, "이건 매칭 안 되는 문장이다"))
    v = check_g1(res, lay, reg)
    res.unmatched.pop()
    assert any(x.code == "C1.1" for x in v)


def test_g1_reports_location_missing_from_layout(env):
    res, lay, _, _, reg = env
    removed = lay._local.pop("LOC_동측측방접근로")
    v = check_g1(res, lay, reg)
    lay._local["LOC_동측측방접근로"] = removed
    assert any(x.code == "C1.2" and "동측측방접근로" in x.detail for x in v)


def test_engagement_pairs_extracted(env):
    res, lay, _, _, reg = env
    pairs = engagement_pairs(res.events, reg, lay)
    kinds = {k for _, k, _, _ in pairs}
    assert kinds == {"direct", "indirect"}
    assert len(pairs) >= 90   # 직접 77 + 간접 21 (aim 포함 시 더 많음)


def test_g0_passes_on_designed_layout(env):
    res, lay, _, wr, reg = env
    v = check_g0(res.events, reg, lay, wr)
    hard = [x for x in v if x.code in ("C0.1", "C0.2")]
    assert hard == [], [x.detail for x in hard]


def test_g0_reports_unverified_patriots_separately(env):
    res, lay, _, wr, reg = env
    v = check_g0(res.events, reg, lay, wr)
    assert any(x.code == "C0.3" for x in v)
    assert all(x.code != "C0.1" for x in v if "Patriot" in x.detail)


def test_g0_catches_shrunk_layout(env):
    res, lay, _, wr, reg = env
    lay.scale = 0.5          # M109 최소사거리 2km가 깨진다
    v = check_g0(res.events, reg, lay, wr)
    lay.scale = 1.0
    assert any(x.code == "C0.1" for x in v)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_gates.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtmak.gates'`

- [ ] **Step 3: `vtmak/gates.py` 구현**

```python
"""검증 게이트.

G0 사거리 — .scnx를 만들기 전에 레이아웃만으로 검사한다. 선행 프로젝트는
사거리 미달 사격을 조용히 스킵해 '의도한 스킵'과 '레이아웃 오류'가
구분되지 않았다. 여기서는 레이아웃 문제로 먼저 잡는다.
G1 파싱 — 미매칭 0(선언된 절단 제외), 지명이 전부 레이아웃에 존재.
G2 커버리지 — timetable 모듈에서 별도로 검사한다.
"""
from __future__ import annotations

from dataclasses import dataclass

from .geometry import BattlefieldLayout
from .parser import KNOWN_TRUNCATION, Event, ParseResult
from .ranges import NO_WEAPON, OK, TOO_CLOSE, TOO_FAR, UNVERIFIED, WeaponRanges
from .registry import EntityDef

_FIRE_KIND = {
    "directFireAt": "direct",
    "indirectFireAt": "indirect",
    "aimAt": "indirect",       # 포신 정렬도 같은 사거리 제약을 받는다
}


@dataclass(frozen=True)
class Violation:
    gate: str
    code: str
    detail: str


def check_g1(result: ParseResult, layout: BattlefieldLayout,
             registry: dict[str, EntityDef]) -> list[Violation]:
    out: list[Violation] = []
    for line_no, frag in result.unmatched:
        if frag.startswith(KNOWN_TRUNCATION):
            continue          # 원문 PDF 절단 — 선언된 예외
        out.append(Violation("G1", "C1.1",
                             f"미매칭 문장 line {line_no}: {frag[:80]}"))
    seen: set[str] = set()
    for e in result.events:
        for lid in (e.location, e.src, e.dst):
            if lid and lid not in seen:
                seen.add(lid)
                if layout.local(lid) is None:
                    out.append(Violation(
                        "G1", "C1.2", f"레이아웃에 없는 지명: {lid}"))
    for e in result.events:
        if e.actor and e.actor not in registry:
            out.append(Violation("G1", "C1.3",
                                 f"사전에 없는 객체: {e.actor} ({e.event_id})"))
    return out


def _coord_of(ref: str, registry: dict[str, EntityDef],
              layout: BattlefieldLayout):
    """객체 id 또는 지명 → 좌표. 정적 객체는 바인딩된 지명으로 푼다."""
    bound = layout.static_target(ref)
    if bound:
        return layout.coord(bound)
    ent = registry.get(ref)
    if ent and ent.initial_location:
        return layout.coord(ent.initial_location)
    return layout.coord(ref)


def engagement_pairs(events: list[Event], registry: dict[str, EntityDef],
                     layout: BattlefieldLayout
                     ) -> list[tuple[str, str, str, float]]:
    """(사수 id, fire_kind, 설명, 거리 m). 사수 위치는 문장의 src를 쓴다."""
    out = []
    for e in events:
        kind = _FIRE_KIND.get(e.template)
        if not kind or not e.actor or not e.target:
            continue
        shooter = layout.coord(e.src) if e.src else _coord_of(
            e.actor, registry, layout)
        target = _coord_of(e.target, registry, layout)
        if shooter.is_zero() or target.is_zero():
            continue
        from .geometry import ground_distance
        out.append((e.actor, kind,
                    f"{e.src or e.actor} → {e.target} ({e.event_id})",
                    ground_distance(shooter, target)))
    return out


def check_g0(events: list[Event], registry: dict[str, EntityDef],
             layout: BattlefieldLayout,
             ranges: WeaponRanges) -> list[Violation]:
    out: list[Violation] = []
    seen: set[tuple[str, str, str]] = set()
    for actor, kind, detail, dist in engagement_pairs(events, registry, layout):
        ent = registry.get(actor)
        ecls = ent.entity_class if ent else ""
        key = (ecls, kind, detail.split(" (")[0])
        if key in seen:
            continue          # 같은 쌍을 여러 번 보고하지 않는다
        seen.add(key)
        verdict = ranges.check(ecls, kind, dist)
        if verdict == OK:
            continue
        if verdict == TOO_CLOSE:
            out.append(Violation("G0", "C0.1",
                                 f"{ecls} {detail} {dist:.0f}m — 최소사거리 미달"))
        elif verdict == TOO_FAR:
            out.append(Violation("G0", "C0.2",
                                 f"{ecls} {detail} {dist:.0f}m — 최대사거리 초과"))
        elif verdict == UNVERIFIED:
            out.append(Violation("G0", "C0.3",
                                 f"{ecls} {detail} {dist:.0f}m — 무기체계 미확인"))
        elif verdict == NO_WEAPON:
            out.append(Violation("G0", "C0.4",
                                 f"{ecls} {detail} — 사격 능력 없는 모델"))
    return out
```

- [ ] **Step 4: `scripts/02_parse_events.py` 작성**

```python
"""원문 → 이벤트 JSONL (+G1, +G0 사전 점검)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vtmak.gates import check_g0, check_g1                    # noqa: E402
from vtmak.geometry import BattlefieldLayout                  # noqa: E402
from vtmak.parser import PatternMap, parse_scenario           # noqa: E402
from vtmak.ranges import WeaponRanges                         # noqa: E402
from vtmak.registry import ClassMap, build_registry           # noqa: E402

CONFIG = ROOT / "config"
SRC = ROOT / "scenario_original" / "scenario_v3.txt"
OUT = ROOT / "build" / "events"


def main() -> int:
    layout = BattlefieldLayout.load(CONFIG / "battlefield_layout.json")
    pmap = PatternMap.load(CONFIG / "pattern_map.csv")
    cmap = ClassMap.load(CONFIG / "entity_class_map.csv")
    ranges = WeaponRanges.load(CONFIG / "weapon_ranges.csv")

    result = parse_scenario(SRC.read_text(encoding="utf-8"), pmap)
    static_ids = layout.static_ids()
    registry = build_registry(result.events, cmap, static_ids)

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "battle.jsonl", "w", encoding="utf-8") as f:
        for e in result.events:
            f.write(json.dumps(e.to_json(), ensure_ascii=False) + "\n")

    print(f"문장 {result.sentence_count} · 이벤트 {len(result.events)} · "
          f"객체 {len(registry)}")

    g1 = check_g1(result, layout, registry)
    g0 = check_g0(result.events, registry, layout, ranges)
    for v in g1 + g0:
        print(f"  [{v.gate}/{v.code}] {v.detail}")
    hard = [v for v in g1 + g0 if v.code not in ("C0.3", "C0.4")]
    print(f"G1 {len(g1)}건 · G0 {len(g0)}건 (차단 {len(hard)}건)")
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_gates.py -v`
Expected: PASS (7 passed)

- [ ] **Step 6: 스크립트 실제 실행 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python scripts/02_parse_events.py; echo "exit=$?"`
Expected: `문장 3000 · 이벤트 2999 · 객체 335`, 차단 0건, `exit=0`. `build/events/battle.jsonl`이 2,999줄로 생성된다.

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && wc -l build/events/battle.jsonl`
Expected: `2999`

- [ ] **Step 7: 커밋**

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments"
git add new_VTMAK/vtmak/gates.py new_VTMAK/scripts/02_parse_events.py new_VTMAK/tests/test_gates.py
git commit -m "feat(new_vtmak): G0 사거리 게이트와 G1 파싱 게이트"
```

---

### Task 7: 타임테이블과 G2

**Files:**
- Create: `new_VTMAK/vtmak/timetable.py`
- Create: `new_VTMAK/scripts/03_build_timetable.py`
- Test: `new_VTMAK/tests/test_timetable.py`
- Reference: `VTMAK/vtmak/timetable.py` (구조 참고 — 이벤트 스키마가 달라 그대로 복사할 수 없다)

**Interfaces:**
- Consumes: `vtmak.parser.Event`, `vtmak.registry.EntityDef`
- Produces:
  - `Cell(object_id: str, t0: int, t1: int, state: str, location: str)` (frozen)
  - `boundaries(events) -> list[int]` — 이벤트가 존재하는 시각 정렬 목록
  - `build_timetable(events, registry) -> list[Cell]`
  - `plan_coverage(events, registry) -> tuple[set[str], set[str]]` — `(플랜 있는 객체, task 가능하나 플랜 없는 객체)`
  - `check_g2(events, registry) -> list[Violation]`

플랜 유발 이벤트는 `task_kind`가 `noop`이 아닌 것 — 즉 `moveTo` / `directFireAt` / `indirectFireAt` / `aimAt` 템플릿이다.

- [ ] **Step 1: 실패하는 테스트 작성**

`new_VTMAK/tests/test_timetable.py`:

```python
from pathlib import Path

import pytest

from vtmak.geometry import BattlefieldLayout
from vtmak.parser import PatternMap, parse_scenario
from vtmak.registry import ClassMap, build_registry
from vtmak.timetable import build_timetable, check_g2, plan_coverage

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def env():
    pm = PatternMap.load(ROOT / "config" / "pattern_map.csv")
    res = parse_scenario(
        (ROOT / "scenario_original" / "scenario_v3.txt").read_text(encoding="utf-8"), pm)
    lay = BattlefieldLayout.load(ROOT / "config" / "battlefield_layout.json")
    cm = ClassMap.load(ROOT / "config" / "entity_class_map.csv")
    reg = build_registry(res.events, cm, lay.static_ids())
    return res.events, reg


def test_every_taskable_object_has_a_plan(env):
    events, reg = env
    _, missing = plan_coverage(events, reg)
    assert missing == set(), sorted(missing)[:10]


def test_g2_passes(env):
    events, reg = env
    assert check_g2(events, reg) == []


def test_timetable_covers_all_objects(env):
    events, reg = env
    cells = build_timetable(events, reg)
    assert {c.object_id for c in cells} == set(reg)


def test_cells_are_contiguous_per_object(env):
    events, reg = env
    cells = build_timetable(events, reg)
    by = {}
    for c in cells:
        by.setdefault(c.object_id, []).append(c)
    for oid, cs in by.items():
        cs.sort(key=lambda c: c.t0)
        for a, b in zip(cs, cs[1:]):
            assert a.t1 == b.t0, f"{oid}: {a.t1} != {b.t0}"


def test_suppressed_object_keeps_final_state(env):
    events, reg = env
    cells = [c for c in build_timetable(events, reg)
             if c.object_id == "FR-INF-001"]
    assert cells[-1].state == "제압"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_timetable.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtmak.timetable'`

- [ ] **Step 3: `vtmak/timetable.py` 구현**

```python
"""이벤트 → 객체별 타임테이블 + G2 커버리지.

선행 프로젝트는 플랜 없는 객체에 코드 상수로 기본 행동을 주입했다
(커버리지 49% → 98%). 새 원문은 task 가능 객체 전원이 실제 행동을 갖고
있으므로 그 주입을 하지 않는다. 하나라도 비면 G2가 잡는다.
"""
from __future__ import annotations

from dataclasses import dataclass

from .gates import Violation
from .parser import Event
from .registry import EntityDef

# 플랜(태스크)을 만드는 템플릿. 나머지는 상태·서술이라 PLN에 남지 않는다.
PLAN_TEMPLATES = {"moveTo", "directFireAt", "indirectFireAt", "aimAt"}


@dataclass(frozen=True)
class Cell:
    object_id: str
    t0: int
    t1: int
    state: str
    location: str


def boundaries(events: list[Event]) -> list[int]:
    return sorted({e.time_s for e in events})


def plan_coverage(events: list[Event],
                  registry: dict[str, EntityDef]) -> tuple[set[str], set[str]]:
    have = {e.actor for e in events
            if e.template in PLAN_TEMPLATES and e.actor}
    taskable = {oid for oid, d in registry.items() if d.taskable}
    return have & taskable, taskable - have


def check_g2(events: list[Event],
             registry: dict[str, EntityDef]) -> list[Violation]:
    _, missing = plan_coverage(events, registry)
    return [Violation("G2", "C2.1", f"플랜 없는 task 가능 객체: {oid}")
            for oid in sorted(missing)]


def build_timetable(events: list[Event],
                    registry: dict[str, EntityDef]) -> list[Cell]:
    """객체별로 상태·위치가 바뀌는 시점마다 셀을 끊는다.

    셀은 [t0, t1)이며 같은 객체의 셀은 빈틈 없이 이어진다.
    """
    bounds = boundaries(events)
    if not bounds:
        return []
    end = bounds[-1] + 1

    changes: dict[str, dict[int, tuple[str, str]]] = {}
    for e in sorted(events, key=lambda x: (x.time_s, x.event_id)):
        if not e.actor:
            continue
        cur = changes.setdefault(e.actor, {})
        prev_state, prev_loc = cur.get(e.time_s, (None, None))
        state = e.state_to or prev_state
        loc = e.location or e.dst or e.src or prev_loc
        cur[e.time_s] = (state, loc)

    cells: list[Cell] = []
    for oid in sorted(registry):
        d = registry[oid]
        state, loc = d.initial_state, d.initial_location
        times = sorted(changes.get(oid, {}))
        marks = [0] + [t for t in times if t > 0]
        for i, t0 in enumerate(marks):
            if t0 in changes.get(oid, {}):
                s, l = changes[oid][t0]
                state = s or state
                loc = l or loc
            t1 = marks[i + 1] if i + 1 < len(marks) else end
            cells.append(Cell(oid, t0, t1, state, loc))
    return cells
```

- [ ] **Step 4: `scripts/03_build_timetable.py` 작성**

```python
"""이벤트 → 객체별 타임테이블 CSV (+G2)."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vtmak.geometry import BattlefieldLayout               # noqa: E402
from vtmak.parser import Event                             # noqa: E402
from vtmak.registry import ClassMap, build_registry        # noqa: E402
from vtmak.timetable import build_timetable, check_g2      # noqa: E402

ROOT_CFG = ROOT / "config"
EVENTS = ROOT / "build" / "events" / "battle.jsonl"
OUT = ROOT / "build" / "timetable"


def main() -> int:
    if not EVENTS.exists():
        print("build/events/battle.jsonl 없음 — 02를 먼저 실행할 것")
        return 1
    events = [Event(**json.loads(l))
              for l in EVENTS.read_text(encoding="utf-8").splitlines() if l]
    layout = BattlefieldLayout.load(ROOT_CFG / "battlefield_layout.json")
    cmap = ClassMap.load(ROOT_CFG / "entity_class_map.csv")
    registry = build_registry(events, cmap, layout.static_ids())

    cells = build_timetable(events, registry)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "battle.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["object_id", "t0", "t1", "state", "location"])
        for c in cells:
            w.writerow([c.object_id, c.t0, c.t1, c.state, c.location])

    v = check_g2(events, registry)
    for x in v:
        print(f"  [{x.gate}/{x.code}] {x.detail}")
    print(f"셀 {len(cells)} · 객체 {len(registry)} · G2 {len(v)}건")
    return 1 if v else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 테스트와 스크립트 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_timetable.py -v && python scripts/03_build_timetable.py; echo "exit=$?"`
Expected: 테스트 5 passed. 스크립트가 `G2 0건`을 출력하고 `exit=0`.

- [ ] **Step 6: 커밋**

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments"
git add new_VTMAK/vtmak/timetable.py new_VTMAK/scripts/03_build_timetable.py new_VTMAK/tests/test_timetable.py
git commit -m "feat(new_vtmak): 타임테이블과 G2 커버리지 (플랜 보강 없이 328/328)"
```

---

### Task 8: `.scnx` 저작 백엔드 이식

**Files:**
- Copy: `VTMAK/vtmak/scnx/ids.py` → `new_VTMAK/vtmak/scnx/ids.py` (수정 없음)
- Copy: `VTMAK/vtmak/scnx/catalog.py` → `new_VTMAK/vtmak/scnx/catalog.py` (수정 없음)
- Copy: `VTMAK/vtmak/scnx/golden.py` → `new_VTMAK/vtmak/scnx/golden.py` (수정 없음)
- Copy: `VTMAK/config/task_catalog.csv` → `new_VTMAK/config/task_catalog.csv`
- Copy: `VTMAK/vtmak/scnx/writer.py` → `new_VTMAK/vtmak/scnx/writer.py` (import·기본값 수정)
- Test: `new_VTMAK/tests/test_golden.py`

**Interfaces:**
- Consumes: `vtmak.geometry.Coord`
- Produces:
  - `IdAllocator(seed).alloc(kind: str, key: str) -> str` (uuid5, 결정적)
  - `TaskCatalog.load(path)`, `.get(type_group, action_label) -> TaskTemplate | None`, `.labels_for(type_group) -> list[str]`
  - `DisCatalog.load(path)`, `.dis(entity_class) -> tuple[int,...] | None`, `.known(entity_class) -> bool`
  - `Golden.load(scnx_path) -> Golden`, `.entity_by_dis(dis) -> GoldenObject | None`, `.template_for(kind) -> GoldenObject | None`, `.points_and_areas() -> list[GoldenObject]`

- [ ] **Step 1: 파일 복사**

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments"
cp "VTMAK/vtmak/scnx/ids.py"      "new_VTMAK/vtmak/scnx/ids.py"
cp "VTMAK/vtmak/scnx/catalog.py"  "new_VTMAK/vtmak/scnx/catalog.py"
cp "VTMAK/vtmak/scnx/golden.py"   "new_VTMAK/vtmak/scnx/golden.py"
cp "VTMAK/vtmak/scnx/writer.py"   "new_VTMAK/vtmak/scnx/writer.py"
cp "VTMAK/config/task_catalog.csv" "new_VTMAK/config/task_catalog.csv"
```

- [ ] **Step 2: import 경로 수정**

`new_VTMAK/vtmak/scnx/writer.py`에서 `from .geometry import Coord`를 `from ..geometry import Coord`로 바꾼다(`geometry`가 `scnx/` 밖으로 이동했다). `catalog.py`·`golden.py`·`ids.py`는 `geometry`를 import하지 않으므로 수정할 것이 없다 — `grep`으로 확인한다.

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK"
grep -n "from .geometry\|from .spec\|import geometry" vtmak/scnx/*.py
```

`writer.py`의 두 곳을 고친다:
- `from .geometry import Coord` → `from ..geometry import Coord`
- `def get_writer(name: str, golden: str = "ys2.scnx")` → `def get_writer(name: str, golden: str = "yewon_test.scnx")`
- `class TemplateScnxWriter: def __init__(self, golden_path: str = "ys2.scnx", …)` → 기본값을 `"yewon_test.scnx"`로

`writer.py`는 `from .spec import ControlObjectSpec, EntitySpec, ScnxSpec`을 참조한다. `spec.py`는 Task 9에서 만든다. 이 태스크에서는 `writer.py`가 아직 import되지 않으므로 테스트가 통과한다.

- [ ] **Step 3: 실패하는 테스트 작성**

`new_VTMAK/tests/test_golden.py`:

```python
from pathlib import Path

import pytest

from vtmak.scnx.catalog import DisCatalog, TaskCatalog
from vtmak.scnx.golden import Golden
from vtmak.scnx.ids import IdAllocator

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "yewon_test" / "yewon_test.scnx"

# 시나리오가 쓰는 26종 — dis_catalog와 golden 양쪽에 다 있어야 한다.
SCENARIO_CLASSES = [
    "US Army M4", "Russian Soldier AK47", "Russian Soldier SA7",
    "Russian Soldier Sniper-127", "US Army XM107", "Turkish Soldier RPG",
    "US Army Javelin", "T-69 MBT", "T-72 MBT", "T-80 MBT",
    "M1A2 Abrams MBT", "BTR-60 APC", "BTR-80 APC", "LAV III APC",
    "M113 APC", "ZPU-4 AA Gun", "GAZ-66 Truck", "M35 Truck",
    "M1028 FMTV Canvas Cargo Truck", "M1083A1 FMTV Flatbed Truck",
    "MO-120RT-61 Mortar", "M109 Howitzer", "AHS Krab Howitzer",
    "CAESAR SP Howitzer", "M901 Patriot Launcher",
    "MIM-104 Patriot Launcher",
]


@pytest.fixture(scope="module")
def dis():
    return DisCatalog.load(ROOT / "config" / "dis_catalog.csv")


def test_id_allocator_is_deterministic():
    a = IdAllocator("battle")
    b = IdAllocator("battle")
    assert a.alloc("entity", "FR-INF-001") == b.alloc("entity", "FR-INF-001")
    assert a.alloc("entity", "FR-INF-001") != a.alloc("entity", "FR-INF-002")


def test_dis_catalog_covers_scenario_classes(dis):
    missing = [c for c in SCENARIO_CLASSES if dis.dis(c) is None]
    assert missing == []


def test_task_catalog_has_expected_type_groups():
    tc = TaskCatalog.load(ROOT / "config" / "task_catalog.csv")
    for tg in ["보병 - 소총(M4 계열)", "보병 - RPG 계열",
               "차량/장갑차 - M2HB 계열", "포병 - 155mm 자주포",
               "포병 - 박격포(m9333he 계열)"]:
        assert tc.labels_for(tg), tg


@pytest.mark.skipif(not GOLDEN.exists(), reason="golden .scnx 없음")
def test_golden_has_a_record_for_every_scenario_dis(dis):
    g = Golden.load(GOLDEN)
    missing = [c for c in SCENARIO_CLASSES
               if g.entity_by_dis(dis.dis(c)) is None]
    assert missing == [], f"golden에 레코드 없는 모델: {missing}"
```

- [ ] **Step 4: golden `.scnx` 준비**

`yewon_test/`는 압축이 풀린 디렉터리다. `Golden.load`는 `.scnx`(ZIP)를 기대하므로 ZIP으로 묶는다.

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK/yewon_test"
python -c "
import zipfile, pathlib
d = pathlib.Path('.')
with zipfile.ZipFile('yewon_test.scnx', 'w', zipfile.ZIP_DEFLATED) as z:
    for p in sorted(d.iterdir()):
        if p.is_file() and p.suffix != '.scnx':
            z.write(p, p.name)
print('ok')
"
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_golden.py -v`
Expected: PASS (4 passed). `test_golden_has_a_record_for_every_scenario_dis`가 실패하면 golden에 그 모델이 실제로 없다는 뜻이므로 **구현을 고치지 말고 보고할 것**.

- [ ] **Step 6: 커밋**

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments"
git add new_VTMAK/vtmak/scnx new_VTMAK/config/task_catalog.csv new_VTMAK/tests/test_golden.py new_VTMAK/yewon_test/yewon_test.scnx
git commit -m "chore(new_vtmak): .scnx 저작 백엔드 이식 (ids/catalog/golden/writer)"
```

---

### Task 9: 스펙 조립과 플랜 생성

**Files:**
- Create: `new_VTMAK/vtmak/scnx/plan.py`
- Create: `new_VTMAK/vtmak/scnx/spec.py`
- Test: `new_VTMAK/tests/test_spec.py`
- Reference: `VTMAK/vtmak/scnx/plan.py` (LABEL_CANDIDATES·_fill 로직 이식), `VTMAK/vtmak/scnx/spec.py` (구조 참고 — `_enrich_plans`·`_OBJECTIVES`·`_ENEMY_TARGETS`는 이식하지 않는다)

**Interfaces:**
- Consumes: `vtmak.parser.Event`, `vtmak.registry.EntityDef`, `vtmak.geometry.BattlefieldLayout`, `vtmak.ranges.WeaponRanges`, `vtmak.scnx.catalog.TaskCatalog`, `vtmak.scnx.catalog.DisCatalog`, `vtmak.scnx.ids.IdAllocator`
- Produces:
  - `PlanStep(event_id, time_s, template, task_kind, action_label, pln: str | None, refs: list[str], issues: list[str])`
  - `build_entity_plan(events: list[Event], entity: EntityDef, catalog: TaskCatalog, ranges: WeaponRanges, ctx: PlanContext) -> list[PlanStep]` — 좌표는 `ctx.coord_of`로 얻으므로 `layout`을 직접 받지 않는다
  - `EntitySpec(object_id, name, uuid, entity_class, type_group, faction, dis, coord, heading, initial_state)`
  - `ControlObjectSpec(ref_id, kind, uuid, name, coord, vertices)`
  - `ScnxSpec(scenario_id, terrain, entities, control_objects, entity_plans)`
  - `build_spec(events, registry, layout, catalog, dis, ranges, scenario_id, seed="") -> ScnxSpec`

**설계 스펙 대비 변경점 (반드시 지킬 것):**
1. `_enrich_plans`·`_OBJECTIVES`·`_ENEMY_TARGETS`를 만들지 않는다. 플랜은 실제 이벤트에서만 나온다.
2. 사거리 미달 사격을 조용히 버리지 않는다. `PlanStep.issues`에 사유를 남기고 `pln=None`으로 둔다. G0가 이미 앞에서 잡았으므로 여기 도달하면 그 자체가 이상 신호다.
3. 정적 객체 7개는 `EntitySpec`을 만들지 않는다. 간접사격 목표일 때 `layout.static_target()`으로 좌표를 풀어 `ffe-on-location` 템플릿에 넣는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`new_VTMAK/tests/test_spec.py`:

```python
from pathlib import Path

import pytest

from vtmak.geometry import BattlefieldLayout
from vtmak.parser import PatternMap, parse_scenario
from vtmak.ranges import WeaponRanges
from vtmak.registry import ClassMap, build_registry
from vtmak.scnx.catalog import DisCatalog, TaskCatalog
from vtmak.scnx.spec import build_spec

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def spec():
    cfg = ROOT / "config"
    pm = PatternMap.load(cfg / "pattern_map.csv")
    res = parse_scenario(
        (ROOT / "scenario_original" / "scenario_v3.txt").read_text(encoding="utf-8"), pm)
    lay = BattlefieldLayout.load(cfg / "battlefield_layout.json")
    cm = ClassMap.load(cfg / "entity_class_map.csv")
    reg = build_registry(res.events, cm, lay.static_ids())
    return build_spec(res.events, reg, lay,
                      TaskCatalog.load(cfg / "task_catalog.csv"),
                      DisCatalog.load(cfg / "dis_catalog.csv"),
                      WeaponRanges.load(cfg / "weapon_ranges.csv"),
                      scenario_id="battle")


def test_entities_exclude_static_objects(spec):
    ids = {e.object_id for e in spec.entities}
    assert len(ids) == 328
    assert "EN-FP-001" not in ids
    assert "OBJ-009" not in ids


def test_every_entity_has_dis_and_nonzero_coord(spec):
    for e in spec.entities:
        assert e.dis is not None, e.object_id
        assert not e.coord.is_zero(), e.object_id


def test_entities_sharing_a_location_are_jittered(spec):
    at = [e for e in spec.entities
          if e.object_id.startswith("FR-INF-")][:20]
    coords = {e.coord.as_tuple() for e in at}
    assert len(coords) == len(at)


def test_all_taskable_entities_have_at_least_one_pln(spec):
    empty = [oid for oid, steps in spec.entity_plans.items()
             if not any(s.pln for s in steps)]
    assert empty == [], sorted(empty)[:10]


def test_no_synthesised_plan_steps(spec):
    # 플랜 보강을 제거했으므로 event_id가 없는 스텝이 있으면 안 된다.
    for steps in spec.entity_plans.values():
        for s in steps:
            assert s.event_id.startswith("E"), s


def test_indirect_fire_targets_static_object_by_location(spec):
    steps = [s for s in spec.entity_plans["FR-M109-001"] if s.pln]
    ffe = [s for s in steps if "ffe-on-location" in s.pln]
    assert ffe, [s.pln for s in steps]


def test_control_objects_cover_referenced_locations(spec):
    refs = {c.ref_id for c in spec.control_objects}
    assert "LOC_중앙킬존" in refs
    assert all(c.coord is None or not c.coord.is_zero()
               for c in spec.control_objects)


def test_spec_is_deterministic(spec):
    a = [(e.object_id, e.uuid, e.coord.as_tuple()) for e in spec.entities]
    assert a == sorted(a, key=lambda x: x[0]) or len(a) == len(set(x[0] for x in a))
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_spec.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtmak.scnx.plan'`

- [ ] **Step 3: `vtmak/scnx/plan.py` 구현**

`VTMAK/vtmak/scnx/plan.py`의 `LABEL_CANDIDATES` 표와 `_fill` 치환 로직을 가져오되, 이벤트 스키마와 사거리 처리가 바뀌었다. `MIN_INDIRECT_RANGE_M` 상수와 `promote_target` 승격은 **가져오지 않는다** — 사거리는 `WeaponRanges`가, 목표는 원문이 명시한 `target`이 결정한다.

```python
"""이벤트 → VR-Forces PLN(Task/Set) 블록.

선행 프로젝트와 두 가지가 다르다.
1) 사거리 상수를 코드에 두지 않는다. WeaponRanges가 판정한다.
2) '지점 사격 → 근처 적 객체로 승격'을 하지 않는다. 원문이 모든 사격에
   목표 객체를 명시하므로 추측할 필요가 없다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..geometry import Coord, ground_distance
from ..parser import Event
from ..ranges import OK, UNVERIFIED, WeaponRanges
from ..registry import EntityDef
from .catalog import TaskCatalog

# (task_kind, ref_kind) → task_catalog '행동' 후보. 앞에서부터 type_group에
# 존재하는 첫 템플릿을 쓴다. 라벨은 task_catalog.csv '행동' 컬럼과 정확히 일치.
LABEL_CANDIDATES: dict[tuple[str, str], list[str]] = {
    ("move", "COORD"): ["좌표로 이동", "통제점으로 이동"],
    ("move", "CONTROL_POINT"): ["통제점으로 이동", "좌표로 이동"],
    ("fire_direct", "ENTITY"): ["대상 직접사격", "대상 자동무장 사격"],
    ("fire_indirect", "COORD"): ["좌표 대상 간접사격"],
    ("fire_indirect", "ENTITY"): ["Entity 대상 간접사격", "좌표 대상 간접사격"],
    ("aim", "ENTITY"): ["객체 조준"],
    ("aim", "COORD"): ["객체 조준"],
}


class PlanContext(Protocol):
    def entity_uuid(self, object_id: str) -> str | None: ...
    def ref_uuid(self, ref_id: str) -> str: ...
    def coord_of(self, ref: str) -> Coord: ...
    def ref_kind(self, ref: str) -> str: ...   # ENTITY | COORD | CONTROL_POINT


@dataclass
class PlanStep:
    event_id: str
    time_s: int
    template: str
    task_kind: str
    action_label: str | None
    pln: str | None
    refs: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


_KIND_BY_TEMPLATE = {
    "moveTo": "move",
    "directFireAt": "fire_direct",
    "indirectFireAt": "fire_indirect",
    "aimAt": "aim",
}
_FIRE_KIND = {"fire_direct": "direct",
              "fire_indirect": "indirect",
              "aim": "indirect"}


def build_entity_plan(events: list[Event], entity: EntityDef,
                      catalog: TaskCatalog, ranges: WeaponRanges,
                      ctx: PlanContext) -> list[PlanStep]:
    steps: list[PlanStep] = []
    for e in sorted(events, key=lambda x: (x.time_s, x.event_id)):
        kind = _KIND_BY_TEMPLATE.get(e.template)
        if kind is None:
            continue
        steps.append(_one(e, entity, kind, catalog, ranges, ctx))
    return steps


def _one(e: Event, entity: EntityDef, kind: str, catalog: TaskCatalog,
         ranges: WeaponRanges, ctx: PlanContext) -> PlanStep:
    ref = e.target or e.dst
    step = PlanStep(e.event_id, e.time_s, e.template, kind,
                    None, None, [], [])
    if not ref:
        step.issues.append("참조 대상 없음")
        return step

    fire = _FIRE_KIND.get(kind)
    if fire:
        d = ground_distance(ctx.coord_of(e.src or entity.initial_location),
                      ctx.coord_of(ref))
        verdict = ranges.check(entity.entity_class, fire, d)
        if verdict not in (OK, UNVERIFIED):
            step.issues.append(f"사거리 {verdict} ({d:.0f}m) — G0가 먼저 잡았어야 함")
            return step

    ref_kind = ctx.ref_kind(ref)
    tmpl, label = _pick_template(kind, ref_kind, entity.type_group, catalog)
    if tmpl is None:
        step.issues.append(
            f"템플릿 없음: kind={kind} ref_kind={ref_kind} tg={entity.type_group}")
        return step
    step.action_label = label
    step.pln, step.refs = _fill(tmpl.pln, kind, ref_kind, ref, entity, ctx)
    return step


def _pick_template(kind: str, ref_kind: str, type_group: str,
                   catalog: TaskCatalog):
    for label in LABEL_CANDIDATES.get((kind, ref_kind), []):
        t = catalog.get(type_group, label)
        if t is not None:
            return t, label
    return None, None


def _fill(template: str, kind: str, ref_kind: str, ref: str,
          entity: EntityDef, ctx: PlanContext) -> tuple[str, list[str]]:
    """placeholder 치환. 좌표는 ECEF 미터로 넣는다."""
    out, refs = template, []
    weapon = entity.weapons[0] if entity.weapons else ""
    if ref_kind == "ENTITY":
        uuid = ctx.entity_uuid(ref) or ctx.ref_uuid(ref)
        refs.append(uuid)
        out = (out.replace("TARGET_UUID", uuid)
                  .replace("ENTITY_UUID", uuid)
                  .replace("CONTROL_POINT_UUID", uuid))
    else:
        uuid = ctx.ref_uuid(ref)
        refs.append(uuid)
        out = out.replace("CONTROL_POINT_UUID", uuid).replace(
            "TARGET_UUID", uuid).replace("ENTITY_UUID", uuid)
    x, y, z = ctx.coord_of(ref).to_ecef()
    out = out.replace("(aiming-point X Y Z)",
                      f"(aiming-point {x:.6f} {y:.6f} {z:.6f})")
    out = out.replace("(location X Y Z)",
                      f"(location {x:.6f} {y:.6f} {z:.6f})")
    if weapon:
        out = out.replace('(weapon-to-fire "M4 rifle")',
                          f'(weapon-to-fire "{weapon}")')
        out = out.replace('(weapon "M4 rifle")', f'(weapon "{weapon}")')
    return out, refs


def balanced(pln: str) -> bool:
    depth = 0
    for ch in pln:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0
```

`_fill`의 치환 토큰은 `task_catalog.csv`의 `PLN_문법`·`교체할_파라미터` 컬럼과 맞아야 한다. 구현 전에 다음으로 실제 토큰을 확인할 것:

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK"
python -c "
import csv
for r in csv.DictReader(open('config/task_catalog.csv', encoding='utf-8-sig')):
    print(r['객체_타입_그룹'], '|', r['행동'], '|', r['교체할_파라미터'])
"
```

- [ ] **Step 4: `vtmak/scnx/spec.py` 구현**

```python
"""이벤트 + 사전 + 레이아웃 → ScnxSpec(결정적 확정 스펙).

writer가 읽는 유일한 입력. 좌표·uuid·DIS가 여기서 전부 확정된다.
선행 프로젝트의 _enrich_plans(백마고지 탈환 기본행동 주입)는 없다 —
task 가능 객체 전원이 실제 이벤트를 갖고 있다.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from ..geometry import BattlefieldLayout, Coord
from ..parser import Event
from ..ranges import WeaponRanges
from ..registry import EntityDef
from .catalog import DisCatalog, TaskCatalog
from .ids import IdAllocator
from .plan import PlanStep, build_entity_plan

DEFAULT_HEADING = 0.0   # 원문에 방위각이 없다
JITTER_M = 25.0         # 같은 지명을 공유하는 객체가 겹치지 않도록


@dataclass
class EntitySpec:
    object_id: str
    name: str
    uuid: str
    entity_class: str
    type_group: str
    faction: str
    dis: tuple[int, ...] | None
    coord: Coord
    heading: float
    initial_state: str


@dataclass
class ControlObjectSpec:
    ref_id: str
    kind: str            # COORD | CONTROL_POINT | ROUTE
    uuid: str
    name: str
    coord: Coord | None
    vertices: tuple[Coord, ...] = ()


@dataclass
class ScnxSpec:
    scenario_id: str
    terrain: str
    entities: list[EntitySpec] = field(default_factory=list)
    control_objects: list[ControlObjectSpec] = field(default_factory=list)
    entity_plans: dict[str, list[PlanStep]] = field(default_factory=dict)


def _jitter_offset(key: str, meters: float = JITTER_M) -> tuple[float, float]:
    """object_id 해시로 ±meters 결정적 오프셋(로컬 미터)."""
    h = hashlib.sha256(key.encode("utf-8")).digest()
    dx = (int.from_bytes(h[:4], "big") / 2 ** 32 - 0.5) * 2 * meters
    dy = (int.from_bytes(h[4:8], "big") / 2 ** 32 - 0.5) * 2 * meters
    return dx, dy


class _Ctx:
    """plan.PlanContext 구현."""

    def __init__(self, layout: BattlefieldLayout, ids: IdAllocator,
                 registry: dict[str, EntityDef],
                 entity_uuids: dict[str, str]) -> None:
        self._layout = layout
        self._ids = ids
        self._reg = registry
        self._uuids = entity_uuids
        self.referenced_locs: set[str] = set()

    def entity_uuid(self, object_id: str) -> str | None:
        return self._uuids.get(object_id)

    def ref_kind(self, ref: str) -> str:
        if ref in self._uuids:
            return "ENTITY"
        return "COORD"

    def ref_uuid(self, ref: str) -> str:
        if ref in self._uuids:
            return self._uuids[ref]
        lid = self._layout.static_target(ref) or ref
        self.referenced_locs.add(lid)
        return self._ids.alloc("control_object", lid)

    def coord_of(self, ref: str) -> Coord:
        """객체 id → 그 객체의 배치 좌표. 정적 객체·지명 → 레이아웃 좌표."""
        bound = self._layout.static_target(ref)
        if bound:
            return self._layout.coord(bound)
        ent = self._reg.get(ref)
        if ent and ent.initial_location:
            dx, dy = _jitter_offset(ref)
            return self._layout.offset_coord(ent.initial_location, dx, dy)
        return self._layout.coord(ref)


def build_spec(events: list[Event], registry: dict[str, EntityDef],
               layout: BattlefieldLayout, catalog: TaskCatalog,
               dis: DisCatalog, ranges: WeaponRanges,
               scenario_id: str, seed: str = "") -> ScnxSpec:
    ids = IdAllocator(seed or scenario_id)
    taskable = {oid: d for oid, d in sorted(registry.items()) if d.taskable}
    entity_uuids = {oid: ids.alloc("entity", oid) for oid in taskable}
    ctx = _Ctx(layout, ids, registry, entity_uuids)

    spec = ScnxSpec(scenario_id=scenario_id, terrain=layout.terrain)
    for oid, d in taskable.items():
        dx, dy = _jitter_offset(oid)
        spec.entities.append(EntitySpec(
            object_id=oid,
            name=d.role or oid,
            uuid=entity_uuids[oid],
            entity_class=d.entity_class,
            type_group=d.type_group,
            faction=d.faction,
            dis=dis.dis(d.entity_class),
            coord=layout.offset_coord(d.initial_location, dx, dy),
            heading=DEFAULT_HEADING,
            initial_state=d.initial_state,
        ))

    by_actor: dict[str, list[Event]] = {oid: [] for oid in taskable}
    for e in events:
        if e.actor in by_actor:
            by_actor[e.actor].append(e)
    for oid, d in taskable.items():
        spec.entity_plans[oid] = build_entity_plan(
            by_actor[oid], d, catalog, ranges, ctx)

    used = set(ctx.referenced_locs) | {
        d.initial_location for d in taskable.values() if d.initial_location}
    for lid in sorted(used):
        spec.control_objects.append(ControlObjectSpec(
            ref_id=lid, kind="COORD",
            uuid=ids.alloc("control_object", lid),
            name=lid.removeprefix("LOC_"),
            coord=layout.coord(lid)))
    return spec
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_spec.py -v`
Expected: PASS (8 passed)

`test_indirect_fire_targets_static_object_by_location`이 실패하면 `LABEL_CANDIDATES[("fire_indirect","COORD")]`가 `task_catalog`의 실제 라벨("좌표 대상 간접사격")과 일치하는지, `ref_kind`가 정적 객체에 대해 `"COORD"`를 돌려주는지 확인할 것.

- [ ] **Step 6: 커밋**

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments"
git add new_VTMAK/vtmak/scnx/plan.py new_VTMAK/vtmak/scnx/spec.py new_VTMAK/tests/test_spec.py
git commit -m "feat(new_vtmak): 스펙 조립과 플랜 생성 (플랜 보강 상수 제거)"
```

---

### Task 10: `.scnx` 출력과 G3

**Files:**
- Create: `new_VTMAK/vtmak/scnx/gates.py`
- Create: `new_VTMAK/scripts/04_compile_scnx.py`
- Modify: `new_VTMAK/vtmak/scnx/writer.py` (Task 8에서 복사한 것 — 스펙 필드명 맞춤)
- Test: `new_VTMAK/tests/test_writer.py`
- Reference: `VTMAK/vtmak/scnx/gates.py`, `VTMAK/scripts/04_compile_scnx.py`

**Interfaces:**
- Consumes: `vtmak.scnx.spec.ScnxSpec`, `vtmak.scnx.golden.Golden`, `vtmak.gates.Violation`
- Produces:
  - `check_g3(spec: ScnxSpec, golden: Golden, dis: DisCatalog) -> list[Violation]`
  - `get_writer(name: str, golden: str) -> IScnxWriter`, `.write(spec, out_dir) -> Path`

- [ ] **Step 1: 실패하는 테스트 작성**

`new_VTMAK/tests/test_writer.py`:

```python
import zipfile
from pathlib import Path

import pytest

from vtmak.geometry import BattlefieldLayout
from vtmak.parser import PatternMap, parse_scenario
from vtmak.ranges import WeaponRanges
from vtmak.registry import ClassMap, build_registry
from vtmak.scnx.catalog import DisCatalog, TaskCatalog
from vtmak.scnx.gates import check_g3
from vtmak.scnx.golden import Golden
from vtmak.scnx.spec import build_spec
from vtmak.scnx.writer import get_writer

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "yewon_test" / "yewon_test.scnx"


@pytest.fixture(scope="module")
def built():
    cfg = ROOT / "config"
    pm = PatternMap.load(cfg / "pattern_map.csv")
    res = parse_scenario(
        (ROOT / "scenario_original" / "scenario_v3.txt").read_text(encoding="utf-8"), pm)
    lay = BattlefieldLayout.load(cfg / "battlefield_layout.json")
    cm = ClassMap.load(cfg / "entity_class_map.csv")
    reg = build_registry(res.events, cm, lay.static_ids())
    dis = DisCatalog.load(cfg / "dis_catalog.csv")
    spec = build_spec(res.events, reg, lay,
                      TaskCatalog.load(cfg / "task_catalog.csv"), dis,
                      WeaponRanges.load(cfg / "weapon_ranges.csv"), "battle")
    return spec, dis


@pytest.mark.skipif(not GOLDEN.exists(), reason="golden .scnx 없음")
def test_g3_passes(built):
    spec, dis = built
    v = check_g3(spec, Golden.load(GOLDEN), dis)
    assert v == [], [x.detail for x in v]


@pytest.mark.skipif(not GOLDEN.exists(), reason="golden .scnx 없음")
def test_writes_a_loadable_zip(built, tmp_path):
    spec, _ = built
    out = get_writer("template", str(GOLDEN)).write(spec, tmp_path)
    assert out.exists() and out.suffix == ".scnx"
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        stem = out.stem
        for ext in (".scn", ".oob", ".pln", ".omp"):
            assert any(n.endswith(ext) for n in names), ext
        oob = z.read(f"{stem}.oob").decode("utf-8", "replace")
    # 328 엔티티가 전부 들어갔는가
    assert oob.count("(local-vrf-object") >= 328


@pytest.mark.skipif(not GOLDEN.exists(), reason="golden .scnx 없음")
def test_markings_are_ascii(built, tmp_path):
    # 한글 marking은 DIS 11byte 한계를 넘겨 깨지고 클릭이 안 된다.
    spec, _ = built
    out = get_writer("template", str(GOLDEN)).write(spec, tmp_path)
    with zipfile.ZipFile(out) as z:
        oob = z.read(f"{out.stem}.oob").decode("utf-8", "replace")
    import re
    for m in re.findall(r'\(marking-text "([^"]*)"\)', oob):
        assert m.isascii(), m
        assert len(m) <= 11, m


def test_output_is_byte_identical_across_runs(built, tmp_path):
    spec, _ = built
    a = get_writer("dir", str(GOLDEN)).write(spec, tmp_path / "a")
    b = get_writer("dir", str(GOLDEN)).write(spec, tmp_path / "b")
    assert a.read_bytes() == b.read_bytes()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_writer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtmak.scnx.gates'`

- [ ] **Step 3: `vtmak/scnx/gates.py` 구현**

```python
"""G3 — .scnx 정합성.

선행 프로젝트의 G3에 DIS 커버리지 검사를 더했다. golden에 DIS 완전일치
레코드가 없는 엔티티는 VR-Forces에서 실행 hang을 일으키므로, 파일을 쓰기
전에 잡는다.
"""
from __future__ import annotations

from ..gates import Violation
from .catalog import DisCatalog
from .golden import Golden
from .plan import balanced
from .spec import ScnxSpec


def check_g3(spec: ScnxSpec, golden: Golden,
             dis: DisCatalog) -> list[Violation]:
    out: list[Violation] = []
    uuids: set[str] = set()

    for e in spec.entities:
        if e.dis is None:
            out.append(Violation("G3", "C3.1",
                                 f"DIS 없음: {e.object_id} ({e.entity_class})"))
        elif golden.entity_by_dis(e.dis) is None:
            out.append(Violation("G3", "C3.2",
                                 f"golden 레코드 없음: {e.entity_class} {e.dis}"))
        if e.coord.is_zero():
            out.append(Violation("G3", "C3.3", f"좌표 미할당: {e.object_id}"))
        if e.uuid in uuids:
            out.append(Violation("G3", "C3.4", f"uuid 중복: {e.uuid}"))
        uuids.add(e.uuid)

    for c in spec.control_objects:
        if c.coord is not None and c.coord.is_zero():
            out.append(Violation("G3", "C3.3", f"좌표 미할당: {c.ref_id}"))
        if c.uuid in uuids:
            out.append(Violation("G3", "C3.4", f"uuid 중복: {c.uuid}"))
        uuids.add(c.uuid)

    known = uuids | {e.uuid for e in spec.entities}
    for oid, steps in spec.entity_plans.items():
        for s in steps:
            if s.pln is None:
                if s.issues:
                    out.append(Violation("G3", "C3.5",
                                         f"{oid} {s.event_id}: {'; '.join(s.issues)}"))
                continue
            if not balanced(s.pln):
                out.append(Violation("G3", "C3.6",
                                     f"괄호 불균형: {oid} {s.event_id}"))
            for r in s.refs:
                if r not in known:
                    out.append(Violation("G3", "C3.7",
                                         f"참조 미해결: {oid} {s.event_id} → {r}"))
    return out
```

- [ ] **Step 4: `writer.py`를 새 스펙 필드에 맞추기**

`VTMAK/vtmak/scnx/writer.py`는 `EntitySpec.name`·`.uuid`·`.dis`·`.coord`·`.faction`을 읽는다. 새 `EntitySpec`도 같은 필드명을 쓰므로 대부분 그대로 동작한다. 다음 세 곳만 확인·수정한다.

1. `_ascii_stem` / marking 생성부: `EntitySpec.name`이 한글 역할명("방어 보병 1")이 되었다. marking은 ASCII 11자 이하여야 하므로 **`object_id`를 marking으로 쓴다**(예: `FR-INF-001` = 10자, ASCII). 해당 부분을 `mark = e.object_id[:11]`로 바꾼다.
2. `_pln`: `PlanStep.pln`만 읽으므로 수정 불필요. `s.pln`이 `None`인 스텝은 건너뛰는지 확인한다.
3. `ControlObjectSpec.kind`가 항상 `"COORD"`이므로 `ROUTE` 분기는 타지 않는다. 그대로 둔다.

확인 명령:

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK"
grep -n "marking\|\.name\|_ascii_stem\|s.pln" vtmak/scnx/writer.py
```

- [ ] **Step 5: `scripts/04_compile_scnx.py` 작성**

```python
"""이벤트 → 확정 스펙 → PLN → .scnx (+G0, G3)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vtmak.gates import check_g0                              # noqa: E402
from vtmak.geometry import BattlefieldLayout                  # noqa: E402
from vtmak.parser import Event                                # noqa: E402
from vtmak.ranges import WeaponRanges                         # noqa: E402
from vtmak.registry import ClassMap, build_registry           # noqa: E402
from vtmak.scnx.catalog import DisCatalog, TaskCatalog        # noqa: E402
from vtmak.scnx.gates import check_g3                         # noqa: E402
from vtmak.scnx.golden import Golden                          # noqa: E402
from vtmak.scnx.spec import build_spec                        # noqa: E402
from vtmak.scnx.writer import get_writer                      # noqa: E402

CFG = ROOT / "config"
EVENTS = ROOT / "build" / "events" / "battle.jsonl"
OUT = ROOT / "build" / "scnx"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default=str(ROOT / "yewon_test" / "yewon_test.scnx"))
    ap.add_argument("--writer", choices=["template", "dir"], default="template")
    args = ap.parse_args()

    if not EVENTS.exists():
        print("build/events/battle.jsonl 없음 — 02를 먼저 실행할 것")
        return 1
    events = [Event(**json.loads(l))
              for l in EVENTS.read_text(encoding="utf-8").splitlines() if l]

    layout = BattlefieldLayout.load(CFG / "battlefield_layout.json")
    cmap = ClassMap.load(CFG / "entity_class_map.csv")
    ranges = WeaponRanges.load(CFG / "weapon_ranges.csv")
    dis = DisCatalog.load(CFG / "dis_catalog.csv")
    registry = build_registry(events, cmap, layout.static_ids())

    g0 = check_g0(events, registry, layout, ranges)
    blocking = [v for v in g0 if v.code in ("C0.1", "C0.2")]
    for v in g0:
        print(f"  [{v.gate}/{v.code}] {v.detail}")
    if blocking:
        print(f"G0 차단 {len(blocking)}건 — 레이아웃을 고칠 것")
        return 1

    spec = build_spec(events, registry, layout,
                      TaskCatalog.load(CFG / "task_catalog.csv"),
                      dis, ranges, scenario_id="battle")
    g3 = check_g3(spec, Golden.load(args.golden), dis)
    for v in g3:
        print(f"  [{v.gate}/{v.code}] {v.detail}")
    if g3:
        print(f"G3 {len(g3)}건 — .scnx를 쓰지 않는다")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    out = get_writer(args.writer, args.golden).write(spec, OUT)
    print(f"엔티티 {len(spec.entities)} · 통제점 {len(spec.control_objects)} · "
          f"플랜 {sum(1 for v in spec.entity_plans.values() if any(s.pln for s in v))}")
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/test_writer.py -v`
Expected: PASS (4 passed)

- [ ] **Step 7: 전체 파이프라인 실행**

Run:
```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK"
python scripts/02_parse_events.py && python scripts/03_build_timetable.py && python scripts/04_compile_scnx.py; echo "exit=$?"
```
Expected: 세 스크립트 모두 `exit=0`. `build/scnx/battle.scnx`가 생성되고 엔티티 328이 보고된다.

- [ ] **Step 8: 커밋**

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments"
git add new_VTMAK/vtmak/scnx new_VTMAK/scripts/04_compile_scnx.py new_VTMAK/tests/test_writer.py
git commit -m "feat(new_vtmak): .scnx 저작과 G3 정합성 검증"
```

---

### Task 11: 전체 검증과 문서

**Files:**
- Create: `new_VTMAK/README.md`
- Modify: `docs/superpowers/specs/2026-08-02-new-vtmak-scnx-pipeline-design.md` (구현 중 드러난 사실 반영)
- Test: 전체 테스트 스위트

- [ ] **Step 1: 전체 테스트 실행**

Run: `cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK" && python -m pytest tests/ -v`
Expected: 전부 PASS. 실패가 있으면 이 단계에서 멈추고 원인을 보고할 것 — 테스트를 느슨하게 고쳐서 통과시키지 말 것.

- [ ] **Step 2: 결정성 확인**

같은 입력으로 두 번 돌려 산출물이 바이트 단위로 같은지 본다.

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments/new_VTMAK"
python scripts/02_parse_events.py >/dev/null && cp build/events/battle.jsonl /tmp/a.jsonl
python scripts/02_parse_events.py >/dev/null && diff -q /tmp/a.jsonl build/events/battle.jsonl && echo "이벤트 결정적"
python scripts/04_compile_scnx.py --writer dir >/dev/null && cp -r build/scnx /tmp/scnx_a
python scripts/04_compile_scnx.py --writer dir >/dev/null && diff -r /tmp/scnx_a build/scnx && echo "스펙 결정적"
```

- [ ] **Step 3: `new_VTMAK/README.md` 작성**

```markdown
# new_VTMAK

`scenario_v3.txt` → VR-Forces 4.9 `.scnx` 자동 생성 파이프라인.

설계 근거: `../docs/superpowers/specs/2026-08-02-new-vtmak-scnx-pipeline-design.md`

## 실행

```bash
python scripts/02_parse_events.py       # 원문 → 이벤트 (+G1, G0)
python scripts/03_build_timetable.py    # 이벤트 → 타임테이블 (+G2)
python scripts/04_compile_scnx.py       # 스펙 → PLN → .scnx (+G0, G3)
```

산출: `build/scnx/battle.scnx` (약 7분, 328객체)

## VR-Forces에서 열 때 (필수)

**Ground Clamping을 반드시 켤 것.** 객체 좌표는 위경도만 결정적이고 고도는
0이라, 켜지 않으면 지형에 따라 땅속이나 공중에 배치된다.

1. `Settings → Ground Clamping`
2. **Ground Clamping Cutoff Distance Scale을 최대로**

## 입력

파이프라인이 읽는 시나리오 입력은 `scenario_original/scenario_v3.txt` **단독**이다.
`시나리오_원문.md`와 배치도 PNG는 사람이 보는 참고 자료이며 코드가 참조하지 않는다.

## config

| 파일 | 내용 |
|---|---|
| `battlefield_layout.json` | 지명 27개 로컬 미터 좌표 + 정적객체 바인딩 |
| `weapon_ranges.csv` | 모델 → 직접/간접 사거리 |
| `pattern_map.csv` | 문장 템플릿·이동행동 → STKG 술어 + task_kind |
| `entity_class_map.csv` | 모델 → type_group + 무기명 |
| `dis_catalog.csv` | 모델 → DIS 7튜플 (26종) |
| `task_catalog.csv` | (type_group, 행동) → `.pln` S-expression 템플릿 |

## 지형이 좁아 배치가 안 들어갈 때

`battlefield_layout.json`의 `scale`을 낮춘다. **0.71 미만으로 낮추면** M109
최소사거리 2 km가 깨져 G0가 차단한다. 그게 축소 하한이다.

## 검증 게이트

| 게이트 | 조건 |
|---|---|
| G0 | 모든 교전 쌍이 사거리 안. 미확인 무기체계(Patriot 2종)는 별도 보고 |
| G1 | 3,000문장 전부 매칭. 예외는 원문 절단 1건뿐 |
| G2 | task 가능 328객체 전원 플랜 보유 |
| G3 | DIS·좌표·uuid·괄호·참조 정합성 |
```

- [ ] **Step 4: 스펙 문서에 실측 반영**

구현 중 예상과 달랐던 값(엔티티 수, 통제점 수, G0 보고 건수, `scale` 하한 등)을 설계 스펙에 반영한다. 예상과 전부 같았다면 "구현으로 확인됨" 한 줄만 §9 뒤에 덧붙인다. **추측으로 채우지 말고 실제 실행 출력을 근거로 적을 것.**

- [ ] **Step 5: 커밋**

```bash
cd "C:/Users/user/OneDrive/문서/Cybermarine system lab/STKG/STKG_Experiments"
git add new_VTMAK/README.md docs/superpowers/specs/2026-08-02-new-vtmak-scnx-pipeline-design.md
git commit -m "docs(new_vtmak): README와 스펙 실측 반영"
```

---

## 실행 후 남는 것 (이 계획의 범위 밖)

1. **Ala Moana 지형 커버리지 확인.** 생성된 `battle.scnx`를 VR-Forces에서 열어 6.8 × 4.0 km 배치가 지형 안에 들어가는지 눈으로 볼 것. 벗어나면 `scale`을 낮춘다(하한 0.71).
2. **Patriot 2종(M901 / MIM-104)의 지상 간접사격.** G0가 `C0.3 UNVERIFIED`로 보고한다. VR-Forces에서 실제로 태스크가 도는지 확인한 뒤 `weapon_ranges.csv`의 `unverified`를 0으로 내리고 사거리를 채울 것.
3. **Data Logger 수집 → STKG.** 정적 객체 7개는 시뮬레이션에 실체가 없어 Data Logger에 남지 않는다(설계 스펙 §5.3). 탄착 21건은 `build/events/battle.jsonl`에서 가져와 합쳐야 한다.
