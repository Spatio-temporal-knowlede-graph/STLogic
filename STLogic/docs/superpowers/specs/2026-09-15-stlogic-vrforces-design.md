# STLogic — dataset-agnostic 방법론 설계

작성 2026-09-15. 대상 `STLogic/mycode/`, `STLogic/tools/`.
선행 기록: [PROGRESS.md](../../PROGRESS.md), [STLogic_연구내용.md](../../STLogic_연구내용.md).

방법론 정의에 특정 데이터셋의 어휘(`LOC_*`, `move to`, landmark)를 남기지 않는다.
남는 것은 relation, visible history, spatial grounding, 상대 공간 특징, 관계 조건부
적합도뿐이다. 설계 판단마다 그 근거가 된 실측값을 함께 적는다.

---

## 0. 기여

1. **Spatial Grounding Layer** — 엔티티마다 다른 공간 가용성을 하나의 인터페이스로
   통합하고 불확실성을 정량화한다.
2. **Relation-adaptive Spatial Candidate Augmentation** — 시간 규칙이 만들지 못한
   후보를 visible relation range에서 복구한다.
3. **Graceful Spatial-Temporal Fusion** — 공간성이 약하거나 위치가 없으면 STLogic이
   기저 시간 규칙 모델로 정확히 환원된다.

---

## 1. 문제 설정과 입출력

### 1.1 전제

시간 사원소 `(s, r, o, t)`와, **일부 엔티티에 대해 시간에 따라 얻을 수 있는 spatial
grounding**을 가진 STKG. 모든 object가 좌표점일 필요는 없다.

### 1.2 모델 입력 — 쿼리 하나당

```
query      (s, r, ?, t)          t는 실제 시각 그대로
horizon    Δ
obs        t − Δ                 관측 시각
visible    { 엣지 e : ts(e) < obs }
grounding  G(·, τ) for τ ≤ obs
```

`obs` 하나가 **창 컷오프 · 공간 기준 시각 · 시간 근접성 점수 · 후보 도메인 구성**
네 곳 모두를 지배한다. 한 곳이라도 `t`를 쓰면 미래가 샌다.

### 1.3 출력

```
{ candidate : score }  내림차순  +  후보별 근거(발화 규칙 · 공간 근거)
```

### 1.4 시스템 입력 (VR-Forces 실험 기준)

관측자당 CSV 한 개. 시나리오 저작 자산(`battlefield_layout.json` 등)은 **입력이
아니다** — 손으로 만든 자산이 필수면 "임의의 STKG에 적용 가능"이 성립하지 않는다.
읽는 컬럼: `subject` `predicate` `object` `timestamp` `latitude` `longitude`
(필수), `Heading` `CurrentSpeed` `EntityType` `Force` (선택).

좌표는 국소 ENU 미터로 투영한다. 위도 21.38°에서 경도 1도는 위도 1도보다 7% 짧아
원시 위경도로는 거리가 왜곡되고 방위는 더 크게 틀어진다. 시나리오 전역 2.2km에서
측지선(Vincenty) 대비 1m 이내임을 검증했다.

---

## 2. 시스템 구성도

```
                      ┌────────────────────────┐
                      │  관측 CSV (관측자별)    │
                      └───────────┬────────────┘
┌─────────────────────────────────▼──────────────────────────────────┐
│ STAGE 0   데이터셋 구축                                             │
│   ENU 투영 · 격자 · 시간 분할 · 엔티티 타입                          │
└───────────┬──────────────────────────────────┬─────────────────────┘
            │ train.txt                        │ visible history
┌───────────▼───────────┐      ┌───────────────▼─────────────────────┐
│ STAGE 1  learn.py     │      │ STAGE 2  Spatial Grounding Layer    │
│   (TLogic 원형·무변경) │      │   G(e,t) → (p, q, extent, source)   │
│   temporal walk       │      │   + 관계 조건부 적합도 F_r 적합      │
└───────────┬───────────┘      └───────────────┬─────────────────────┘
            │ rules.json                       │ grounding + F_r
            └──────────────┬───────────────────┘
┌──────────────────────────▼─────────────────────────────────────────┐
│ STAGE 3   추론  (obs = t − Δ)                                       │
│   3a  규칙 grounding                      → C_T                     │
│   3b  Visible Relation Range 구성          O_vis(r, obs)            │
│   3c  Spatial Candidate Augmentation      → C_S = TopK F_r(φ)       │
│   3d  Reliability-aware Fusion            C = C_T ∪ C_S             │
└──────────────────────────┬─────────────────────────────────────────┘
┌──────────────────────────▼─────────────────────────────────────────┐
│ STAGE 4   평가                                                      │
│   Standard(C=E) / Relation-domain(C=O_vis) · horizon · hard · CI    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 방법론

### Step 1 — Spatial Grounding Layer

엔티티마다 공간 가용성이 다르다(사람=시변 점, 차량=시변 점, 기관=본사 또는 다지점,
국가=영역, 부대=구성원 분포). STLogic 내부에서 `entity → (lat, lon)`을 가정하지 않고
아래 인터페이스를 둔다.

```
G(e, t) → (p, q, extent, source)
   p        대표 공간 표현
   q ∈[0,1] grounding 신뢰도
   extent   공간적 크기 추정치 (영역형 엔티티용)
   source   direct | temporal_recovery | structural_aggregation | anchor_inference
