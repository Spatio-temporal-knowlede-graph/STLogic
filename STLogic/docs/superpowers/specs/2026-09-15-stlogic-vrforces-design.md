# STLogic — Spatial Context 기반 STKG Forecasting (설계 고정판)

작성 2026-09-15 · 고정 2026-09-21. 대상 `STLogic/mycode/`, `STLogic/tools/`.
선행 기록: [PROGRESS.md](../../PROGRESS.md), [STLogic_연구내용.md](../../STLogic_연구내용.md).

방법론 정의에 특정 데이터셋의 어휘(`LOC_*`, `move to`, landmark)를 남기지 않는다.
설계 판단마다 그 근거가 된 실측값을 함께 적는다. **이 문서는 구현 착수 시점의
고정 스펙이다** — 여기서 벗어나는 구현은 문서를 먼저 고친다.

---

## 0. 핵심

```
φ  = [ d̃ , ṽ_d ]                                   공간 특징 두 개
F_r(o) = log P(φ|y=1,r) / P(φ|y=0,r)                관계 조건부 적합도
C_S = TopK_{o∈O_vis(r,obs), F_r(o)>0} F_r(o)        공간 후보 생성
C   = C_T ∪ C_S                                     후보 합집합
S   = S_T(o) + λ·S_S(o)                             가산 결합 (기본안)
```

공간 증거를 계산할 수 없으면 `C_S = ∅`, `S = S_T` → **STLogic ≡ TLogic**.

TLogic의 temporal random walk와 rule learning은 **변경하지 않는다**.

```
RuleLearning_STLogic = RuleLearning_TLogic
```

기여는 rule learning이 아니라 inference 단계의 공간 문맥 추가에 있다.

---

## 1. 문제 설정

TLogic의 forecasting 실패는 두 종류다.

| 실패 유형 | 상황 | STLogic의 대응 |
|---|---|---|
| **Missing Candidate** | 정답이 후보 집합에 없음 | Spatial Candidate Generation |
| **Wrong Ranking** | 후보에는 있으나 순위가 낮음 | Spatial-Temporal Reranking |

예측 query는 TLogic과 동일하다.

```
(s, r, ?, t)
```

전장 행동은 임무·지휘·무기체계·위협도 등 관측되지 않는 변수에도 좌우된다.
따라서 목표는 공간 정보로 행동을 결정론적으로 예측하는 것이 아니라,
**시간 규칙에 공간적 근거를 더해 ranking을 개선하는 것**이다.

---

## 2. 입력과 정규화

### 2.1 방법론이 요구하는 것

```
Temporal Fact   (s, r, o, t)
Spatial State   P(e, t) → position
```

두 가지뿐이다. 물리적 파일 구조는 방법론에 등장하지 않는다.

### 2.2 Position Provider — source 우선순위

```
Direct Observation  ≻  Static Registry  ≻  Observed Anchor Derivation
```

| # | source | 정의 |
|---|---|---|
| ① | `direct` | fact row 또는 position table에 위치가 직접 있음 |
| ② | `registry` | 정적 entity의 좌표가 별도로 제공됨 (VR-Forces: `battlefield_layout.json`) |
| ③ | `anchor_derivation` | registry가 없을 때, 그 entity를 대상으로 하는 엣지가 **종료되는 시점**의 subject 위치를 집계 |

③은 그래프 구조만으로 좌표를 지어내는 spatial inference가 **아니다**. 관측
데이터에 이미 존재하는 좌표를 entity의 공간 표현으로 정규화하는 과정이다.

#### ③의 적격 판정 — 수렴하는 관계만 anchor가 된다

모든 관계가 object를 anchor하지는 않는다. 어떤 지점을 **포격하는** 부대는 사격진지에
머물며 목표로 다가가지 않으므로, 그 subject 위치는 목표의 위치를 말해주지 않는다.

**산포로는 거를 수 없다.** VR-Forces 실측에서 `FFE-on-Location`은 전 관계 중 종료
산포가 **가장 작은데**(4 m — 사격진지가 일관되므로) 위치는 **가장 많이 틀린다**
(2,697 m). 구분하는 것은 **subject가 거리를 좁혔는가**이다.

