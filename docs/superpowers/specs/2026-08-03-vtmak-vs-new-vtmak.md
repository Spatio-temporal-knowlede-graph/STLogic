# VTMAK → new_VTMAK 차이 정리

작성일 2026-08-03. 실측 기준.

## 0. 한 줄

`VTMAK`은 PDF 원문 14구간을 사람이 만든 사전으로 해석해 `.scnx` 14개를 냈다.
`new_VTMAK`은 시나리오 원문 하나를 자동 생성한 사전으로 해석해 `.scnx` 하나를
내고, 여기에 **시뮬레이터가 돌린 결과를 되받아 STKG로 만드는 단계**가 붙었다.

| | VTMAK | new_VTMAK |
|---|---|---|
| 저장소 | `cms-stkg/VTMAK.git` (5커밋) | `Spatio-temporal-knowlede-graph/VR-Forces.git` |
| 파이썬 | 35개 · 3,720줄 | 53개 · 6,091줄 |
| 설정 파일 | 12개 | 8개 |
| 입력 | `scenario_src/` 14개 · 613줄 | `scenario_original/scenario.txt` 1,294줄 |
| 산출 | `.scnx` 14개 (일자별) | `.scnx` 1개 + STKG CSV 5개 |

## 1. 파이프라인

```
VTMAK      00_mine_registry → 01_extract_text → 02_parse_events
           → 03_build_timetable → 04_compile_scnx → 05_build_campaign
           (+ harvest_golden, make_terrain_probe)

new_VTMAK  01_harvest_layout → 02_parse_events → 03_build_timetable
           → 04_compile_scnx → 05_data_postprocessing
```

`00_mine_registry`와 `01_extract_text`가 사라졌다. PDF 추출과 사전 채굴을 따로
돌리지 않고 `02_parse_events`가 원문에서 직접 객체 사전을 만든다.

`05_data_postprocessing`은 방향이 반대다. 앞의 넷은 원문 → 시뮬레이터지만
05는 시뮬레이터 → 데이터셋이다.

## 2. 사전을 사람이 쓰지 않는다

가장 큰 차이다. VTMAK의 설정은 사람이 채워 넣는 어휘 사전이었다.

```
action_lexicon.csv / .candidates.csv     행위 어휘
entity_registry.csv / .candidates.csv    객체 명부
location_registry.csv / .candidates.csv  지명 명부
state_lexicon.csv / .candidates.csv      상태 어휘
primitive_map.csv                        원시 동작 매핑
action_task_map.csv                      행위 → VR-Forces task
```

`.candidates` 짝이 있는 것은 `00_mine_registry`가 후보를 뽑아 주면 사람이
고르는 구조였다는 뜻이다.