```

우선순위:

| Level | source | 정의 |
|---|---|---|
| 0 | `direct` | 관측된 위치 `p_e(t)` |
| 1 | `temporal_recovery` | `p̂_e(t) = f(p_e(t′), v_e, heading_e, t−t′)` |
| 2 | `structural_aggregation` | 집합 관계(`partOf`/`memberOf`)로 연결된 구성원의 집계 |
| 3 | `anchor_inference` | `p̂_o = Aggregate{ p_s(t) : (s,r,o,t) ∈ visible }`, **단 `r ∈ R_anchor`** |

끝내 좌표를 못 얻으면 `q = 0`으로 두고 공간항을 쓰지 않는다.

**⚠️ Level 3은 모든 관계에 적용하면 안 된다.** `Bob criticizes OpenAI`로 OpenAI의
위치를 추정하는 것은 틀렸다. `R_anchor`는 사람이 지정하지 않고 train에서 자동 선택한다.

**anchor eligibility는 relation이 아니라 `(relation, object)` 단위로 판정한다.**
같은 `locatedIn`이라도 object가 건물일 수도 도시일 수도 국가일 수도 있어, relation
전체를 anchor/not-anchor로 이분하면 너무 거칠다.

```
A(r, o) = 1[ SE(r,o)/ℓ₀ < τ_SE  ∧  spread(r,o)/ℓ₀ < τ_spread ]
          SE(r,o) = spread(r,o) / √n