| relation | 종료 산포 | 수렴 중앙 | 실측 오차 | 판정 |
|---|---:|---:|---:|---|
| `move to` | 103 m | **616 m** | 54 m | anchor |
| `Provide-Suppressive-Fire-Loc` | 533 m | **0 m** | 1,350 m | 제외 |
| `FFE-on-Location` | 4 m | **0 m** | 2,697 m | 제외 |

```
A(r, o) = 1[ median_spans( d(start, ĉ) − d(end, ĉ) )  >  spread(ends) ]
          ĉ = 종료 위치들의 중심
```

즉 **subject들이 추정치 자체의 산포보다 크게 다가와서 끝난 (관계, 객체) 쌍만**
anchor로 인정한다. 도메인 지식이 개입하지 않고 위치가 판정한다.

**성능** — 이 필터를 적용하면 VR-Forces에서 최대 오차가 2,697 m → **300 m**로
잡힌다(train 구간 70%, 표본 ≥3 조건에서 LOC 18개 중 7개 복원, 오차 중앙 98 m).
표본 하한을 두지 않고 `move to` 전체를 쓰면 오차 중앙은 1 m까지 내려가지만 표본이
적은 객체에서 큰 오차가 섞인다 — **복원 범위와 정확도의 교환**이며, `anchor_min_samples`로
조절한다.

③을 유지하는 이유는 성능이 아니라 **일반성**이다. registry가 필수 입력이면
"임의의 STKG에 적용 가능"이 성립하지 않는다. registry가 있으면 registry가 이긴다.

### 2.3 범위에서 제외하는 것

공간 정보가 전혀 없는 KG에 대해 그래프 관계만으로 좌표를 생성하는 spatial
completion은 다루지 않는다. 여러 곳에 나뉘어 저장된 공간 정보를 하나의 `P(e,t)`로
통합하는 것과, ②③으로 정적 entity의 좌표를 확보하는 것은 정규화로 본다.

### 2.4 좌표 정규화

위경도는 국소 metric 좌표(ENU)로 변환한다. 위도 21.38°에서 경도 1도는 위도
1도보다 7% 짧아 원시 위경도로는 거리가 왜곡되고 방위는 더 크게 틀어진다.
시나리오 전역 2.2 km에서 측지선(Vincenty) 대비 1 m 이내임을 검증했다.

---

## 3. Spatial Feature

### 3.1 두 개로 고정

```
d(s,o,t)  = ‖ P(s,t) − P(o,t) ‖
v_d       = ( d(t₁) − d(t₀) ) / (t₁ − t₀)
φ         = [ d̃ , ṽ_d ]
```

`d`와 `v_d`는 모두 거리만의 함수이므로 **평행이동·회전에 불변**이다.

### 3.2 `[Δx, Δy]`를 쓰지 않는 이유

| feature set | MRR | 90° 회전 후 |
|---|---:|---:|
| `[d]` | 0.2814 | 0.2814 |
| **`[d, v_d]`** | **0.5310** | 0.5310 |
| `[Δx, Δy]` | 0.2590 | 0.2500 |
| `[Δx, Δy, d, v_d]` | 0.4960 | 0.4859 |

추가하면 **성능이 떨어지고**(0.5310 → 0.4960), 좌표축 회전에 값이 변해
frame-invariance를 깬다. 제외한다.

`v_d`가 기여의 대부분을 담당한다 — `[d]` 0.2814 → `[d, v_d]` 0.5310 (**+89%**).
단, 이는 판별적 형태(§5)에서만 나온다. `−Δd`로 단순 정렬하면 무작위보다 못하다.

### 3.3 관측 간격 `δ` — 전역 상수가 아니다

```
t₁ = obs 이하의 가장 최근 관측
t₀ = t₁ 직전의 이용 가능한 관측
δ  = t₁ − t₀                          ← query마다 결정
```

**측정 — `δ`가 길수록 단조 악화**:

| `δ` | hard MRR |
|---|---:|
| **10 s** | **0.5268** |
| 30 s | 0.5210 |
| 60 s | 0.5125 |
| 120 s | 0.4905 |
| 300 s | 0.4283 |
| 600 s | 0.2643 |

