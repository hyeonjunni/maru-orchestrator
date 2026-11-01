# MARU Master Specification v0.3

> **MARU = Memory-Aware Relay & Understanding**  
> **Agents move. Memory stays. Human understands.**

- 문서 유형: Master Project Specification / AI Agent Handoff
- 구현 목표: MARU v0.1부터 단계적 확장
- 핵심 플랫폼: Windows 11 / macOS / Linux
- 핵심 사용자: 주니어 개발자, CS 학생, 학습 지향 AI-assisted developer, 적당히 프로젝트 이해를 유지하려는 vibe coder
- 비대상: 결과만 나오면 되고 구조·리뷰·이해에 전혀 관심이 없는 사용자
- 상태: 구현 기준 문서
- 원칙: **아이디어보다 구현 우선. v0.1에서는 Core/Relay/State/CLI만 완성한다.**

---

# 0. 이 문서를 읽는 AI 에이전트에게

이 문서는 MARU의 **source-of-intent**다.

다음 원칙은 구현 편의를 이유로 제거하지 않는다.

1. Production Plane과 Learning/Understanding Plane을 같은 conversation context로 합치지 않는다.
2. LLM이 전체 control plane을 직접 지배하지 않는다.
3. Agent 간 전달은 shared chat보다 structured artifact/event를 기본으로 한다.
4. Model private memory가 없어져도 project state를 복원할 수 있어야 한다.
5. Prompt/output/decision/review/state transition은 inspectable해야 한다.
6. 사람 전체를 beginner/junior 등으로 단순 분류하지 않는다.
7. 질문 횟수를 Understanding Debt 점수로 직접 사용하지 않는다.
8. Skill/Memory는 scope를 가진다.
9. 새 습관은 Local/Project scope에서 시작하고, evidence가 쌓여야 넓은 scope로 승격된다.
10. Agent self-improvement는 weight fine-tuning보다 memory/skill/tool/policy scaffolding 개선을 우선한다.
11. Sleep/Dream/Stress 아이디어는 연구 축이지만 v0.1 구현을 방해하지 않는다.
12. Human approval이 필요한 행동은 자동 우회하지 않는다.

---

# 1. MARU가 해결하려는 문제

## 1.1 수동 Relay 병목

기존:

```text
Planner
  ↓
Human copy/paste
  ↓
Worker
  ↓
Human copy/paste
  ↓
Reviewer
  ↓
Human copy/paste
```

인간이 사실상 메시지 큐, API, DB, 오케스트레이터 역할까지 수행한다.

MARU 목표:

```text
Human Goal
   ↓
MARU
   ↓
Planner → Challenger → Worker → Reviewer
   ↓
Human Summary / Gate
   ↓
Human decision
```

---

## 1.2 Context 손실

새 session, compaction, 모델 교체 뒤에도 다음이 복원되어야 한다.

- Goal
- Current state
- Why / decisions
- Risks
- Failed attempts
- Next step
- Artifacts
- Human Gates

> Session ≠ Task  
> **Arc = durable task unit**

---

## 1.3 Role contamination

Planner에게 교육 질문을 섞으면 계획 context가 오염될 수 있다.

따라서:

```text
Production Plane
Planner / Challenger / Worker / Reviewer

Understanding Plane
Teacher / Expert / Scout / Cartographer
```

두 plane은 canonical artifact를 함께 읽을 수 있지만 conversation history는 공유하지 않는다.

---

## 1.4 Human Comprehension Gap

AI 생산 능력이 인간 이해 속도보다 빨라질 수 있다.

```text
AI Production Capability
████████████████████

Human Understanding
████████
```

이 차이를 관리하는 것이 MARU의 핵심 연구축 중 하나다.

MARU는:

> **Build with AI. Understand what you build.**

를 목표로 한다.

---

# 2. 핵심 사용자

## Primary

### AI-native Junior Developer

- CS 학생
- 주니어 개발자
- 신입 개발자
- AI 코딩 도구로 실제 프로젝트를 만드는 사람
- 빠르게 만들고 싶지만 왜 그렇게 만들어졌는지도 알고 싶은 사람

## Secondary

### Learning-oriented Vibe Coder

- 비전공자
- Maker
- 창업자
- AI로 빠르게 구현하되 architecture/security/operation을 어느 정도 이해하고 싶은 사람

