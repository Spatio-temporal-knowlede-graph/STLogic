# new_VTMAK — 시뮬레이터 CSV → STKG 관계 추출 설계

작성일: 2026-08-03
대상 디렉터리: `new_VTMAK/`
선행 문서: `2026-08-02-new-vtmak-scnx-pipeline-design.md`

---

## 1. 목적

VR-Forces에서 뽑은 CSV를 **주어–술어–목적어(S-P-O) 관계 테이블**로 바꾼다.

원문은 객체 간 상호작용을 서술하도록 작성됐고 파서까지 그 정보가 살아서 온다.
그런데 최종 CSV의 `object` 열이 **전 행 `-`** 라 지식그래프가 성립하지 않는다.
상호작용을 잃는 지점을 찾아 복원하는 것이 이 작업의 전부다.

---

## 2. 현재 상태 (2026-08-03 실측)

### 2.1 입력 파일

| 파일 | 크기 | 행 | subject | 시각 |
|---|---|---|---|---|
| `ground_truth_20260803_dataset.csv` | 53.2MB | 478,360 | 287 | 05:20:00 ~ 07:25:15 Z |
| `UAV 1_20260803_dataset.csv` | 7.1KB | 53 | 9 | 22:00:06 ~ 22:04:18 Z |
| `UAV 2_20260803_dataset.csv` | 309KB | 2,278 | 54 | 22:00:04 ~ 22:07:02 Z |
| `UAV 3_20260803_dataset.csv` | 84KB | 604 | 46 | 22:00:00 ~ 22:05:05 Z |
| `UAV 4_20260803_dataset.csv` | 79KB | 572 | 47 | 22:00:00 ~ 22:06:59 Z |

공통 스키마: `subject,predicate,object,latitude,longitude,timestamp,source,CID`

### 2.2 이 CSV는 현재 빌드의 산출물이 아니다

```
신 battle.oob (16:01)  엔티티 141 · 통제점  0
구 battle.oob (15:41)  엔티티  90 · 통제점  0
CSV ground_truth       엔티티 167 · 통제점 41 (P1~P41)
```

GT가 신 빌드를 **완전히 포함**하고 26기(`ENINF036~054`, `FRCMD001`,
`ENCAESAR004` 등)와 통제점 41개를 더 갖는다. 명명 규칙이 같으므로 같은
파이프라인의 **더 이른 빌드**(명부 감축 전 · 통제점 저작 시절)다.

스키마 문제는 빌드와 무관하게 성립하므로 A단계는 이 CSV로 진행한다. 다만
**최종 검증은 현재 빌드로 다시 뽑은 CSV로 한다.**

### 2.3 상호작용을 잃는 두 지점

**1단계 원문 → 이벤트: 정상.** 138건의 명시적 교전쌍이 살아 있다.

```
directFireAt  25건   FR-INF-001 (US Army M4) → EN-INF-001 (Russian Soldier AK47)
hitBy         25건   actor + source_obj
engAttacker   50건   "공격자 객체는 FR-MORT-001이고, 목표 객체는 EN-FP-001이다"
engSource     38건   "피격 원천 객체는 FR-M109-001이고, 피격 대상 객체는 EN-FP-001이다"
```

**2단계 이벤트 → PLN: 1차 손실.** `battle.pln` 282개 태스크 중 엔티티를
참조하는 것은 63개(22%)뿐이다.

| 태스크 | 수 | 대상 |
|---|---|---|
| `move-to-location-task` | 173 | 좌표 |
| `follow-entity` | 38 | **엔티티 UUID** |
| `provide_suppressive_fire_loc` | 25 | 좌표 |
| `find_cover` | 25 | **엔티티 UUID** (Threat) |
| `ffe-on-location` | 13 | 좌표 |

직접사격 태스크가 **0개**다. `spec.py`의 `suppression_events()`가 "표적이
나중에 제압 상태가 됨"을 근거로 `directFireAt` 25건을 전부 `제압사격`
(`provide_suppressive_fire_loc`)으로 재분류하고, 그 템플릿은 표적을 좌표로만
받는다. `plan.py:31`의 `("fire_direct","ENTITY") → 대상 직접사격` 경로가
존재하지만 도달하지 않는다.

`engAttacker` 50건 + `engSource` 38건은 `pattern_map.csv`에서 `noop`이라
파이프라인 입구에서 버려진다.

> 실패 중인 테스트 `test_spec.py::test_infantry_direct_fire_targets_an_entity`,
> `test_writer.py::test_ak47_infantry_fires_with_ak47`가 정확히 이것을 잡고
> 있다. B단계가 이 둘을 통과시킨다.

