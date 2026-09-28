# Agent Specifications

> Every agent in HireBridge. Each spec is a contract: change the contract, bump the
> `prompt_version`, and record why in `06-decisions.md`.
> Last updated 2026-09-28.

## 0. Shared rules

Applies to all agents without exception.

1. **Structured output.** Every agent returns a Pydantic-validated object. No free-text parsing.
2. **Prompt versioning.** Prompts live in `app/agents/<agent>/prompts/v{n}.py`. The version is
   written to `agent_runs.prompt_version` on every call. Never edit a released prompt in place.
3. **One run, one row.** No model call happens outside an `agent_runs` row.
4. **Token budget.** Each agent declares `max_input_tokens` and `max_output_tokens`. Exceeding
   aborts with `aborted_budget` rather than silently truncating context.
5. **Retry policy.** 3 attempts on transient provider errors. On *validation* failure: one retry
   with the validator's complaint appended, then hard fail. Never degrade silently.
6. **No PII beyond need.** Each spec declares its input field allowlist. Scoring agents never
   receive identity fields.
7. **Deterministic where possible.** `temperature = 0` for extraction and scoring. Higher only
   for generation that should vary (question sets, phrasing).
8. **Evaluated, not vibed.** Each agent has a fixture set in `tests/agents/<agent>/cases/` with
   pass criteria. A prompt change that drops the eval score does not ship.
---

## 1. Resume Parser Agent

**Purpose.** Raw CV text → structured `profile_facts` with stable IDs.

| | |
|---|---|
| Trigger | CV upload, or guest apply |
| Model tier | Small, `temperature=0` |
| Input | Extracted text (PDF/DOCX), optional layout hints |
| Output | `ParsedProfile` — contact block, list of typed facts, per-fact confidence |

**Why it is hard here.** Local CV conventions break naive parsers: photos, "Father's Name",
NID rows, two-column layouts, mixed Bangla/English, and dates written `01/2023 – Present`,
`Jan'23-now`, or `2023-current` in the same document.

**Rules**
- Never infer a fact that is not written. A missing graduation year stays null; it is not
  computed from an enrolment year.
- Normalize dates to ISO; keep the original string in `payload.raw_date` for display.
- Split experience bullets into individually addressable units with stable `bullet_id`s.
- Confidence below 0.7 marks the fact `needs_review`; the UI asks the user to confirm.

**Failure modes.** Scanned image CVs (route to OCR first), multi-column misordering (use layout-
aware extraction, not plain text), header/footer contamination.

**Eval.** 100 real anonymized CVs; field-level precision/recall per fact kind. Target ≥ 0.92
precision on experience and education.

---

## 2. JD Parser Agent

**Purpose.** Raw job description → structured job record.

| | |
|---|---|
| Model tier | Small, `temperature=0` |
| Input | Raw JD text, optional company context |
| Output | `StructuredJD` — responsibilities, typed requirements, seniority, skills split into must/nice, years range, red flags |

**Rules**
- Classify each requirement as `must` or `nice`. If the JD does not signal it, default to `nice` —
  over-strict must-haves silently sink good candidates in the rules score.
- Extract implied seniority from the responsibilities, not only the title ("Senior" in a title
  with 1-year requirements is a real signal to surface).
- Normalize skill names to a canonical vocabulary (`Next.js` → `nextjs`, `PostgreSQL` → `postgres`)
  so lexical matching does not fail on spelling.
- Flag discriminatory phrasing ("male candidates preferred", "age below 30") into `red_flags`
  and surface it to the employer at publish time. This is common in local postings and is a
  meaningful product differentiator.

**Eval.** 50 JDs, human-labelled must/nice split; target ≥ 0.85 agreement.

---

## 3. CV Tailoring Agent ⚠ highest-risk agent

**Purpose.** Candidate profile + target JD → tailored CV content that re-expresses existing
facts to match the job.

| | |
|---|---|
| Model tier | Large |
| Temperature | 0.3 |
| Input allowlist | `profile_facts` (with IDs), `structured_jd`, template constraints, candidate name only for the header |
| Output | `TailoredResume` — ordered sections, each line carrying `source_fact_ids[]` |

**What it may do**
- Reorder experiences and bullets by relevance to the JD
- Rewrite a bullet's wording to use the JD's vocabulary, **when the underlying fact matches**
  (profile says "built a retrieval chatbot", JD says "RAG systems" → allowed)
