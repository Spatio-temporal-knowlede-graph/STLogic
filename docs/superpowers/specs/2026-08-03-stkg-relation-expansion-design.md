# 시뮬레이터 CSV 후처리 설계 — 8열을 유지한 채 술어와 object를 채운다

작성일 2026-08-03. 대상: `new_VTMAK/scripts/05_data_postprocessing.py`.

## 0. 열 계약

시뮬레이터 내보내기가 준 **8열만** 쓴다.

```
subject, predicate, object, latitude, longitude, timestamp, source, CID
```

파생 정보를 열로 붙이지 않는다. 열을 늘리면 원본과 대조가 안 되고, STKG
쪽에서 어느 열이 관측이고 어느 열이 우리가 만든 것인지 매번 되물어야 한다.
판정 근거와 임계값은 열이 아니라 보고서(`build/stkg/report.md`)에 적는다.

## 1. 무엇을 고치는가

내보내기는 대상을 `predicate` 문자열 안에 박아 두고 `object` 열은 전 행 `-`로
비워 놓는다. 05는 그 둘만 고친다.

| 원문 | predicate | object |
|---|---|---|
| `Move to {좌표}` | `move to` | 좌표를 붙인 지명 |
| `Follow-Entity Entity: "X"` | `Follow-Entity` | `X` |
| `FFE-On-Location "Location={좌표}"` | `FFE-on-Location` | 좌표를 붙인 지명 |
| `find_cover: ... Threat=X; ...` | `find_cover` | `X` |
| `None` | `none` | 비움 |
| (발사체 행) | `fired_by` | 확정된 사수. 못 하면 비움 |

정규형이 없는 술어는 원문을 그대로 두고 보고서에 건수와 함께 적는다.
조용히 버리지 않는다.

## 2. 행은 인프라 객체만 지운다

시뮬레이터 인프라(`N Force`, `Observer N`, `GlobalEnv N`)는 원문 시나리오에
없고 물리 객체도 아니다. `Force` 노드는 좌표까지 (42.32429274, 45.0) 고정
쓰레기값이다. 실측 `ground_truth` 5,072행.

이름을 나열하지 않고 번호를 패턴으로 받는다. VR-Forces가 몇 개를 만드는지는
세션마다 다르다 — 실측에서 `Observer`가 하나인 줄 알고 `Observer 1`만
적었더니 다음 내보내기에 `Observer 2`가 생겨 767행이 관측 데이터인 척
새어 들어갔다.

입력 행 수 != 출력 행 수 + 삭제 행 수이면 종료 코드 1이다.

## 3. fired_by는 확정만 한다

최근접 엔티티를 발사자로 보는 방식은 못 쓴다. 실측에서 `M933HE 1`의 포구
최근접 1등(26.7m)과 2등(32.2m)이 5.5m 차이다. 서로 **독립인 신호 셋**이 같은
짝을 가리킬 때만 채운다.

1. **태스크 종료** — 사수의 FFE가 발사체 첫 관측 전에 끝났고 그 뒤로 없다.
   FFE가 계속 도는 사수는 아직 안 쏜 것이다(실측 `ENMORT003`은 08:16:16까지
   FFE가 살아 있고 발사체가 없다).
2. **탄착점** — 발사체 마지막 위치가 그 사수의 FFE 표적에 가장 가깝고,
   2등과 3배 **그리고** 50m 이상 벌어진다. 배수만 걸면 1등이 0.0m일 때 어떤
   2등이든 통과한다.
3. **포구** — 발사체 첫 위치 기준 최근접 사수도 같은 사수다.

여기에 1:1을 걸어 한 사수가 두 발을 갖지 못하게 한다. 하나라도 어긋나면
`object`를 비우고 사유를 보고서에 적는다.

짝짓기는 `source`별로 따로 돈다. 같은 발사체가 여러 관측자에게 보이므로
(실측 `M933HE 1`이 `GROUND_TRUTH`와 `UAV 2` 양쪽에 있다) 섞으면 다른 시각대의
관측이 하나로 이어진다.

FFE 무기명과 발사체 이름은 대조하지 않는다. 실측에서 무기명이 `m9333he`,
발사체가 `M933HE`라 철자가 다르다. 같은 것을 가리키는 게 뻔해 보여도 다른
두 문자열을 같다고 우기면 그건 추론이다.

## 4. 실측 결과 (2026-08-03)

| 파일 | 입력 | 출력 | 삭제 | object 채움 | fired_by 확정 |
|---|---:|---:|---:|---:|---|
| `ground_truth` | 126,718 | 121,646 | 5,072 | 92,409 | 4/4 |
| `UAV 1` | 1,227 | 1,227 | 0 | 683 | — |
| `UAV 2` | 1,281 | 1,281 | 0 | 800 | 0/3 |
| `UAV 3` | 609 | 609 | 0 | 576 | — |
| `UAV 4` | 688 | 688 | 0 | 656 | — |

`ground_truth` 술어별: `move to` 59,516 · `Follow-Entity` 31,920 · `none`
29,237 · `FFE-on-Location` 868 · `fired_by` 104 · `find_cover` 1.

검산: 원본 `None` 34,413 = 인프라 5,072 + 발사체 104 + 남은 `none` 29,237.

`UAV 2`의 발사체 3개는 그 드론이 사수의 FFE를 못 봐서 확정되지 않았다.
`object`를 비운 채로 둔다.

## 5. 구조

```
vtmak/stkg/rewrite.py    행 하나의 (predicate, object)를 정한다. 인프라 제외.
vtmak/stkg/firing.py     발사체 → 사수 확정. 신호 셋과 1:1.
vtmak/stkg/predicate.py  원문 술어 파싱 (기존)
vtmak/stkg/locate.py     좌표 → 지명 (기존)
vtmak/stkg/filter.py     인프라 판정 (기존)
vtmak/stkg/resolve.py    uuid → marking (기존)

scripts/05_data_postprocessing.py
    파일 목록을 돌며 rewrite를 부르고, 행 회계를 확인하고, 보고서를 쓴다.
```

테스트는 `tests/test_stkg_rewrite.py`(10건)와 `tests/test_stkg_firing.py`
(8건)에 둔다.

## 6. 폐기한 것

이전 설계(관계/위치 두 테이블 + 구간 축약 + 파생 열 4개)를 대체한다.
`vtmak/stkg/collapse.py`, `derive.py`, `export.py`와 그 테스트를 지웠다.
`config/munition_map.csv`도 `firing.py`가 무기명을 안 쓰므로 지웠다.

## 7. 범위 밖

- 원문 이벤트(`build/events/battle.jsonl`) 병합. 시각축이 다르다(원문은
  시나리오 시작 기준 초, 관측은 벽시계).
- 전역과 드론 병합. 전역은 정답이고 드론은 관측이며 시각대도 다르다
  (실측 전역 08:09~08:16, 드론 22:00~22:07).