## Not Target

- 결과만 나오면 되고 이해·리뷰·유지보수에 관심이 전혀 없는 사용자

---

# 3. 핵심 원칙

| 원칙 | 의미 |
|---|---|
| AUTOMATE THE RELAY | 인간 복붙 제거 |
| EXTERNALIZE THE MEMORY | 기억을 session 밖으로 |
| PRESERVE UNDERSTANDING | 인간 supervisory control 보존 |
| SEPARATE EXECUTION FROM EDUCATION | Planner와 Teacher 분리 |
| EVOLVE THROUGH USE | 반복 실패를 rule/skill/tool로 승격 |
| AGENCY IN ISLANDS | Agent 자율성은 제한된 구간 |
| INSPECT EVERYTHING IMPORTANT | 중요한 모든 과정 추적 |
| LOCAL FIRST, PROMOTE WITH EVIDENCE | Memory/Skill은 좁은 scope에서 시작 |
| REASONING SHOULD DECREASE WITH EXPERIENCE | 반복 작업은 skill/tool로 proceduralize |
| SURPRISE RETURNS CONTROL TO REASONING | Skill/tool이 예외를 만나면 다시 LLM reasoning으로 |

---

# 4. CLI-first

MARU v0.x의 핵심 인터페이스는 CLI다.

```text
maru ...
```

Dashboard는 추후 observer로 붙인다.

## 기본 UX

```bash
maru init
maru run "로그인 기능 개선"
maru run --prompt-file task.md
maru status
maru arc list
maru trace <run-id>
maru inbox
maru approve <gate-id>
maru reject <gate-id>
maru resume <arc-id>
maru explain --simple "refresh token rotation"
maru explain --expert "refresh token rotation"
maru learn resources "refresh token rotation"
maru doctor
```

---

# 5. Cross-platform 요구사항

지원:

- Windows 11
- macOS
- Linux

규칙:

- `pathlib.Path`
- `subprocess` argv list
- Bash 전용 core 금지
- UTF-8 명시
- 한국어/공백 path 테스트
- Windows process termination 고려
- Docker 필수 금지
- CI matrix:
  - ubuntu-latest
  - macos-latest
  - windows-latest

---

# 6. 전체 아키텍처

```text
                               HUMAN
                                 │
                  ┌──────────────┴──────────────┐
                  │                             │
                  ▼                             ▼
             Discovery                     MARU Bridge
                  │                    Teacher / Expert / Scout
                  ▼                             │
              Problem Brief                 Learning Map
                  │
                  ▼
            MARU CONTROL PLANE
      deterministic state machine / gates
                  │
                  ▼
               Event Bus
      ┌───────────┼────────────┬───────────┐
      ▼           ▼            ▼           ▼
   Planner    Challenger      Worker     Reviewer
      │           │            │           │
      └───────────┴────────────┴───────────┘
                  │
              Artifacts / Git
                  │
                  ▼
            Persistence Layer

SQLite:
state / tasks / events / gates / metrics

Markdown/Git:
plan / ADR / reviews / human summaries / learning

Later:
Memory Lifecycle / Skills / Sleep / Dream
```

---

# 7. Discovery Agent

사용자가 처음부터 정확한 Goal/Requirements를 작성할 수 있다고 가정하지 않는다.

사용자는 다음 정도만 입력해도 된다.

```markdown
# What I want
뭘 만들고 싶은가?

# Why
왜 필요한가?

# What I know
현재 알고 있는 것.

# What I don't know
모르는 것 / 고민 중인 것.

# Constraints
OS, 돈, 시간, 반드시 지킬 것.
```

Discovery는 다음으로 변환한다.

```text
Vague Idea
  ↓
Known / Unknown
  ↓
Decision Needed Now
  ↓
Decision Can Wait
  ↓
Required Research
  ↓
Required Learning
  ↓
Draft Goal
  ↓
Draft Requirements
  ↓
Human confirmation
  ↓
Planner
```

### Discovery 원칙

- 불필요한 질문 폭탄 금지
- 지금 결정할 필요 없는 것은 reasonable default + assumption으로 기록
- 중요 결정은 Teacher/Expert를 통해 필요한 지식만 학습 후 인간 승인
- 사용자가 모른다는 사실을 global skill level로 일반화하지 않는다