**3단계 PLN → CSV: 2차 손실.** 내보내기가 `object` 열을 채우지 않는다.
엔티티가 이미 `predicate` 문자열 안에 있는데도 그렇다.

```
None                                      328,240  (68.6%)
Move to {...}                              95,444
Follow-Entity Entity: "ENINF001" ...       46,976   ← 엔티티 있음
Follow-Entity Entity: "ENSA7001" ...        4,863   ← 엔티티 있음
FFE-On-Location "Location=..."              2,605
Target-entity task: 2c380775-b3d4-...         175   ← 엔티티 UUID 있음
Move-To Waypoint: "62f22b9c-..."               30   ← UUID 있음
find_cover: ChooseFiringPosition=False;...      2
suppressed_prone                               25
```

**52,044행(10.9%)이 이미 대상 엔티티를 품고 있다.** 파싱만 하면 복구된다.

### 2.4 그 밖의 결함

| 결함 | 규모 | 처리 |
|---|---|---|
| GT와 UAV 시간대 불일치 (05:20~07:25 vs 22:00~22:07) | 겹침 0초 | **이 스펙 범위 밖.** §10 참조 |
| 1970-01-01 epoch 타임스탬프 | 197행 (UAV2 182, UAV3 15) | A단계에서 격리·보고 |
| 완전중복 행 | 260,877행 (54.5%) | 구간 축약(§7)이 흡수 |
| `CID`가 GT에서 전부 `-1` | 478,360행 | 관계 테이블이 대체 (§10) |
| GT 샘플링 공백 | 1,058초 · 215초 | 보고만 |

내보내기 코드는 이 저장소에 없다. `GROUND_TRUTH`·`CID` 문자열로 전수 검색해도
나오지 않는다. VR-Forces 플러그인 쪽으로 보이며 C단계에서 다룬다.

---

## 3. 결정 사항 (사용자 확정, 2026-08-03)

**제거** — `1 Force`, `2 Force`, `3 Force`, `Observer 1`, `GlobalEnv 1`,
관계 복원 불가능한 E 계열 효과 객체

**관계 어휘 유지** — `fires_at`, `suppresses`, `moves_to`, `moves_along`,
`follows`, `takes_cover_from`, `engages`, `observes`, `resupplies`,
`fired_by`, `detonated_at`

**별도 위치 테이블로 이동** — `None`, 일반 위치 스냅샷, 발사체 매 tick 궤적

**후속 범위** — `embark`, `disembark`, `send-radio`

**구현 순서** — A(기존 CSV 후처리) → B(PLN 의미 매핑) → C(ObjectManager 실시간
관계 추출) → D(원문 파서 확장)

**추가 승인** — 관계를 tick이 아니라 **구간**으로 담는다. `detonated_at`은
어휘에 예약하되 **C단계로 미룬다**.

---

## 4. 출력 스키마

산출물을 두 테이블로 나눈다. 관계와 위치는 갱신 주기도 소비 방식도 다르다.

### 4.1 `build/stkg/relations.csv`

```
subject, predicate, object, object_type, t_start, t_end, source, confidence, evidence
```

| 열 | 값 | 설명 |
|---|---|---|
| `subject` | marking | 관계의 주체 |
| `predicate` | 어휘 11종 (§5) | 정규화된 관계명 |
| `object` | marking / 지명 / route명 / 좌표 | 관계의 대상 |
| `object_type` | `entity` `location` `waypoint` `route` `coord` | 소비 쪽 분기용 |
| `t_start` `t_end` | ISO8601 | 관계가 성립한 구간 |
| `source` | `GROUND_TRUTH` / `UAV n` | 관측 주체 |
| `confidence` | `observed` / `inferred` | 태스크에서 직접 읽었는가, 추론했는가 |
| `evidence` | 자유 문자열 | 원본 predicate, 매칭 거리 등 검증 근거 |

`confidence`를 두는 이유: `fired_by`는 최근접 매칭으로 만든 **추론**이고
`follows`는 태스크에 적힌 **사실**이다. 둘을 같은 신뢰도로 쓰면 안 된다.

`evidence`를 두는 이유: 추출이 틀렸을 때 원본으로 되짚을 수 없으면 디버깅이
불가능하다. 좌표 스냅 거리, 원본 predicate 문자열을 남긴다.

### 4.2 `build/stkg/positions.csv`

```
subject, kind, latitude, longitude, timestamp, source
```

`kind`는 `entity` / `projectile`. `predicate=None` 328,240행과 발사체 매 tick
궤적이 전부 여기로 간다.

### 4.3 `build/stkg/report.md`