오래된 관측과 비교하면 현재 운동 상태가 희석된다. 가장 최근의 이용 가능한
간격을 쓰는 것이 원칙이고, 하한은 관측 잡음이 정한다.

### 3.4 Scale Normalization — 전이 장치이지 성능 장치가 아니다

```
L = training spatial entities의 pairwise distance 중앙값     (VR-Forces ≈ 1,038 m)
τ = training spatial observation interval의 중앙값

d̃   = d / L
ṽ_d = v_d · τ / L                                  ← 두 항 모두 무차원
```

`v_d / L`은 단위가 1/s라 무차원이 아니다. 시간 척도가 다른 STKG(1 Hz 전장 vs
일 단위 ICEWS)로 옮기면 깨지므로 `τ`를 곱한다.

**측정 — 단일 데이터셋 안에서 정규화는 결과를 바꾸지 않는다**:

| 정규화 (δ=60 s) | hard MRR |
|---|---:|
| 정규화 없음 `[d, v_d]` | 0.5125 |
| `[d/L, v_d/L]` | 0.5125 |
| `[d/L, v_d·τ/L]` | 0.5125 |

대각 Gaussian의 로그우도비는 특징별 affine 스케일링에 불변이라 positive와
negative가 똑같이 스케일되어 상쇄된다. 따라서 **`L`과 `τ`는 데이터셋 간 feature
scale을 맞추기 위한 장치이며, valid/test에서 튜닝하지 않는다.**

---

## 4. Relation-Compatible Candidate Pool

```
O_vis(r, obs) = { o : ∃ s, t′ ≤ obs,  (s, r, o, t′) }
```

**측정 — 전체 entity 탐색은 붕괴한다**:

| 탐색 범위 | 후보 수 | MRR | Recall@5 |
|---|---:|---:|---:|
| relation-compatible | 15 | **0.4960** | **77.8%** |
| 전체 공간 entity | 338 | 0.0311 | 2.2% |

`[d, v_d]`는 순수 기하 특징이라 "800 m 앞의 목적지"와 "800 m 앞의 전차"를
구분하지 못한다. 후보가 338개면 무관한 entity가 상위를 점령한다.

**train이 아니라 가시 창에서 만드는 이유** — hill395(섹터 네임스페이싱, 완전
inductive)에서:

| | 정답 포함률 |
|---|---:|
| `O_train(r)` | **0.00%** (0 / 20,210) |
| `O_vis(r, obs)` | **97.50%** (19,704 / 20,210) |

창이 `obs`에서 잘리므로 미래 누수는 없다.

**한계** — 한 번도 관계 `r`의 object로 등장한 적 없는 entity는 후보가 될 수 없다
(hill395 잔여 2.5%). 전체 entity 탐색으로 잡을 수 있으나 위 표대로 손실이 훨씬
크므로, zero-shot first appearance는 범위 밖 확장 문제로 둔다.

**원칙**: 정규화란 후보 제약을 없애는 것이 아니라, 데이터셋과 무관하게 동일한
방식으로 relation compatibility를 정의하는 것이다.

---

## 5. Spatial Pattern Learning

### 5.1 Positive / Negative

관계별로 **정답과 오답의 공간 패턴 차이**를 학습한다. "가까운 후보가 좋다"를
배우는 것이 아니다.

```
Positive   φ⁺ = φ(s, o⁺, obs)
Negative   N(q) = N_hard ∪ N_rel
             N_hard = C_T \ { o⁺ }                  시간적으로 그럴듯하나 오답
             N_rel  ⊂ O_vis(r, obs) \ { o⁺ }        관계 호환 후보에서 sampling
```

`N_hard`가 핵심이다. random negative만 쓰면 "아주 멀리 있는 무관한 후보를
배제하는 모델"이 된다. hard negative를 넣어야 **"시간적으로는 그럴듯한데
공간적으로 아닌 후보"**를 구분하도록 학습된다. hard negative가 없는 query에서는
`N_rel`만 쓴다.

### 5.2 Estimator

```
P(φ | y, r) = N( μ_{r,y} , diag(σ²_{r,y}) )
```

특징이 두 개뿐이라 공분산을 추정할 표본이 부족하므로 대각 Gaussian에서 시작한다.