---

# 8. State Machine

기본:

```text
DISCOVERY
  ↓
PLANNING
  ↓
PLAN_REVIEW
  ↓
IMPLEMENTING
  ↓
TESTING
  ↓
CODE_REVIEW
  ├─ fail → IMPLEMENTING
  └─ pass
       ↓
UNDERSTANDING_CHECK
       ↓
HUMAN_APPROVAL
       ↓
MERGED
```

v0.1에서는 Discovery와 Understanding을 최소 구현하거나 placeholder로 둘 수 있다.

---

# 9. Agent 역할

## Discovery
Vague request → Problem Brief

## Planner
Problem Brief → PlanArtifact / TaskGraph

## Challenger
Plan을 공격하지만 직접 수정하지 않음

## Worker
Approved Task만 구현

### 기본 Worker
**Claude Code CLI**

## Reviewer
Diff/Test/Plan을 읽고 finding 반환

### 기본 Reviewer
**Codex CLI**

## Teacher
쉬운 설명

## Expert
전문 설명

## Scout
공식문서/자료 검색

## Cartographer
Concept별 understanding evidence 기록

## Evolution
Memory/Skill/Tool/Policy 개선안을 제안하지만 직접 적용하지 않음

---

# 10. 기본 Agent Backend 설정

User-editable config:

```toml
# maru.toml

[agents.discovery]
backend = "claude"
permission = "read-only"

[agents.planner]
backend = "claude"
permission = "read-only"

[agents.challenger]
backend = "codex"
permission = "read-only"

[agents.worker]
backend = "claude"
permission = "workspace-write"

[agents.reviewer]
backend = "codex"
permission = "read-only"

[agents.teacher]
backend = "claude"
permission = "read-only"
```

Backend mapping은 Python 코드에 hard-code하지 않는다.

---

# 11. Arc / Task

```yaml
arc:
  id: auth-refresh
  goal: "Refresh token rotation 구현"
  state: IMPLEMENTING

  tasks:
    - id: auth-001
      state: done
      depends_on: []

    - id: auth-002
      state: ready
      depends_on: [auth-001]

  risks: []
  decisions: []
  next: "Implement reuse detection"
```

---

# 12. Event

```yaml
event:
  event_id: UUID
  arc_id: string
  run_id: string
  timestamp: ISO-8601
  source: planner|worker|reviewer|human|core|bridge
  type: PLAN_CREATED|REVIEW_FAILED|...
  payload: {}
  artifact_refs: []
  parent_event_id: UUID|null
```

append-only 기본.

---

# 13. Prompt / Artifact Contract

저장:

- raw user prompt
- rendered prompt
- role
- backend
- model
- session id
- output
- structured result
- tool result
- artifacts
- start/end time
- exit code

Agent 간 전달:

```text
Planner conversation X

Planner
  ↓
PlanArtifact
  ↓
Worker
```

---

# 14. Production Pipeline

```text
INTAKE
 ↓
DISCOVERY
 ↓
PLANNER
 ↓
CHALLENGER
 ↓
PLAN REVISION
 ↓
WORKER
 ↓
DETERMINISTIC TEST
 ↓
REVIEW
 ↓
UNDERSTANDING SUMMARY
 ↓
HUMAN GATE
 ↓
LEARNING / EVOLUTION CAPTURE
```

---

# 15. MARU Bridge

Bridge는 Production State를 수정하지 않는다.

```text
READ:
project
plan
code
review
decision

WRITE:
learning/*
```

## Teacher
쉬운 설명

## Expert
전문 설명

## Scout
현재 project에 필요한 자료만 추천

## Cartographer
Concept-level map

---

# 16. Human Understanding Debt

HUD는 Code Technical Debt와 별도다.

> 프로젝트를 안전하게 판단/운영하기 위해 필요한 지식과 실제로 확인된 인간 이해 사이의 차이.

직접 측정되는 값이 아니라 **multi-evidence latent estimate**로 취급한다.

---

## 16.1 질문은 약한 evidence

질문은 다음 용도로만 강하게 사용한다.

- concept candidate
- 설명 필요성
- checkpoint 출제 범위

금지:

```text
질문 1회 → mastery -10
Teacher 5회 사용 → junior 판정
```

---

## 16.2 Evidence