추출 결과 요약. 제외한 행 수, 관계별 건수, 좌표 스냅 3단계별 비율, 미해결
항목. **조용히 버리는 데이터가 없도록** 모든 감축을 여기 적는다.

---

## 5. 관계 어휘

| predicate | 출처 | object_type | 단계 |
|---|---|---|---|
| `follows` | `Follow-Entity Entity: "X"` 파싱 | entity | **A** |
| `moves_to` | `Move to {x,y,z}` 좌표 스냅 | location / coord | **A** |
| `moves_to` | `Move-To Waypoint: "uuid"` | waypoint | **A** |
| `engages` | `Target-entity task: uuid` | entity | **A** |
| `takes_cover_from` | `find_cover` Threat UUID | entity | **A** |
| `suppresses` | `provide_suppressive_fire_loc` 좌표 | location | **A** |
| `fires_at` | `FFE-On-Location` 좌표 | location | **A** |
| `fired_by` | 발사체 최근접 + 무기 정합 (§8) | entity | **A** |
| `fires_at` | `fire-at-target` TARGET_UUID | **entity** | **B** |
| `moves_along` | `move-along-route` route UUID | route | **B** |
| `observes` | 원문 관측 서술 | entity | **D** |
| `resupplies` | 원문 보급 서술 | entity | **D** |
| `detonated_at` | 소멸 이벤트 | location | **C** (예약) |

UUID는 전부 `.oob`의 `marking-text`로 되짚어 사람이 읽을 수 있는 값으로
내보낸다. UUID를 그대로 두면 다른 산출물과 조인할 수 없다.

### `detonated_at`을 C로 미루는 근거

현재 데이터로 만들 근거가 없다. 유일한 후보였던 E 계열이 복원 불가로 판정됐고
(§6.2), 발사체 궤적의 마지막 좌표를 탄착점으로 삼는 대안은 궤적이 있는 8종만
가능하다. 나머지 4종(`M107 3/4/6`, `M933HE 5`)은 고유 좌표가 1개뿐이라 발사
직후 소멸한 것으로 보인다. C단계에서 소멸 이벤트를 직접 받는 편이 정확하다.

---

## 6. 제외 대상

### 6.1 시뮬레이터 인프라 — 무조건 제거

| subject | 종 | 행 | 근거 |
|---|---|---|---|
| `1 Force` `2 Force` `3 Force` | 3 | 12,434 | 조직 트리 노드. 좌표가 전부 `(42.32429274, 45.00000000)` 고정 쓰레기값 — 전장은 하와이(21.3°N, -157.7°E) |
| `Observer 1` | 1 | 4,830 | 관측 카메라 |
| `GlobalEnv 1` | 1 | 3,385 | 전역 환경 |

합계 **20,649행(4.3%)**. 원문에 등장하지 않고 물리 객체도 아니다.

### 6.2 E 계열 — 복원 불가로 확정, 전량 제거

`E1`~`E62`, 62종 3,720행. 판정 근거는 셋이다.

1. **62종 전부가 `07:13:22` 한 시각에 동시 등장한다.** 탄착이라면 사격 시각에
   흩어져야 한다.
2. **각자 고유 위치 1개에서 움직이지 않는다.**
3. **서로 2m~3,659m로 흩어져 있고 FFE 표적 좌표는 12개뿐이다.** 62개 위치를
   12개 사격과 짝지을 수 없다.

탄착 효과가 아니라 일괄 스폰이다. 어떤 관계도 복원할 수 없다.

### 6.3 유지

| subject | 종 | 행 | 이유 |
|---|---|---|---|
| `P1`~`P41` | 41 | 2,460 | 통제점. §7 좌표 스냅의 **object 후보** |
| `M107 1~6` `M933HE 1~5` `PAC-3 1` | 12 | 1,942 | 발사체. `fired_by` 관계 + 궤적 |

---

## 7. 이동 object 3단 폴백

재료가 셋 있다.

```
config/battlefield_layout.json   지명 29개 (golden 통제점 23 + 파생 6)
P1~P41                           통제점 41개, .oob에 좌표 보유
Move to {x,y,z}                  95,444행의 목적지 좌표
```

태스크 저작 시 지명 좌표를 **그대로** 넣으므로 최근접 탐색이 아니라 정확
일치로 대부분 해결된다. 오차가 나는 것은 `spec.jitter_offset()`으로 ±흩뿌린
개체별 좌표뿐이다.

```
1. 정확 일치   목적지 == battlefield_layout.json 지명 좌표  → 지명   (location)
2. 최근접      통제점 중 반경 50m 내 최근접                  → 통제점 (location)
3. 폴백        좌표 문자열 유지                              →        (coord)
```