> **Diagonal Gaussian은 density estimator의 구현 선택이며 방법론의 정의가 아니다.**
> KDE·GMM·histogram으로 교체할 수 있다.

### 5.3 Spatial Compatibility

```
F_r(o) = log [ P(φ(o) | y=1, r) / P(φ(o) | y=0, r) ]
```

| 값 | 해석 |
|---|---|
| `F_r > 0` | 이 공간 패턴이 오답보다 정답 후보에서 흔하다 |
| `F_r ≈ 0` | 공간 패턴이 정답과 오답을 구분하지 못한다 |
| `F_r < 0` | 오답 후보에서 더 흔한 패턴이다 |

`fireAt`처럼 명령·임무·무기체계에 좌우되는 관계는 두 분포가 비슷해져 `F_r ≈ 0`이
된다. **관계별로 공간 정보가 유효한 정도가 데이터에서 자연히 결정된다.**

---

## 6. Training Pipeline — 순차 구조

hard negative가 `C_T`에서 나오므로 temporal rule grounding이 선행해야 한다.
이전 판의 병렬 다이어그램은 틀렸다.

```
Training STKG
      │
      ▼
① STKG Normalization            (s,r,o,t) + P(e,t)
      │
      ▼
② TLogic Temporal Rule Learning          ← 원형 그대로, 변경 없음
      │
      ▼  Temporal Rules
      │
      ▼
③ Training Query Rule Grounding  →  C_T
      │
      ▼
④ Negative Construction
      ├─ N_hard = C_T \ {GT}
      └─ N_rel  ⊂ O_vis(r) \ {GT}
      │
      ▼
⑤ Spatial Pattern Extraction     φ = [d̃, ṽ_d]  (positive / negative)
      │
      ▼
⑥ Relation-wise Diagonal Gaussian
      │
      ▼
   STLogic Model
```

순서가 바뀌어도 `RuleLearning_STLogic = RuleLearning_TLogic`은 성립한다 —
TLogic의 결과를 **읽어서** negative 구성에 쓸 뿐이다.

---

## 7. Forecasting Pipeline

```
Query (s, r, ?, t)  →  obs = t − Δ
      │
      ├────────────────────────────┬──────────────────────────┐
      ▼                            ▼                          │
 TLogic Grounding            O_vis(r, obs)                     │
      │                            ▼                           │
      │                      Position Check ──── 없음 ─────────┤
      │                            ▼                           │
      │                      φ = [d̃, ṽ_d]                      │
      │                            ▼                           │
      │                          F_r(o)                        │
      │                            ▼                           │
      ▼                     C_S = TopK_{F_r>0}                 │
   C_T, S_T                       C_S, S_S ←────── ∅ ──────────┘
      │                            │
      └──────────────┬─────────────┘
                     ▼
                C = C_T ∪ C_S
                     ▼
         S(o) = S_T(o) + λ·S_S(o)
                     ▼
              Ranked Candidates
```

모든 temporal·spatial 정보는 `t′ ≤ obs`까지만 쓴다.

---

## 8. 위치 결측 정책과 Graceful Degradation

**새로운 위치를 추론하지 않는다.**

| 상황 | 처리 |
|---|---|
| `P(s, obs)` 미정의 | 그 query는 공간 추론 없음. `C_S = ∅` |
| `P(o, obs)` 미정의 | 그 후보는 `C_S` 대상에서 제외. `C_T`에 있으면 `S_S(o) = 0` |
| `F_r(o) ≤ 0` | `C_S`에 추가하지 않음 |

따라서 쓸 만한 공간 증거가 없으면

```
C_S = ∅   ⇒   C = C_T ,  S = S_T   ⇒   STLogic ≡ TLogic
```

점수와 후보 집합이 **모두** 정확히 환원된다. STLogic은 사용 가능한 spatial
evidence가 있을 때만 TLogic에 개입한다.

---

## 9. Reranking

```
S_T(o)              TLogic score. C_T에 없으면 0
S_S(o) = Norm(F_r(o))   valid 통계로 공통 범위 정규화, test에 고정
```