### Strong

- 실제 디버깅 성공
- 실제 설계 판단
- transfer
- 코드리뷰 bug 발견
- 결과 사전 예측
- incident recovery

### Medium

- adaptive checkpoint
- 자기 말로 설명
- Human Gate 선택 근거

### Weak

- 질문 횟수
- 문서 조회
- Teacher 사용
- 작업 시간
- 자기평가

---

## 16.3 Concept State

```yaml
concept: refresh-token-rotation

required_mastery: 0.90
criticality: 0.90

mastery: 0.63
evidence_confidence: 0.71
stability: 0.48
retrievability: 0.74
```

---

## 16.4 Debt

```text
Gap(c) = max(0, RequiredMastery - Mastery)

ConfirmedDebt(c)
= Criticality × Gap × Confidence

Uncertainty(c)
= Criticality × (1 - Confidence)
```

Confidence가 낮다고 Debt가 없다고 판단하지 않는다.

---

## 16.5 Principal / Interest

Principal:
현재 이해 gap

Interest:
이 gap 때문에 발생한 실제 비용

- rework
- 잘못된 human approval
- 같은 설명 반복
- debug failure
- decision delay
- review miss

---

# 17. Memory Lifecycle — 연구/후속 구현

v0.1 필수 아님.

Memory type:

```text
Working
Episodic
Semantic
Procedural
Deterministic Tool
```

---

## 17.1 Write Gate

모든 event를 기억하지 않는다.

후보 signal:

- Novelty
- Surprise
- Importance
- Resolution Effort
- Failed Hypotheses
- Human Correction
- Future Utility
- Transfer Potential

단순 formatting error는 장기기억하지 않는다.

---

## 17.2 Retrieval

Cosine-only 금지.

```text
Current Goal
 ↓
Memory Router
 ↓
Scope Filter
 ↓
Metadata Filter
 ↓
ANN Retrieval
 ↓
Graph Expansion
 ↓
Reranker
 ↓
Working Context
```

Goal-conditioned associative retrieval을 지향한다.

---

# 18. Scoped Memory / Scoped Habit

Scope:

```text
GLOBAL
DOMAIN / WORKSPACE
PROJECT
ARC
```

새 memory/skill은 좁은 scope에서 시작한다.

> **Local first, promote with evidence.**

---

## 18.1 Faceted Scope

Tree 하나로 제한하지 않는다.

```yaml
scope:
  project: MARU
  language: python
  framework: typer
  platform:
    - windows
    - macos
    - linux
  task_type:
    - implementation
  component:
    - cli
```

---

## 18.2 Promotion / Demotion

Project에서 반복 성공:

```text
Project Skill
```

여러 project에서 공통 성공:

```text
Domain Skill
```

다양한 domain에서 검증:

```text
Global Skill
```

실패 증가:

```text
Global → Domain
Domain → Project
```

scope는 넓어질 수도, 좁아질 수도 있다.

---

# 19. Reasoning-to-Routine Loop

반복 작업은 계속 LLM reasoning으로 처리하지 않는다.

```text
REASON
 ↓
SOLVE
 ↓
REMEMBER
 ↓
GENERALIZE
 ↓
PROCEDURALIZE
 ↓
AUTOMATE
 ↓
MONITOR
```

예외:

```text
Unexpected Result
OOD
Human Override
Skill Failure
 ↓
RETURN TO REASONING
```

---

## 19.1 Skill 단계

```text
Level 0: LLM Reasoning

Level 1: Recipe

Level 2: Parameterized Skill

Level 3: Deterministic Tool

Level 4: Automatic Trigger
```

---

## 19.2 Skill Promotion 조건

- 반복 빈도
- 높은 성공률
- 낮은 variance
- clear input/output
- deterministic validation
- 낮은 risk
- 낮은 false activation
- human/reviewer approval

---

# 20. Skill Evaluation

측정:

- task success
- validator pass
- human override
- false activation
- token saving
- latency saving
- project diversity
- context diversity

특히:

> **Activation Precision**

을 중요하게 본다.

잘못된 skill activation은 context contamination을 만들 수 있다.

---

# 21. Experience Promotion Engine

Memory / Skill / Tool Evolution을 하나의 공통 pipeline으로 본다.