- Select which projects and skills to surface, and which to drop
- Rewrite the summary/headline from existing facts
- Adjust section ordering and density to fit one or two pages

**What it may never do**
- Invent an employer, title, date, degree, certification, or tool
- Invent a metric ("improved performance by 40%") that is not in the source fact
- Upgrade scope ("contributed to" → "led", "assisted" → "owned")
- Change employment dates, or close a gap by stretching a range
- Claim a skill that appears only in the JD and nowhere in the profile

### Fabrication Validator (separate, deterministic, non-optional)

Runs after generation, before the user ever sees the output. **Not an LLM judge** — a
deterministic pass first, then a model check only on what survives:

| Check | Method |
|---|---|
| Every output line cites ≥ 1 `fact_id` | structural assertion |
| Cited facts exist and belong to this profile | DB lookup |
| No numeric value appears in output that is absent from its source facts | regex extraction + set comparison |
| No date in output outside the source fact's date range | date parsing |
| No skill/tool token in output absent from the profile's skill+text corpus | canonical vocabulary diff |
| Scope-escalation verbs | verb-tier comparison against the source bullet |
| Semantic equivalence of rewritten bullet vs source | small-model entailment check: does the source **entail** the rewrite? |

Any hard-check failure → one repair retry with the specific complaint → then `validator_status = failed`
and the run surfaces an error. **A failed validation never renders a PDF.**

`passed_with_warnings` (soft checks only) renders, but the diff view highlights each warned line
for explicit user confirmation.

**Eval.** 30 seeded adversarial cases (profile deliberately missing a JD-critical skill) — the
validator must block 100%. This is a release gate.

---

## 4. Question Generation Agent

**Purpose.** JD + candidate profile + seniority → a calibrated interview question set.

| | |
|---|---|
| Model tier | Large |
| Temperature | 0.7 (variety across sessions is desirable) |
| Output | `QuestionSet` — 8–12 questions, each with `competency`, `difficulty`, `expected_signals[]`, `followup_triggers[]` |

**Composition target**

| Type | Share | Note |
|---|---|---|
| Role-technical | 40% | Drawn from the JD's must-haves |
| Experience-probing | 25% | Anchored to a specific item in *this candidate's* profile |
| Behavioral / situational | 25% | Mapped to the competency rubric |
| Role-context | 10% | Domain and team-fit questions from the JD |

**Rules**
- Calibrate difficulty to the *JD's* seniority, not the candidate's — the point is rehearsing the
  real interview.