`S_S(o)`는 `C_T`와 `C_S`의 **모든** 후보에 계산한다. 주입된 후보에만 붙이면
`C_T` 후보가 전부 `S_S = 0`을 받아 λ가 그들 사이 순서를 바꿀 수 없고, 재순위화가
구조적으로 불가능해진다.

```
S_convex(o) = (1−λ) · S_T(o) + λ · S_S(o)        0 < λ < 1
S_add(o)    = S_T(o) + λ · S_S(o)                척도 대조용
```

**측정 — 두 형태는 같은 trade-off를 다른 매개변수로 태운다** (valid, K=10, Δ=600s):

| λ (convex) | ALL MRR | HARD MRR | H@1 |
|---|---:|---:|---:|
| *TLogic baseline* | *0.7531* | *0.0034* | — |
| 0.1 ~ 0.5 | **0.7804** | 0.1645 | 0.7378 |
| 0.6 | 0.7710 | 0.1645 | 0.7259 |
| 0.7 | 0.6595 | 0.1866 | 0.5782 |
| 0.8 | 0.6314 | 0.2138 | 0.5593 |
| 0.9 | 0.6018 | 0.2254 | 0.5155 |
| 1.0 *(Spatial-only)* | 0.6048 | **0.2325** | 0.5006 |

additive는 λ ≤ 1에서 변화가 없고 λ ≥ 2부터 같은 궤적을 그린다 — `S_T`가 noisy-OR
확률(대부분 0.9 이상)이고 `S_S ∈ [0,1]`이라 **두 점수가 같은 척도가 아니라는 증거**다.

### 9.1 세 모델

| 모델 | 정의 | 재는 것 |
|---|---|---|
| **TLogic** | `C = C_T`, `S = S_T` | baseline. **후보 증강을 수행하지 않은 원본** |
| **STLogic-Conservative** | `C = C_T ∪ C_S`, λ = 0.1 | **Candidate Recovery** |
| **STLogic-Fusion** | `C = C_T ∪ C_S`, 0 < λ < 1 | Recovery + Reranking (Pareto 곡선으로 보고) |
| *Spatial-only* | λ = 1 | endpoint. `S = S_S`라 temporal logic이 전혀 없음 |

**메인 모델은 λ = 0.1의 Conservative로 고정한다.** RQ1의 primary metric이 전체
query MRR이고, λ=0.1~0.5가 동일하므로 가장 작은 양수를 택한다. λ=1은 이름이
Fusion인데 TLogic을 전혀 쓰지 않으므로 최종 모델이 될 수 없고, ALL이 baseline보다
나빠져 메인 RQ에 불리하다.

### 9.2 기여 분해

```
Stage 0  TLogic                      hard MRR 0.0034
Stage 1  + Candidate Recovery                 0.1645      +0.1611
Stage 2  + 강한 Spatial Reranking             0.2325      +0.0680  (ALL 손실 동반)
```

> Candidate generation은 overall과 hard를 동시에 개선했지만, 공격적인 spatial
> reranking은 transition-heavy한 hard case를 더 개선하는 대신
> persistence-dominated query에서 성능 저하를 유발한다.

query-adaptive spatial weighting은 자연스러운 후속 연구이나 본 논문에서는 구현하지
않고, 전역 λ의 trade-off를 보이는 선에서 멈춘다.

### 9.3 ⚠️ λ = 0은 TLogic이 아니다 — selection에서 제외

`λ = 0`이면 `S = S_T`지만 **후보 증강은 이미 수행된 뒤**다. 주입 후보는 0점
**동점 블록**으로 들어가고, `calculate_rank(setting="best")`가 그 블록 전체에 가장
낙관적인 순위를 준다.

| λ | best | average | worst | 평균 동점 수 |
|---|---:|---:|---:|---:|
| **0.0** | **0.2494** | 0.1188 | 0.0729 | **6.2** |
| 0.1 | 0.1645 | 0.1645 | 0.1645 | 1.0 |
| 1.0 | 0.2325 | 0.2325 | 0.2325 | 1.0 |

λ=0의 0.2494는 동점 처리가 만든 **인공물**이고 방식에 따라 3배 넘게 흔들린다.
λ>0에서는 `S_S`가 서로 달라 동점이 사라져 세 방식이 일치한다.