```text
Experience
 ↓
Pattern Detection
 ↓
Abstraction
 ↓
Scope Estimation
 ↓
Evaluation
 ↓
Promotion / Demotion
```

Output:

- Semantic Memory
- Procedural Skill
- Executable Tool
- Policy Proposal

---

# 22. Stress — 연구 축

실제 감정으로 주장하지 않는다.

기술 용어 후보:

- Deliberation Load
- Agent Cognitive Load Proxy
- Operational Stress Proxy

friendly UI에서는 Stress라고 부를 수 있다.

---

## 22.1 Stress 후보

```text
tokens
retries
failed tool calls
failed hypotheses
human correction
context pressure
unresolved uncertainty
```

예:

```text
Stress =
w1 TokenLoad
+ w2 Retries
+ w3 Failures
+ w4 HumanCorrection
+ w5 ContextPressure
+ w6 Uncertainty
```

---

## 22.2 Repeated Stress

새로운 문제에서 높은 Stress는 정상일 수 있다.

중요한 것은 반복되는 task에서 Stress가 줄어드는가다.

```text
Run 1: 0.80
Run 2: 0.53
Run 3: 0.28
Run 4: 0.14
```

정상 학습.

반면:

```text
0.80
0.82
0.79
0.84
```

→ Proceduralization failure 후보.

---

# 23. Scar Memory — 연구 축

`Trauma`라는 용어 대신 기술적으로는:

- Failure Salience
- Scar Memory
- Critical Incident Memory

를 사용한다.

반복/치명 failure는 높은 retrieval priority를 가진다.

```yaml
scar:
  incident: destructive-migration
  severity: critical
  recurrence: 3
  human_override: 2
  salience: 0.96
```

단:

> Salience ≠ absolute prohibition

성공 경험이 쌓이면 decay 가능.

---

# 24. MARU Sleep — Offline Cognitive Maintenance

v0.1 필수 아님.  
중요 연구축으로 보존한다.

핵심 아이디어:

> Wake에서는 외부 일을 하고, Sleep에서는 자신이 일하는 방식을 정리한다.

---

## 24.1 Sleep Cycle

```text
0. Sleep Onset
   - new work pause
   - snapshot

1. Replay
   - important episodes
   - failures
   - corrections
   - high stress tasks

2. Consolidation
   - episode → semantic rule
   - repeated trajectory → skill candidate
   - duplicate merge

3. Downscaling
   - stale memory decay
   - unused skill decay
   - finished-project skill archive

4. Stress / Scar Regulation
   - recurrent failure 강화
   - obsolete warning 약화

5. Skill Reorganization
   - merge
   - split
   - promote
   - demote
   - scope change

6. Dream
   - synthetic edge cases
   - counterfactual rollouts
   - cross-platform simulation
   - old failure replay

7. Validation
   - deterministic tests
   - held-out tasks
   - regression tests

8. Staging
   - memory changes
   - skill proposals
   - tool proposals

9. Human Review

10. Wake
```

---

## 24.2 Sleep Trigger

### Periodic
하루 종료

### Release
Version boundary

### Stress-triggered

```text
high stress
+
high repetition
+
low learning progress
```

---

## 24.3 Sleep Depth

```text
Nap
- recent memory cleanup

Normal Sleep
- daily consolidation
- skill review
- small dream

Deep Sleep
- release level
- full project review
- architecture drift
- skill scope review
- regression
```

---

# 25. Dream / Counterfactual Skill Rehearsal

실제 production repo에서 직접 하지 않는다.

```text
Production Snapshot
 ↓
Temp Worktree / Sandbox
 ↓
Synthetic Scenarios
```

예:

```text
Windows + Korean path
macOS + space path
Linux + permission failure
Malformed CLI JSON
Child process timeout
```

Skill은 실제 경험 성공만으로 승격하지 않고 가상 edge case에서도 검증할 수 있다.

---

# 26. Guardrail

```text
SAFE → execute
ASK  → Human Gate
DENY → reject
```

필수:

- main merge 기본 금지
- deploy 기본 Human Gate
- destructive filesystem
- credentials
- external transmission
- constitution update
- high-risk security change

---

# 27. Self-Improvement

Weight modification은 v0.x 범위 밖.

MARU는 scaffolding improvement를 우선한다.

```text
memory
skills
tools
prompts
policies
routing
```