- At least 2 questions must cite a concrete profile item ("You built a RAG chatbot at Autofy —
  how did you handle retrieval quality when the corpus grew?").
- `expected_signals` are what a strong answer contains; the evaluator scores against these, so
  they must be written at generation time, not inferred later.
- No trick questions, no puzzles, no questions about protected attributes or personal life.

**Eval.** Human rating of relevance on 20 JD/profile pairs; target ≥ 70% rated "relevant to the
actual job".

---

## 5. Interview Conductor Agent

**Purpose.** Run the session turn by turn.

| | |
|---|---|
| Model tier | Mid (it selects and phrases, it does not judge) |
| Temperature | 0.5 |
| State | `interview_sessions.current_index` + prior turns |

**Rules**
- Ask one question at a time. Never batch.
- Follow up at most once per question, and only when a `followup_trigger` fires (answer under
  ~40 words, missing a named `expected_signal`, or a claim with no specifics).
- Never reveal the rubric, never say whether an answer was right, never coach mid-session —
  feedback belongs entirely to the report.
- Stay in role: a professional interviewer, neutral, brief between questions.
- Honour session budget — cap total turns so a rambling candidate cannot 10× the cost.
- On resume after disconnect, continue from `current_index` with the **frozen** question set.

**Voice mode (Phase 3).** Same agent; the transport changes. STT text goes in, the response is
spoken through TTS. Add: barge-in handling, a "still there?" prompt after 20 s of silence, and
transcript confidence — a low-confidence STT segment asks for a repeat rather than scoring noise.

---

## 6. Evaluation / Summary Agent

**Purpose.** Completed transcript → per-answer scores and a competency rollup.

| | |
|---|---|
| Model tier | Large, `temperature=0` |
| Input | Full transcript, the question set with `expected_signals`, the JD, the rubric. **Not** the candidate's name or any identity field |
| Output | `InterviewEvaluation` — per-turn score + evidence quote, competency rollup, strengths, gaps |

**Rubric — 1 to 5 per competency**

| Competency | Scored on |
|---|---|
| Technical depth | Correctness, specificity, awareness of trade-offs |
| Problem structuring | Clarifies before solving, decomposes, states assumptions |
| Communication | Clear, ordered, appropriately concise |
| Experience evidence | Concrete, first-person, specific over generic |
| Role alignment | Answers map to this JD's actual responsibilities |

**Rules**
- Every score cites a verbatim quote from the answer. A score without evidence is invalid output.
- Score the *answer*, never the person. No inference about personality, confidence, or fit as a
  human being.
- Never penalize grammar, accent, or non-native phrasing. Communication is scored on structure
  and clarity of content only — an explicit instruction in the prompt and an eval case.
- An unanswered question scores null, not zero, and is reported as "not covered".

---

## 7. Improvement Suggestion Agent

**Purpose.** Evaluation → a prioritized, actionable practice plan.

| | |
|---|---|
| Model tier | Mid |
| Temperature | 0.4 |
| Output | 3–5 `Suggestion` items: `priority`, `competency`, `observation`, `action`, `example_rewrite`, `practice_prompt` |

**Rules**
- Each suggestion names the specific moment it came from ("in Q4 you described the caching layer
  without saying what you cached or why").
- `action` must be concrete and doable this week. "Improve communication" is a rejected output;
  "rehearse Q4 using situation → constraint → decision → result, in 90 seconds" is accepted.
- `example_rewrite` shows a stronger version of *the candidate's own answer*, built only from
  what they actually said — the no-fabrication rule applies to interview content too.
- Lead with the highest-leverage gap; never list every weakness. Max 5.
- Tone: direct and specific, never harsh, never padded with praise.

---

## 8. Ranking Justification Agent (HR mode)

**Purpose.** Explain *why* a candidate scored where they did, with evidence.

Scoring itself is **not** an LLM job — the composite is computed deterministically (lexical +
semantic + rules, see `02-data-model.md` §7). The agent only explains the computed result. This
keeps ranking reproducible, cheap, and auditable.

| | |
|---|---|
| Model tier | Mid, `temperature=0` |
| Input allowlist | Profile facts **stripped of identity**, structured JD, computed sub-scores, matched/missing requirement lists |
| Output | `Justification` — 2–3 sentence summary, `matched[]` (requirement → `fact_id`), `missing[]`, `flags[]` |

**Rules**
- Generated lazily: top 25 by default, plus any candidate the recruiter opens. Never all 400.
- Every `matched` claim cites a `fact_id`; the UI links the claim to the CV line.
- `missing` lists JD must-haves with no supporting fact — stated as absent evidence, never as a
  judgement of the person ("no Kubernetes experience found in the CV", not "unqualified").
- **Never** references or infers a protected attribute. The identity fields are not in the input,
  so it cannot; a unit test asserts the payload builder's allowlist.
- Never recommends an action. It explains a score; the recruiter decides. (Brief §8 rules 2 and 3.)
- If sub-scores are close, say so — "ranked below #3 mainly on years of experience; skills
  coverage is equivalent" is exactly the sentence that makes a recruiter trust the tool.

---

## 9. Agent configuration

```python
class AgentConfig(BaseModel):
    name: str
    model: str                    # from settings, never hardcoded in the agent body
    temperature: float
    max_input_tokens: int
    max_output_tokens: int
    prompt_version: str
    timeout_seconds: int
    retries: int = 3
    requires_validator: bool = False
```

Loaded from settings so a model can be swapped or a budget tightened without a code change.

## 10. Evaluation harness

```
tests/agents/<agent>/
    cases/          # input fixtures + expected properties
    test_eval.py    # runs the agent against cases, asserts thresholds
```

- Runs against a recorded-response fake by default; a `--live` flag hits real providers.
- CI blocks a merge if an agent's eval score regresses.
- The fabrication validator suite and the protected-attribute allowlist test are **release gates**,
  not advisory checks.
- New failures found in production become a fixture the same day. `agent_runs` is the source —
  it already stores the inputs.