따라서 **baseline은 반드시 후보 증강을 수행하지 않은 원본 TLogic 결과**여야 하고,
동점이 발생할 수 있는 모든 설정에서는 best만 보고하지 않고 best/average/worst를
명시하거나 average를 primary로 쓴다.

`λ`·`K`·정규화 파라미터는 **valid에서만 결정하고 test에 고정한다.**

---

## 10. 평가 프로토콜

### 10.1 Horizon

```
obs = t − Δ            Δ = 30 / 60 / 120 / 300 / 600 s
```

tick 단위 평가는 성립하지 않는다 — persistence가 MRR **0.9997**(엣지 496,639 =
서로 다른 사실 522, 변화 158건). horizon을 도입하면 hard 비율이 Δ=30 s에서
1.00%, Δ=600 s에서 **16.15%**로 열린다.

### 10.2 Hard Query

```
hard ⇔ o(obs) ≠ o(t)
```

observation cutoff에서 알던 object와 실제 미래 object가 달라진 query. persistence가
구조적으로 실패하는 유일한 구간이다. **모든 결과를 `ALL` / `HARD` 두 가지로 보고한다.**

### 10.3 Cluster Bootstrap CI

fixed-horizon에서는 하나의 transition이 최대 Δ개의 상관된 query를 낳는다.
독립 단위는 query가 아니라 transition이다.

```
cluster = (s, r, o_prev, o_new)
```

hard MRR에 **95% cluster bootstrap CI**를 붙인다. Δ=600 s test에서 독립 단위는
1,170개가 아니라 **42개**다.

### 10.4 Candidate Generation은 MRR과 분리해 평가

```
Recall(C_T)  vs  Recall(C_T ∪ C_S)

SRR = #{ GT ∉ C_T ∧ GT ∈ C_S } / #{ GT ∉ C_T }
```

**Spatial Recovery Rate**가 Contribution 1의 효과를 가장 직접적으로 보여준다 —
"TLogic이 놓친 정답 중 공간 정보가 몇 %를 복구했는가".

### 10.5 지표

```
Candidate:  Candidate Recall@K · Spatial Recovery Rate
Ranking:    MRR · Hits@1/3/10          (ALL / HARD, hard에 cluster CI)
Efficiency: 평균 후보 풀 크기 · query당 spatial scoring 시간 · TLogic 대비 overhead
```

### 10.6 동점 처리 — **average rank가 primary**

```
rank(o) = ( rank_best(o) + rank_worst(o) ) / 2
```

모든 모델에 동일하게 적용한다. 특정 모델의 예외 처리가 아니다 — 후보 증강은 점수가
같은 항목을 한 블록으로 만들 수 있고, `best`는 그 블록 전체에 맨 앞 순위를 준다.

**측정 (test, hard MRR)**:

| | best | average | worst | 평균 동점 수 |
|---|---:|---:|---:|---:|
| TLogic | 0.0110 | 0.0110 | 0.0083 | 2.0 |
| **+Random Candidates** | **0.1673** | **0.0625** | **0.0377** | **9.0** |
| +Spatial `[d]` | 0.1177 | 0.1177 | 0.1177 | 1.0 |
| +Spatial `[d, v_d]` | 0.1162 | 0.1162 | 0.1162 | 1.0 |

무작위 증강만 4.4배 흔들린다(모든 후보가 `S_T = 0, E_S = 0`으로 한 덩어리가 된다).
공간 모델은 세 방식이 완전히 일치한다. `best`로 보고하면 무작위가 공간 모델을 이기는
것처럼 보인다. tie sensitivity가 쟁점일 때만 best/worst를 추가로 보고한다.

> Tied candidates were assigned their average rank. Best- and worst-case ranks were
> additionally examined to assess tie sensitivity.

---

## 11. RQ1 — Complete Observation

> 공간 문맥을 활용하면 TLogic보다 forecasting 성능이 향상되는가?

입력은 GT의 `t′ ≤ obs`, 정답은 GT의 `t`.

### A. Candidate Generation Ablation