변경은:

```text
Proposal
 ↓
Regression
 ↓
Human Approval
 ↓
Apply
```

---

# 28. 디렉터리 구조

```text
maru/
├── pyproject.toml
├── README.md
├── AGENTS.md
├── CLAUDE.md
├── MARU_MASTER_SPEC.md
├── maru.toml
│
├── src/maru/
│   ├── cli/
│   ├── core/
│   ├── events/
│   ├── storage/
│   ├── agents/
│   │   └── adapters/
│   ├── discovery/
│   ├── bridge/
│   ├── memory/
│   ├── skills/
│   ├── guard/
│   ├── sleep/
│   └── evolution/
│
├── prompts/
│   ├── discovery.md
│   ├── planner.md
│   ├── challenger.md
│   ├── worker.md
│   ├── reviewer.md
│   └── bridge/
│
├── schemas/
├── scripts/
│   └── proto_harness.py
│
├── .maru/
│   ├── constitution.md
│   ├── arcs/
│   ├── project/
│   ├── learning/
│   ├── memory/
│   ├── skills/
│   ├── sleep/
│   └── evolution/
│
└── tests/
```

---

# 29. 기술 스택

| 영역 | v0.x |
|---|---|
| Python | 3.12+ |
| CLI | Typer + Rich |
| Schema | Pydantic v2 |
| Storage | sqlite3 |
| Config | TOML / `tomllib` |
| Orchestration | plain Python deterministic FSM |
| Agent | Claude Code CLI + Codex CLI |
| Worker default | Claude |
| Reviewer default | Codex |
| Git | subprocess adapter |
| CI | GitHub Actions |
| Dashboard | 후순위 |
| LangGraph | 비교/후순위 |

---

# 30. v0.1 — 구현 범위 고정

**지금 당장 구현할 것은 여기까지만이다.**

1. Project skeleton
2. Cross-platform CLI
3. `maru.toml`
4. Claude/Codex adapters
5. Arc
6. Task
7. Event
8. SQLite
9. Planner
10. Challenger
11. Claude Worker
12. Codex Reviewer
13. Deterministic test gate
14. Human Gate
15. Resume
16. Trace
17. `proto_harness.py`
18. Windows/macOS/Linux CI

### v0.1에 구현하지 않음

- Full Discovery Agent
- Full Bridge
- Knowledge Debt estimator
- Automatic memory consolidation
- Skill mining
- Sleep
- Dream
- Stress
- Scar Memory
- Dashboard
- Mobile
- Telegram
- Local model routing

**이 문서에 적혀 있다고 해서 지금 구현하지 않는다.**

---

# 31. Roadmap

## v0.1
Core / Relay / State / CLI

## v0.2
Task dependency / Inbox / Guard

## v0.3
Discovery + Bridge

## v0.4
Understanding Map + HUD

## v0.5
Memory lifecycle + scoped retrieval

## v0.6
Skill mining + scoped habit

## v0.7
Evolution + Reasoning-to-Routine

## v0.8
Sleep / Dream / Stress experimental

## v0.9
Dashboard

## v1.0
Cross-platform stabilization + research evaluation

---

# 32. Research Questions — Backlog

지금 구현을 막지 않는다.

- goal-conditioned memory retrieval
- scoped memory/skill retrieval
- Understanding Debt validity
- false skill activation
- skill promotion/demotion
- deliberation stress
- repeated stress vs learning progress
- sleep consolidation
- synthetic dream rollout
- failure salience
- human supervisory control
- junior developer learning effect

---

# 33. 최우선 구현 철학

판단이 애매하면 우선순위:

1. State recovery
2. Inspectability
3. Context isolation
4. Cross-platform
5. Safety
6. Simplicity
7. Performance
8. Fancy intelligence

> **Do not build the brain first. Build the nervous system that keeps the brain accountable.**

---

# 34. 지금부터의 목표

더 이상 설계 아이디어를 추가하지 않는다.

첫 목표:

```text
request.md
   ↓
Planner
   ↓
Challenger
   ↓
Claude Worker
   ↓
Tests
   ↓
Codex Reviewer
   ↓
human-summary.md
```

이 흐름이 **사람 복붙 없이 실제로 한 번 끝까지 성공하는 것**이 MARU 최초 milestone이다.