```

relation은 anchor inference의 **가능성**을 제공할 뿐, 실제 grounding 가능 여부는
`(r, o)` 쌍마다 결정된다. 충분히 많은 쌍이 anchorable하면 relation-level prior를
둘 수 있다.

**두 조건을 모두 요구하는 이유**와 **ℓ₀로 정규화하는 이유**가 각각 있다.

두 번째가 필요한 이유는 측정으로 확인됐다.

| (relation, object) | 표본 | spread | SE |
|---|---:|---:|---:|
| `move to` / `LOC_중앙킬존남측` | 91 | **565 m** | **59 m** |

SE가 작다고 공간적으로 조밀한 것이 아니다. 킬존은 점이 아니라 영역이라 표본이
많아 SE만 작아진다. `SE → centroid 추정 불확실성`이지 `SE → 고유 공간 크기`가
아니다. SE만으로 문턱을 걸면 영역형 객체를 신뢰도 높은 점 anchor로 오인한다.
반대로 `spread`는 그 자체가 **크기 추정치**이므로 `extent` `ξ`로 승격시켜 쓴다.

그리고 두 문턱은 미터 고정값이 아니라 **장면 특성 길이 `ℓ₀`로 정규화**한다. 실내
STKG에서 20 m는 매우 크고 지정학 STKG에서 수백 km는 정상이라, 고정 미터 임계값은
데이터셋 규모가 바뀌면 깨진다. `q`도 같은 `ℓ₀`를 쓰므로 척도 기준이 하나로 통일된다.

관계별 자동 선택이 실제로 변별하는지도 확인했다(엣지 종료 시점 subject 위치 기준):

| relation | 객체 수 | 평균 표본 | 평균 spread | 평균 SE |
|---|---:|---:|---:|---:|
| `move to` | 14 | 34 | 178 m | **45 m** |
| `FFE-on-Location` | 6 | 2 | 192 m | 136 m |
| `Provide-Suppressive-Fire-Loc` | 2 | 6 | 533 m | 209 m |

`move to`만 통과한다. 사람이 고르지 않아도 관계가 갈린다.

집계 위치는 **모든 관측이 아니라 엣지가 종료되는 시점**의 subject 위치를 쓴다
(`move to`: 전체 관측 328 m → 종료 시점 178 m). 이렇게 얻은 좌표는 실측 대비
**오차 중앙 1 m**(복원 14/15, 도착 표본 20건 이상은 전부 0~1 m)였고, 이를 써도
hard MRR이 떨어지지 않았다(거리 랭커 0.2208 → 0.2333).

`q`는 ad-hoc 상수가 아니라 추정 불확실성에서 직접 나온다.

```
q_o = ( 1 + SE(p̂_o) / ℓ₀ )⁻¹        ℓ₀ = 장면 특성 길이
```

RQ2의 관측 신뢰도 감쇠도 이 안에 들어간다 — 별도 장치가 아니다.

```
q_e(t) = exp( −λ (t − t_obs) ) · q_e^base
```

### Step 2 — Visible Relation Range

```
O_vis(r, obs) = { o : (s, r, o, t′) ∈ visible(obs) }
```

외부 타입 온톨로지 없이 데이터에서 relation range를 얻는다. **train이 아니라 가시
창**에서 만드는 것이 핵심이다.

**측정 — `O_train(r)`은 inductive에서 완전히 실패한다.**

| | 정답이 후보 도메인에 포함 |
|---|---:|
| hill395 (섹터 네임스페이싱, 완전 inductive) — `O_train(r)` | **0 / 20,210 = 0.00%** |
| hill395 — `O_vis(r, obs)` | **19,704 / 20,210 = 97.50%** |
| VR-Forces (단일 장면) — `O_train(r)` | 5,023 / 5,170 = 97.16% |

관계 10종 전부 `O_train`과 test object의 교집합이 0이었다. 가시 창으로 바꾸면 test
섹터의 새 엔티티도 그래프에 처음 등장한 뒤부터 후보가 된다. 창이 `obs`에서 잘리므로
미래 누수는 없다.

**확장 — subject-conditional range.** 위 정의는 relation의 **전역** object range라,
`(person, locatedIn, city)`와 `(company, locatedIn, country)`가 공존하면 city와
country가 한 도메인에 섞인다. 방법론은 조건부 형태를 열어 둔다.

```
O_vis( r | ψ(s), obs )        ψ(s) = subject의 타입 또는 structural signature
```

`ψ`는 외부 타입 온톨로지일 필요가 없고 relation signature 같은 구조적 역할이어도
된다. 본 실험은 표본 희소성 때문에 relation-only 도메인을 쓴다 — `O_vis(r, obs)`는
**최종 원리가 아니라 최소 가정 버전**이다.

**⚠️ 한계 — zero-shot first appearance.** `O_vis`는 쿼리 시점까지 한 번도 그래프에
나타난 적 없는 엔티티를 후보에 넣지 못한다(hill395 잔여 2.5%). 이는 결함이라기보다
관측 기반 후보 생성의 자연스러운 한계다. 학습된 relation-compatibility
`Compat(e, r) > τ`(엔티티의 relation signature 기반)로 이 구간을 다루는 확장이
가능하며, 본 실험 범위 밖이다.

### Step 3 — Spatial Candidate Augmentation

```
C_T = C_TLogic(s, r, obs)
C_S = TopK_{ o ∈ O_vis(r, obs),  q_s q_o F̂_r(φ_o) > τ_F }  q_s q_o F̂_r(φ_o)
C   = C_T ∪ C_S
```

**활성화 문턱 `τ_F`가 필수다.** 문턱 없이 `TopK`를 돌리면 모든 `F̂_r`이 0이어도
0점 후보 K개가 `C_S`로 들어와, 점수는 TLogic으로 환원되지만 **후보 집합은 환원되지
않는다**. 문턱을 두면

```
쓸 만한 공간 증거 없음  ⇒  C_S = ∅  ⇒  C = C_T
```

가 성립하고, Step 6의 "정확한 환원"을 실제로 주장할 수 있다.

`backoff`가 아니라 `augmentation`이다. 기존 설계는 `C_T`가 빌 때만 공간이 개입했는데,
실제로는 `C_T`가 비어 있지 않으면서 정답을 담지 못하는 경우가 지배적이다.

| | hill395 | VR-Forces (Δ=600s) |
|---|---:|---:|
| 규칙 무발화 | 27.5% | **2.8%** |
| 정답이 후보에 없음 (hard 기준) | — | **98.4%** |
| 후보 개수 중앙값 | — | 2 |

`|O_vis(r)| ≤ K`이면 전수 주입이 되고, 크면 공간 top-K 검색이 된다. 같은 코드가
`|O_vis|`가 15든 5,876이든 돈다.

### Step 4 — Relation-conditioned Spatial Compatibility

**원 정의는 joint density ratio다.**

```
F_r(φ) = log [ P(φ | r) / P(φ) ]
φ      = [ d , v_rel , cos β , ρ ]
M      = [ M_d , M_v , M_β , M_ρ ] ∈ {0,1}⁴      feature availability mask
```

| 특징 | 정의 | 성격 |
|---|---|---|
| `d` | `‖G(s,obs).p − G(o,obs).p‖` | subject–candidate 근접도 |
| `v_rel` | `(d(obs) − d(obs−δ)) / δ` | 상대 운동(접근율) |
| `cos β` | `cos(heading_s − bearing(s→o))` | 방향 정렬 |
| `ρ` | `d(o_prev, o_cand)` | **object-transition distance** |

전부 상대량이라 좌표계의 평행이동·회전에 불변이다. `ρ`는 `(s,r,o_prev,·)`에서
`o_cand`로의 target 전이가 공간적으로 연속인지를 본다 — 사람의 장소 이동, 차량
waypoint 변경, 물류 목적지 변경에도 그대로 적용된다. `o_prev`는 명시적으로

```
o_prev = argmax_{t' < obs} t'   s.t.  (s, r, o, t') ∈ visible(obs)
```

이고, `(s,r)`의 첫 등장에서는 **undefined**라 `M_ρ = 0`이 된다.

**⚠️ 모든 특징이 항상 계산 가능하지는 않다.** heading 컬럼이 없는 데이터셋이 있고,
두 시점 위치가 없으면 `v_rel`이 정의되지 않으며, 첫 등장에서는 `ρ`가 없다. 가용한
증거만 결합하도록 mask로 정규화한다.

```
F̂_r(φ) = ( Σ_j M_j w_j log [P(φ_j|r)/P(φ_j)] ) / ( Σ_j M_j w_j )
```

`Σ_j M_j w_j = 0`이면 공간 증거 없음으로 처리한다(`C_S`에 들어가지 못한다).

**측정 — mask는 가장 필요한 곳에서 필요하다** (test 쿼리 기준):

| 데이터셋 | `d` | `v_rel` | `cos β` | `ρ` |
|---|---:|---:|---:|---:|
| VR-Forces (heading 컬럼 有) | 100% | 100% | 100% | 100% |
| hill395 (heading 컬럼 無) | 100% | **90%** | **90%** | **90%** |

hill395에서 빠지는 10%가 정확히 **첫 등장 쿼리** — 그 데이터셋에서 persistence로
풀리지 않는 유일한 구간이다. mask 없이 `cos β`를 강제하면 거기서 깨진다.

**⚠️ 구현은 factorized 근사다.** 표본 부족으로 joint density를 직접 추정할 수 없어

```
F_r(φ) ≈ Σ_j w_j log [ P(φ_j | r) / P(φ_j) ]
```

로 분해한다(위의 mask 정규화 포함). `d`, `v_rel`, `ρ`는 상관이 강할 수 있으므로
(가까운 후보가 접근 중일 확률이 높다) 이 분해는 근사이며, **방법론의 정의가 아니라
구현 선택**이다. 밀도 추정기도 마찬가지다 — 본 실험은 Gaussian을 쓰지만
KDE·GMM·normalizing flow·density-ratio MLP로 교체 가능하다. **방법론 ≠ Gaussian.**

likelihood ratio 형태가 기존 σ 게이팅보다 나은 이유: `P(φ|r) ≈ P(φ)`이면 비가 1에
수렴해 항이 자동으로 사라진다. "σ가 크다 = 중요하지 않다"는 항상 성립하지 않지만
(분포 자체가 넓은 관계가 있다) 비는 원리적으로 게이팅된다.

### Step 5 — Reliability-aware Fusion

```
S_spatial(o) = q_s · q_o · F_r( φ(s, o, obs) )
```

두 모드를 모두 보고한다.

**Conservative** — 시간 규칙 순위를 훼손하지 않는 안전 확장.

```
S_inj < min S_rule
```

**Fusion** — 최종 모델. 공간 증거가 강하면 시간 후보를 넘어설 수 있다.

```
S(o) = S̃_T(o) + λ · q_s · q_o · F̂_r(φ)
```

**⚠️ 척도 정합(calibration)이 남은 연구 문제다.** `S_T ∈ [0,1]`(noisy-OR 확률)인데
`F̂_r ∈ (−∞, +∞)`(로그 밀도비)라 두 항이 같은 척도라는 보장이 없고, 그래서 `λ`가
매우 민감한 하이퍼파라미터가 된다. 원칙형은 각 항을 먼저 보정하는 것이다.

```
S̃_T = g_T(S_T),   S̃_S = g_S(q_s q_o F̂_r),   S = α S̃_T + (1−α) S̃_S
```

본 실험은 구현을 additive `λ` 형태로 유지하되, **`λ`는 valid split에서만 선택하고
test에는 고정한다.** 그렇지 않으면 test 정보로 성능을 맞췄다는 공격을 받는다.

**측정 — 안전 불변식의 비용** (일반 특징만, hard 3,844건):

| 모드 | hard MRR | 천장 |
|---|---:|---:|
| Conservative | 0.2237 | 0.5 (정답이 잘해야 2위) |
| **Fusion** | **0.3158** | 1.0 |

`+0.0920`, 상대 `+41%`. Conservative는 recall을 살리지만 ranking 개선을 차단한다.
Conservative는 안정성 baseline, Fusion이 본체다.

### Step 6 — Graceful Degradation (methodological invariant)

```
q = 0              (좌표 없음)           → q_s q_o F̂_r = 0
Σ_j M_j w_j = 0    (가용 특징 없음)       → F̂_r 미정의
F̂_r(φ) ≈ 0        (비공간 관계)          → 공간항 소멸
⇒ 어떤 후보도 τ_F 를 넘지 못함  ⇒  C_S = ∅  ⇒  C = C_T,  S = S_T
⇒ STLogic  ≡  TLogic   (점수와 후보 집합이 모두 정확히 환원)
```

> STLogic introduces spatial evidence only when spatial grounding and
> relation-specific spatial informativeness are available; otherwise it reduces
> exactly to the underlying temporal rule model.

부가 장점이 아니라 방법론의 불변식으로 기술한다.

---

## 4. 평가 프로토콜

### 4.1 Horizon

쿼리는 실제 시각 `t`에 두고 모델이 볼 수 있는 것을 `t − Δ`로 자른다. tick 단위
평가는 persistence가 MRR 0.9997이라 성립하지 않는다(엣지 496,639 = 서로 다른 사실
522, 변화 158건). horizon을 도입하면 hard 비율이 Δ=30s에서 1.00%, Δ=600s에서
16.15%로 열린다.

### 4.2 두 candidate setting

| setting | 후보 공간 | 목적 |
|---|---|---|
| Standard | `C = E` (전체 엔티티) | 원 논문·기존 벤치마크와 비교 가능 |
| Relation-domain | `C = O_vis(r, obs)` | 공간 후보 생성 자체의 품질. "relation range 제약 덕분 아니냐"는 반론 방어 |

TLogic baseline에도 동일하게 적용한다. 현재 `evaluate.py`는 전체 341개 엔티티 중
순위를 매기는데 `move to`의 정답은 15개뿐이라, 맞히면 과대평가·틀리면 과소평가된다.

### 4.3 지표

```
MRR · Hits@1/3/10 · Candidate Recall
부분집합   all · hard(관측 시각과 답이 달라진 쿼리)
불확실성   hard MRR의 클러스터 부트스트랩 95% CI
           클러스터 = (s, r, 이전 답, 새 답) — 전이 1건이 최대 Δ개의 상관 쿼리를 낳음
```

---

## 5. Ablation 계획

### 5.1 RQ1 — 공간 문맥 (완전 관측)

| # | 구성 | 분리하는 것 |
|---|---|---|
| ⓪ | persistence (직전 관측 복사) | **필수 기준선.** hill395에서 0.90인데 TLogic은 0.5464였다 |
| ① | TLogic | 시간 규칙 단독 |
| ② | + augmentation (무작위 순서) | **주입 자체의 효과** |
| ③ | + `d` | subject–candidate 근접도 |
| ④ | + `d, v_rel` | **거리 변화가 추가 변별력을 주는가** |
| ⑤ | + `d, v_rel, cos β` | **heading/방향이 추가 향상을 주는가** |
| ⑥ | + `d, v_rel, cos β, ρ` | **target 전이의 공간 연속성이 기여하는가** |
| ⑦ | ⑥ Conservative | 안전 모드 |
| ⑧ | **⑥ Fusion** = STLogic | 최종 모델 |

특징을 한 번에 하나씩 누적한다. ③→④→⑤→⑥이 원래 연구 질문(거리 / 거리변화 /
heading / 전이 연속성)과 1:1로 대응하므로, 결과표가 곧 연구 질문의 답이 된다.

### 5.2 RQ2 — 부분 관측

| # | 구성 |
|---|---|
| ⑧ | STLogic (완전 관측) — 상한 |
| ⑨ | STLogic (부분 관측 입력) — 관측 열화의 비용 |
| ⑩ | ⑨ + `q_e(t)` 시간 감쇠 (none / linear / exp / cutoff) |
| ⑪ | ⑩ + Level 1 temporal recovery (마지막 관측 / 등속 / heading+speed) |

### 5.3 대조군

| # | 구성 | 보이려는 것 |
|---|---|---|
| ⑫ | identity transition prior `P(o′|o)` | **장면 종속 상한.** hard MRR 0.4057. 장면을 외우면 더 가지만 전이되지 않는다 |
| ⑬ | heading을 후보 생성기로 | 음성 결과. obs 시점 heading은 **기존** 답을 98.5%로 가리킨다(새 답 1.2%) |
| ⑭ | anchor 대상 엔티티를 제거한 데이터셋 | 366 triple / 전이 0건. 후보 도메인 설계의 필연성 |

⑫가 중요하다. 장면 종속 shortcut 0.4057 대 일반 구조 0.2237(Conservative) /
0.3158(Fusion)의 대비가 frame-invariance 논지 그 자체다 — **dataset-specific prior를
제거하고도 temporal baseline(0.0110) 대비 20~29배를 유지한다.**

### 5.4 명시할 한계

| 한계 | 수치 |
|---|---|
| `O_vis`는 zero-shot first appearance를 못 다룬다 | hill395 2.5% |
| factorized likelihood는 구현 근사 | `d`·`v_rel`·`ρ` 상관 있음. 원 정의는 joint |
| `S_T`와 `F̂_r`의 척도 정합 미해결 | `λ`는 valid에서만 선택, test 고정 |
| `O_vis(r)`는 subject-conditional이 아님 | 최소 가정 버전. `O_vis(r|ψ(s))`로 확장 가능 |
| 짧은 horizon의 hard 표본이 얇다 | Δ=60s에서 test 클러스터 2개, Δ=600s에서 42개 |
| VR-Forces는 단일 관계 | 전이가 전부 `move to` |
| VR-Forces는 단일 장면 | inductive 아님. 대신 임베딩 비교군 실행 가능 |
| Conservative의 hard MRR 천장 0.5 | 안전 불변식의 구조적 결과 |

---

## 6. 구현 순서

```
1. spatial_grounding.py       G(e,t) → (p, q, extent, source) · R_anchor 자동 선택
2. relation_domain.py         O_vis(r, obs) — 가시 창 기반
3. apply.py --augment         Step 3 경로 + Conservative/Fusion 두 모드
4. compatibility.py           F_r — density-ratio, Gaussian 추정기로 시작
5. evaluate_horizon.py        Standard/Relation-domain 두 setting
6. ⓪~⑧ 측정 (RQ1) → ⑨~⑪ (RQ2) → ⑫~⑭ 대조군
```