| 구성 | 목적 | 지표 |
|---|---|---|
| TLogic | temporal 후보 baseline | CR@K |
| TLogic + Random Candidate | **후보 수 증가 자체의 효과 통제** | CR@K |
| TLogic + `[d]` spatial candidates | 거리의 복구 효과 | CR@K, SRR |
| TLogic + `[d, v_d]` spatial candidates | 거리 변화의 추가 효과 | CR@K, SRR |

### B. Final Ranking Ablation

| 구성 | 목적 |
|---|---|
| Persistence | 필수 기준선 (hill395에서 0.90인데 TLogic은 0.5464였다) |
| TLogic | temporal only |
| Spatial only | 공간 패턴 단독 |
| Candidate Generation only | 후보 복구만, reranking 없음 |
| + Additive Fusion | spatial evidence 추가 |
| + Convex Fusion | fusion 구조 비교 |
| **STLogic** | 최종 모델 |

---

## 12. RQ2 — Partial Observation

> 공간 관측이 불완전해도 개선 효과가 유지되는가?

STKG에 공간 정보가 없는 경우가 아니라, **특정 관측자가 전체 객체를 보지 못하는**
상황이다. UAV 개별 커버리지 33~60%, 합집합 216/333, **117개는 아무도 못 봄.**

### 12.1 학습은 한 번만

```
Train      = GT_train   (temporal rules + spatial model 모두)
Inference  = GT / UAV1~5 의 과거 관측
Label      = GT_future
```

UAV별로 모델을 다시 학습하지 않는다. 그래야 **모델 재학습 차이가 아니라 관측
불완전성 자체에 대한 강건성**을 잰다.

### 12.2 `δ` 증가 효과의 분리 — 필수 대조군

UAV는 관측이 드물어 `δ`가 자연히 커진다(관측 간격 중앙 31틱 ≈ 310 s).
§3.3 표에서 `δ` 300 s는 10 s 대비 hard MRR이 0.5268 → 0.4283, **상대 19% 하락**이다.
즉 RQ2의 성능 저하에는 두 원인이 섞여 있다.

| 조건 | 관측 entity | `δ` | 분리하는 것 |
|---|---|---|---|
| GT-Full | GT | GT 원래 간격 | 상한 |
| **GT-Sparse-δ** | GT | UAV와 동일 간격으로 thinning | **`δ` 증가 효과만** |
| UAV*i* | UAV*i* 관측 | UAV 실제 간격 | entity 누락 + `δ` 증가 |

```
GT-Full → GT-Sparse-δ   의 하락 =  관측 간격 증가 효과
GT-Sparse-δ → UAV       의 하락 =  관측 entity 감소 효과
```

### 12.3 보고

절대 성능과 함께 TLogic 대비 개선량을 본다.

```
Gain_MRR = MRR_STLogic − MRR_TLogic
```

관측 커버리지 · Candidate Recall · SRR과 성능의 관계를 함께 분석한다.

---

## 13. 타 모델 비교 — 데이터셋별 적용 가능성

| Category | Model | VR-Forces | hill395 |
|---|---|---|---|
| Naive | Persistence | ✓ | ✓ |
| Rule | TLogic | ✓ | ✓ |
| TKG Forecasting | RE-Net | ✓ | **N/A** |
| TKG Forecasting | CyGNet | ✓ | **N/A** |
| TKG Forecasting | TiRGN | ✓ | **N/A** |
| Spatial-aware | STSE | 확인 필요 | 확인 필요 |
| Proposed | **STLogic** | ✓ | ✓ |

hill395는 섹터 네임스페이싱으로 test entity가 train에 전혀 없는 완전 inductive
설정이라 임베딩 기반 모델은 unseen test entity embedding이 없어 원형 그대로 적용할
수 없다. VR-Forces는 단일 장면·transductive라 적용 가능하다. **이 차이 자체가
STLogic의 generalization 특성을 보이는 분석점이다.**

STSE는 task가 future extrapolation과 다를 수 있으므로, 구현 확인 후 동일
forecasting baseline과 spatial-aware reference 중 어느 범주로 보고할지 정한다.

### 공정성

동일 split · query · horizon Δ · 미래정보 cutoff · candidate universe ·
filtered setting · MRR/Hits@K. STLogic의 spatial input도 `t′ ≤ obs`까지만 쓴다.

---