3단계로 떨어지는 비율은 구현 후 실측해 `report.md`에 적는다. 임계 반경 50m는
초기값이며, 실측 분포를 보고 조정한다.

**2단계는 통제점이 있는 CSV에만 적용된다.** 현재 CSV에는 `P1`~`P41`이 있지만
현재 빌드는 통제점을 저작하지 않는다(§2.2). 통제점 목록은 CSV와 함께 주어진
`.oob`에서 읽고, 없으면 2단계를 건너뛰어 1 → 3으로 간다. 건너뛴 사실은
`report.md`에 적는다. 1단계가 대부분을 처리하므로 2단계 부재가 치명적이지는
않으나, 3단계 폴백 비율이 올라가는지 실측으로 확인한다.

이 폴백은 `moves_to`뿐 아니라 `suppresses`·`fires_at`의 좌표 object에도 같이
쓴다.

---

## 8. `fired_by` 추론 규칙

발사체의 **첫 관측 시각**에 같은 시각의 엔티티 중 최근접을 발사자로 본다.
2026-08-03 실측 결과다.

```
M107 1  → ENCAESAR002  19.7m      M933HE 1 → ENMORT002   89.0m
M107 2  → ENCAESAR004  14.4m      M933HE 2 → FRMORT001   45.7m
M107 3  → FRM109003     2.0m      M933HE 3 → ENMORT002    0.3m
M107 4  → FRM109001     1.3m      M933HE 4 → FRMORT003    0.7m
M107 5  → ENCAESAR002   6.1m      M933HE 5 → ENMORT003    0.4m
M107 6  → FRM109004     2.1m      PAC-3 1  → FRMORT001   19.1m  ← 오분류
```

155mm탄(M107)은 전부 자주포로, 박격포탄(M933HE)은 전부 박격포로 붙는다.
`PAC-3 1`만 박격포에 붙는데 패트리엇 요격탄이므로 틀렸다.

**따라서 최근접만으로는 부족하고 무기·탄약 정합성 검사를 함께 건다.**

```
M107     → 155mm 곡사포 (M109 / AHS Krab / CAESAR)
M933HE   → 박격포 (MO-120RT-61)
PAC-3    → 패트리엇 발사대 (M901 / MIM-104)
```

정합성 매핑은 `config/munition_map.csv`로 뺀다. 코드에 박지 않는다.

- 최근접 엔티티가 정합 조건을 만족하면 `confidence=inferred`로 관계 생성
- 만족하지 않으면 **관계를 만들지 않고** `report.md`에 미확정으로 적는다
- 매칭 거리는 `evidence`에 남긴다

---

## 9. 구간 축약

같은 `(subject, predicate, object, source)`가 연속되면 한 행으로 접고
`t_start`/`t_end`를 갖는다.

`Follow-Entity → ENINF001`이 46,976행이지만 실제로 표현하는 사실은 "누가
언제부터 언제까지 ENINF001을 따랐다"뿐이다. 지식그래프의 시간 표현으로도
구간이 정본이다.

이 축약이 §2.4의 완전중복 54.5%를 함께 흡수한다.

**끊김 처리**: GT 샘플링에 1,058초·215초 공백이 있다. 공백을 사이에 두고
같은 관계가 재개되면 **별도 구간으로 나눈다.** 이어붙이면 관측하지 않은
구간을 관측했다고 주장하게 된다. 임계값은 샘플링 주기(1초)의 3배인 3초로
두고, 실측 후 조정한다.

---

## 10. 이 스펙이 다루지 않는 것

**GT와 UAV의 시간대 불일치.** GT는 05:20~07:25, UAV는 22:00~22:07로 겹침이
0초다. 어떤 UAV 관측도 정답과 조인할 수 없어 관측 성능을 산출할 수 없다.
내보내기 쪽 시계 문제이므로 **C단계에서 다룬다.** A단계는 두 테이블을 각각
독립적으로 산출하며, 조인은 시계가 맞은 뒤에 가능하다.

**`CID` 평가.** GT의 `CID`가 전부 `-1`이라 UAV의 클러스터링(CID 1~4)을 평가할
정답 라벨이 없다. 관계 테이블의 `engages`·`fires_at`이 교전 구조를 담으므로
클러스터 정답의 대체 근거가 될 수 있다. 별도 작업으로 둔다.

**인접 작업 (별건, 유실 방지용 기록)**