new_VTMAK은 이것을 전부 버리고(`1d6c275` "원문에서 객체 사전 자동 생성
(335객체, 수작업 사전 폐기)") 문장 틀만 남겼다.

```
pattern_map.csv          문장 틀 → 이벤트 (parser.py가 쓴다)
entity_class_map.csv     객체 접두 → DIS 모델
weapon_ranges.csv        무기 사거리 (G0가 쓴다)
battlefield_layout.json  지명 29 + 정적 표적 7
layout_rules.json        golden 통제점에서 지명을 미는 규칙
fixed_objects.json       고정 객체
task_catalog.csv         VR-Forces task 문법
dis_catalog.csv          DIS 열거값
```

객체 명부는 산출물이지 입력이 아니다.

## 3. 좌표계가 생겼다

VTMAK은 `map_pack.json`과 `vtmak/scnx/geometry.py`로 `.scnx` 저작 때만
좌표를 다뤘다.

new_VTMAK은 `vtmak/geometry.py`를 최상위로 올려 로컬 미터 전장 좌표계를
세웠다(`30f96d9`). `01_harvest_layout.py`가 golden 시나리오의 통제점에서 지명
좌표를 수확하고, `layout_rules.json`의 규칙으로 파생 지점을 민다. 고도가
0이 아니라 golden 지형점에서 온다(1~95m).

이 좌표계가 없으면 05의 후처리도 못 한다. 시뮬레이터가 뱉은 ECEF 좌표를
지명으로 되돌리는 일(`stkg/locate.py`)이 여기 기댄다.

## 4. 게이트가 늘었다

| 게이트 | VTMAK | new_VTMAK | 내용 |
|---|---|---|---|
| G0 | — | 있음 | 무기 사거리. 사수-표적 거리가 사거리를 넘는 교전을 잡는다 |
| G1 | 있음 | 있음 | 파싱. 문장이 틀에 맞는가 |
| G2 | 있음 | 있음 | 타임테이블 커버리지 |
| G3 | 있음(scnx) | 있음 | `.scnx` 정합성 |

G0은 `ranges.py` + `weapon_ranges.csv`가 받친다. 사거리를 확인 못 한 무기는
추정치를 넣지 않고 `UNVERIFIED`로 따로 표시한다(`b9cd3aa`).

## 5. 명부 감축

new_VTMAK에만 있다(`vtmak/roster.py`, `config/roster.json`). 원문의 335개
객체를 전부 넣으면 VR-Forces가 느려서, 부대별로 솎되 교전 구조는 보존한다.
task를 만드는 이벤트가 있는 객체는 남긴다.

## 6. STKG 후처리 — 전부 새것

VTMAK에는 대응물이 없다. 시뮬레이터를 돌린 뒤 나온 CSV를 데이터셋으로
바꾸는 단계다.

```
vtmak/stkg/rewrite.py     행 하나의 (predicate, object)를 정한다. 인프라 제외
vtmak/stkg/firing.py      발사체 → 사수 확정
vtmak/stkg/predicate.py   시뮬레이터 술어 원문 파싱
vtmak/stkg/locate.py      좌표 → 지명
vtmak/stkg/filter.py      시뮬레이터 인프라 객체 판정
vtmak/stkg/resolve.py     uuid → marking
```

열은 내보내기가 준 8열을 유지한다 — `subject, predicate, object, latitude,
longitude, timestamp, source, CID`.

설계는 [`2026-08-03-stkg-relation-expansion-design.md`](2026-08-03-stkg-relation-expansion-design.md).

## 7. 규모 실측

| | VTMAK | new_VTMAK |
|---|---|---|
| 이벤트 | 구간별 37~53건 (14파일) | 1,259건 (1파일) |
| 타임테이블 | 구간별 | 671행 |
| `.scnx` 객체 | — | 142 |
| `.scnx` 태스크 | — | 283 |
| STKG 후처리 | — | 121,646행 + 드론 4파일 |

## 8. 결정성

new_VTMAK은 같은 입력이면 같은 바이트가 나오는 것을 계약으로 둔다
(`test_writer.py::test_output_is_byte_identical_across_runs`). VTMAK에는
이 계약이 없었다.

## 9. 이번 세션의 변경 (new_VTMAK 안에서)

### 추가

- `vtmak/stkg/rewrite.py` — 8열 유지 후처리. 술어 정규형, object 채움,
  인프라 행 제거
- `vtmak/stkg/firing.py` — 발사체 → 사수를 **확정만** 한다
- `scripts/05_data_postprocessing.py` — 재작성
- `tests/test_stkg_rewrite.py` (10건), `tests/test_stkg_firing.py` (8건)

### 삭제

- `vtmak/stkg/collapse.py` · `derive.py` · `export.py`와 그 테스트 3개
  (구간 축약과 최근접 추론 방식 폐기)
- `config/munition_map.csv` (`firing.py`가 무기명을 안 쓴다)

### 고침

- `.gitignore`에서 `build/` 제거. `build/csv`는 VR-Forces 내보내기 원본이라
  스크립트로 복원할 수 없는데 무시되고 있었다. 16개 파일이 추적으로 들어갔다
- `config/layout_rules.json` · `roster.json` · `fixed_objects.json` 복원.
  작업 트리에서만 지워져 있어 테스트 67건이 오류였다

### 결과

후처리 `ground_truth` 126,718행 → 121,646행(인프라 5,072행 제거), 술어별
`move to` 59,516 · `Follow-Entity` 31,920 · `none` 29,237 ·
`FFE-on-Location` 868 · `fired_by` 104 · `find_cover` 1.

테스트 201 통과 / 1 실패. 남은 실패는
`test_roster.py::test_preserves_every_engagement_kind`로, 복원한 `roster.json`과
현재 시나리오가 어긋나 `FR-M109`·`FR-MORT` 교전 종류가 명부 감축에서 빠지는
문제다. 이번 작업과 무관하다.