## 14. 사용하지 않는 정보

Simple + Normalized 구조를 위해 core에서 제외한다.

```
Heading · Weapon Range · Entity Type · Force · LOC topology · Unit centroid
scenario-specific transition prior · 절대 상대좌표 [Δx, Δy]
handcrafted relation-specific spatial rule
```

core spatial information은 **Distance + Relative Distance Change**뿐이다.

*(참고) scenario-specific transition prior는 hard MRR 0.4057로 일반 구조보다 높지만
장면의 전이 쌍을 외우는 것이라 전이되지 않는다. §11 B의 장면 종속 상한 대조군으로만
보고하며, 0.4057 대 일반 구조의 대비가 frame-invariance 논지의 근거가 된다.*

---

## 15. 모듈 구성

| Module | 역할 | Input | Output |
|---|---|---|---|
| `data.py` | STKG 정규화, Position Provider | CSV / registry / position table | `(s,r,o,t)`, `P(e,t)` |
| `learn.py` *(기존)* | TLogic rule learning | train facts | rules |
| `spatial.py` | feature 추출 · negative 구성 · Gaussian 적합 · scoring | facts + positions + rules | spatial model, `F_r` |
| `apply_stlogic.py` | 후보 생성 + fusion | query + models | ranked candidates |
| `evaluate_stlogic.py` | ALL/HARD 평가 · cluster CI · CR@K · SRR | predictions + GT | metrics |

`spatial.py` 내부:

```
compute_distance()
compute_relative_distance_change()        ← δ는 query마다 결정
build_positive_negative_samples()         ← C_T를 읽어 hard negative 구성
fit_relation_model()
score_candidate()

SpatialModel[r] = { Positive(μ⁺, σ⁺) , Negative(μ⁻, σ⁻) }
```

---

## 16. 구현 순서

```
1. data.py           Position Provider (direct ≻ registry ≻ anchor derivation)
2. 기존 learn.py 실행  →  rules
3. spatial.py        training query grounding → hard negative → [d̃, ṽ_d] → Gaussian
4. apply_stlogic.py  candidate augmentation (F_r > 0, TopK) + additive fusion
5. evaluate_stlogic  ALL / HARD · cluster bootstrap CI · CR@K · SRR
6. RQ1 ablation → RQ2 (GT-Sparse-δ 대조군 포함) → 타 모델 비교
```

---

## 17. 기여

**Contribution 1 — Relation-Compatible Spatial Candidate Generation**
시간 규칙이 생성하지 못한 후보를 relation-compatible candidate space에서 공간
패턴으로 복구한다. 측정: Δ=600 s hard query의 **98.4%**에서 정답이 TLogic 후보에
없었고(후보 개수 중앙 2개), 규칙 무발화는 2.8%뿐이었다 — 병목은 커버리지가 아니라
후보의 내용이다.

**Contribution 2 — Discriminative Spatial Pattern**
가까운 후보를 고르는 것이 아니라 관계별 positive/negative 공간 분포를 대비시켜
학습한다. 이 형태에서만 `v_d`가 작동한다(`[d]` 0.2814 → `[d, v_d]` 0.5310).

**Contribution 3 — Spatial-Temporal Fusion with Graceful Degradation**
temporal evidence를 유지한 채 spatial evidence를 가산하고, 공간 증거가 없으면
후보 집합과 점수가 모두 TLogic으로 정확히 환원된다.

---

## 18. 알려진 한계

| 한계 | 수치 / 내용 |
|---|---|
| zero-shot first appearance 미해결 | hill395 2.5%. relation signature 기반 `Compat(e,r)` 확장은 범위 밖 |
| 대각 Gaussian은 추정기 선택 | joint density가 원칙, factorized는 표본 부족에 따른 근사 |
| 짧은 horizon의 hard 표본이 얇다 | Δ=60 s에서 test 클러스터 2개, Δ=600 s에서 42개 |
| VR-Forces는 단일 관계 | 전이가 전부 `move to`. 술어별 비교 불가 |
| VR-Forces는 단일 장면 | inductive 아님. 대신 임베딩 비교군 실행 가능 |
| `λ`·`K`·정규화 파라미터 | valid에서만 결정, test 고정 |