- 이동 컨트롤러 없는 10기(박격포 5·대공화기 4·M901 1)에 이동 태스크 14개가
  배정돼 VR-Forces가 버리고 있다. GT에서 `Move to` 술어가 한 번도 나오지 않는
  것으로 확인됨. B단계에서 같이 처리하면 효율적이다.
- 간접사격 13발 중 12발이 최소사거리(2000m) 미만. 박격포 4발은
  `weapon_ranges.csv`의 `indirect_min_m=1100`이 VR-Forces 실측 2000m와 달라
  G0를 통과하고 있다.
- 모든 객체 reactive task(AI) off 요청 — 253개 항목 대상.

---

## 11. 코드 배치

기존 `vtmak/`를 건드리지 않고 새 패키지로 격리한다. A단계는 `.scnx` 재빌드도
재시뮬도 필요 없다.

```
vtmak/stkg/
  __init__.py
  filter.py      제외 대상 판정 (Force / Observer / GlobalEnv / E계열)
  predicate.py   predicate 문자열 → (predicate, object, object_type)
  locate.py      좌표 → 위치 객체 3단 폴백
  derive.py      fired_by 추론 (최근접 + 무기·탄약 정합)
  collapse.py    tick → 구간 축약
  export.py      두 테이블 + report.md 출력
scripts/06_stkg_export.py
config/munition_map.csv    탄약 ↔ 무기체계 정합 표
tests/test_stkg_*.py
```

각 모듈은 순수 함수로 두고 파일 입출력은 `export.py`와 스크립트에만 둔다.
`predicate.py`는 문자열만 받아 문자열을 돌려주므로 CSV 없이 단위 테스트할 수
있다.

### 단계별 범위

| 단계 | 건드리는 곳 | 재시뮬 |
|---|---|---|
| **A** 기존 CSV 후처리 | `vtmak/stkg/` 신규 | 불필요 |
| **B** PLN 의미 매핑 | `plan.py` `spec.py` `pattern_map.csv` | 필요 |
| **C** ObjectManager 실시간 추출 | 저장소 밖 (VR-Forces 플러그인) | 필요 |
| **D** 원문 파서 확장 | `parser.py` `pattern_map.csv` | 필요 |

---

## 12. 검증

TDD로 간다. 각 모듈에 실패하는 테스트를 먼저 쓴다.

**단위**

- `predicate.py` — 어휘 9종 각각에 대해 실제 GT 문자열 표본을 넣어
  `(predicate, object, object_type)`이 나오는지. 파싱 실패는 예외가 아니라
  `None`을 돌려주고 호출부가 집계한다.
- `locate.py` — 지명 정확 일치 / 통제점 50m 내 / 폴백 세 경로 각각.
- `derive.py` — `PAC-3 1 → FRMORT001`이 정합성 검사에 걸려 **관계가 생기지
  않는** 것을 못박는다. 이 케이스가 회귀 방지의 핵심이다.
- `collapse.py` — 공백을 사이에 둔 같은 관계가 두 구간으로 나뉘는지.

**통합**

- 제외 대상 5부류가 출력에 하나도 없다.
- `relations.csv`의 모든 `object`가 비어 있지 않다. (`object_type=coord`
  폴백 포함)
- `object_type=entity`인 모든 `object`가 `.oob`의 marking에 존재한다.
- **회계 검사** — 입력 CSV의 모든 행이 정확히 한 갈래로 간다.

  ```
  입력 행 수 = 관계 기여 행(축약 전) + 위치 테이블 행 + 제외 행 + 격리 행
  ```

  구간 축약 때문에 `relations.csv`의 행 수와는 같지 않다. 축약 전 단계에서
  세고, 각 행이 어느 갈래로 갔는지 태그를 붙여 집계한다. **합이 맞지 않으면
  실패한다.** 조용한 유실을 막는 것이 목적이다.
- 파싱 실패로 어느 갈래에도 못 간 행은 `report.md`에 원본 predicate와 함께
  적는다. 0건이 목표지만 0건을 가정하지는 않는다.

**보고**

`report.md`에 좌표 스냅 3단계 비율, 관계별 건수, 미확정 `fired_by`, 격리한
1970 epoch 197행을 적는다.

---

## 13. 미해결

- 좌표 스냅 임계 반경 50m와 구간 끊김 임계 3초는 초기값이다. A단계 실측 후
  확정한다.
- `Move-To Waypoint`의 UUID 4종이 `.oob`의 어느 객체인지 아직 대조하지
  않았다. A단계 구현 중 확인한다.
- `Target-entity task: M933HE 2`처럼 발사체를 표적으로 삼는 행이 24건 있다.
  요격으로 보이나 `engages`로 낼지 별도 술어로 낼지 미정.
