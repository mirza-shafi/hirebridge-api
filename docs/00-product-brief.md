# HireBridge — Product Brief

| | |
|---|---|
| **Status** | Draft v0.1 |
| **Last updated** | 2026-09-28 |
| **Owner** | Mirza Md Shafi Uddin |
| **Audience** | Engineering, design, and anyone joining the project |

> This is the source-of-truth product document. It is duplicated identically in
> `hirebridge-api/docs/` and `hirebridge-web/docs/`. Change it in one place and copy it
> to the other in the same commit.

---

## 1. One-liner

**HireBridge is an AI-native hiring platform that gives every job seeker a job-specific CV and a realistic mock interview for each application, and gives every employer a ranked, explained shortlist instead of a folder of PDFs.**

---

## 2. The problem

### Candidate side

| Pain | Current reality |
|---|---|
| Generic CV, low callback | One CV blasted to 50 postings; callback rate typically 2–5% |
| Tailoring is expensive | Manually rewriting a CV for one JD takes 30–60 minutes, so nobody does it |
| Zero feedback loop | Rejection arrives with no reason, so the next application repeats the same mistake |
| Generic interview prep | YouTube/LeetCode is not "this company, this JD, this seniority" |

### Employer side (SME / startup, the beachhead)

| Pain | Current reality |
|---|---|
| CV flood | 200–800 applications per opening, arriving by email in mixed formats |
| No ATS | Greenhouse/Workable cost USD 150–500/month — out of budget for a 30-person Dhaka company |
| Manual screening | An HR executive eyeballs PDFs for 3–5 working days per role |
| Keyword filters are blunt | "React" filter drops a strong candidate who wrote "Next.js" |
| No structured comparison | Decisions live in a WhatsApp thread, not in a record |

### The gap HireBridge fills

Both sides are doing unstructured work on the same artifact — the CV — with no shared structure between them. HireBridge structures the CV and the JD once, then serves both sides from that structure.

---

## 3. Why now

- Small-model inference makes structured CV parsing and scoring cost **< $0.01 per CV**, so screening 500 CVs costs less than a cup of tea.
- Reliable structured output (JSON schema / constrained decoding) makes *explainable* ranking possible — a score with a reason, not a black box.
- Speech models are cheap and fast enough for turn-based mock interviews without a call-center budget.
- Local incumbents (BDJobs and equivalents) remain listing boards with effectively zero AI surface.

---

## 4. Target market

**Beachhead (v1):** Dhaka-based software / IT / digital-agency SMEs and startups, 10–200 employees, hiring 2–10 roles per quarter — plus their candidate pool (BRACU, NSU, AIUB, BUET, DU graduates with 0–5 years of experience).

**Why this wedge:**
- Direct network access for design partners and first paying customers.
- Incumbents are listings-only; global AI tools are USD-priced and ignore local CV conventions (photo, father's name, NID field, mixed Bangla/English, "Expected Salary" line).
- Small enough that a single HR executive is the buyer, the user, and the champion — one-person sales cycle.

**Expansion path:** remote-hiring agencies in SEA and the Gulf that source South-Asian talent → then a global self-serve candidate product where the candidate pays.

---

## 5. Personas

### Rakib — Candidate (primary)
24, junior backend developer, 1 year experience, applying to 10–15 roles a week.
- **Wants:** more interview calls; to stop rewriting his CV by hand; to not freeze in the first technical interview.
- **Fears:** being filtered out by a keyword bot; being caught with an inflated CV.
- **Success:** applies in under 2 minutes with a CV that actually reflects the JD, and walks into the interview having already answered the likely questions once.

### Nusrat — HR Executive (primary buyer)
29, non-technical, sole HR person at a 40-person software company, runs 3 open roles at once.
- **Wants:** to hand the hiring manager 10 good CVs, not 400 raw ones; to justify why those 10.
- **Fears:** tools she can't explain to her CEO; missing a strong candidate; anything that needs IT setup.
- **Success:** 400 applications → a reviewed shortlist in under 30 minutes, each with a readable reason.

### Tanvir — Hiring Manager (influencer)
Engineering lead. Only opens the tool to review the shortlist and leave a verdict. Every screen he touches must work without training.

### Admin — Platform operator (you)
Needs cost visibility per agent run, prompt version control, and an audit trail for every automated decision.

---

## 6. Product pillars

The five items from the original concept note, specified.

### P1 — Job Intelligence *(original item 1: "job post automatic")*
Employer pastes a raw JD (or a link); the system parses it into a structured job record — title, seniority, must-have vs nice-to-have skills, responsibilities, location, employment type, salary band — generates a clean public posting page, and optionally cross-posts to the company's own LinkedIn/Facebook channels.

- **v1:** paste-JD → structured job → public SEO page → manual share links.
- **v1.5:** authenticated cross-post via official platform APIs.
- **Out of scope:** scraping third-party job boards. See §8 rule 6.

### P2 — Frictionless Apply *(item 2)*
A candidate with a completed profile applies in one action. The application carries a structured profile snapshot plus the CV version used, so the employer sees consistent data across every applicant.

- **v1:** one-click apply for registered candidates; guest apply with CV upload → parsed into a profile.
- **Out of scope:** auto-applying to jobs on the candidate's behalf without review.

### P3 — Adaptive CV *(item 3)*
Given the candidate's structured profile and a target JD, produce a tailored CV: reordered sections, re-weighted bullets, aligned vocabulary, JD-relevant projects surfaced. Output as a rendered PDF plus a diff view against the base CV.

- **Hard constraint:** the agent may only re-express facts that already exist in the candidate's profile. No new employers, dates, degrees, metrics, or tools. See §8 rule 1.
- **v1:** tailor an existing profile to a JD, diff view, PDF export, 2 template choices.
- **v1.5:** build a profile from scratch through a guided interview (the "CV create" half of item 3).

### P4 — Interview Studio *(item 4)*
A multi-agent mock interview tied to a specific JD and the candidate's own background.

| Agent | Role |
|---|---|
| Question Generation | Produces a JD- and seniority-calibrated question set (technical, behavioral, role-specific) |
| Interview Conductor | Runs the session turn by turn; text in v1, voice in v3; asks follow-ups when an answer is thin |
| Evaluation / Summary | Scores each answer against a rubric, produces a per-competency breakdown |
| Improvement Suggestion | Turns the evaluation into a prioritized, concrete practice plan |

- **v1:** text-based session, 8–12 questions, full report.
- **v3:** turn-based voice (STT → LLM → TTS), then optional real-time.
- **Out of scope permanently:** scoring a candidate's face, accent, or "enthusiasm". Video-based personality inference is a legal and ethical minefield and is not a HireBridge feature.

### P5 — HR Copilot *(item 5)*
For a given job, score and rank every applicant's CV against the JD, each with a human-readable justification and evidence citations pointing at specific CV lines.

- **v1:** hybrid ranking (semantic + lexical + structured rules), ranked list with reasons, side-by-side compare, stage pipeline (New → Shortlisted → Interview → Offer → Rejected).
- **v1.5:** recruiter feedback loop — thumbs on rankings feeds calibration.
- **Hard constraint:** ranking sorts, it never hides. See §8 rule 2.

---

## 7. Scope boundary for v1

**In**
- Candidate profile, CV upload + parse, tailored CV generation with diff, PDF export
- Employer org accounts, job creation from pasted JD, public job pages
- Apply flow, application pipeline stages
- CV ranking with explanations
- Text-based mock interview with report
- Email notifications

**Out (deliberately deferred)**
- Voice interview, live or recorded
- Third-party job aggregation / scraping
- Mobile apps (responsive web only)
- Payments and subscriptions (manual invoicing for design partners)
- Bangla-language UI (Bangla *content* in CVs must parse; the UI stays English)
- Assessments, coding tests, background checks, offer letters

---

## 8. Non-negotiable product rules

These are product constraints, not preferences. Violating one is a bug regardless of what it does to a metric.

1. **No fabrication.** The CV agent may only restate, reorder, and re-word facts present in the candidate's profile. Every generated bullet must be traceable to a source fact ID. Unsupported output is rejected by a validator before it reaches the user.
2. **Ranking sorts, it never filters.** The recruiter always sees every applicant. AI changes the order and adds a reason; it never removes a person from view or auto-rejects.
3. **A human makes every hiring decision.** No automated rejection, no automated advancement. The system recommends; a named user acts, and the action is logged.
4. **Every score is explained.** A numeric score with no justification and no evidence citation is not shipped to a user.
5. **The candidate owns their data.** Full export, full delete. A CV is visible to an employer only for a job the candidate actually applied to.
6. **No scraped listings.** Job content enters the system only from the employer who owns it or through an official API. No LinkedIn/board scraping — it is a ToS violation, an IP-ban risk, and a due-diligence problem the day anyone wants to acquire or invest.
7. **Protected attributes are never features.** Name, gender, age, photo, religion, marital status, and address are excluded from every scoring input. See `03-agent-specs.md` for the enforced field allowlist.

---

## 9. Success metrics

**North star:** weekly *tailored applications that a recruiter moves to Shortlisted*. It is the only metric that requires both sides to have gotten value.

| Area | Metric | v1 target |
|---|---|---|
| Candidate | Time from "apply" to tailored CV ready | < 90 s p95 |
| Candidate | Applications per active candidate per week | ≥ 4 |
| Candidate | Self-reported callback rate vs their pre-HireBridge baseline | +2× |
| Employer | Time to a reviewed shortlist for 200 applicants | < 30 min |
| Employer | Precision@10 — of the top 10 ranked, share the recruiter advances | ≥ 60% |
| Employer | Recruiter agreement with the stated reason ("does this explanation make sense?") | ≥ 80% |
| Platform | Agent cost per application | < $0.05 |
| Platform | Interview report generation | < 60 s after session end |
| Trust | Fabrication validator catch rate on a seeded adversarial set | 100% blocked |

---

## 10. Competitive landscape

| Player | What it does | Where the gap is |
|---|---|---|
| BDJobs / local boards | Listings + CV bank | No tailoring, no ranking, no interview prep; keyword search only |
| LinkedIn | Network + Easy Apply + recruiter seats | Priced for enterprise; recruiter tooling not accessible to a 30-person SME; no CV rewriting |
| Jobscan / Teal | ATS keyword match score for candidates | Candidate-only; a score, not a rewritten CV; no employer side |
| HireVue / Interviewer.AI | Video interview + scoring | Enterprise pricing; video-based inference carries real bias and regulatory exposure |
| Paradox (Olivia) | Conversational recruiting at volume | Built for high-volume hourly hiring, not 5-role knowledge-work pipelines |
| Manatal / Zoho Recruit | Affordable ATS with AI match | Match score without evidence; no candidate-side product at all |

**HireBridge's wedge:** the only product where the *same structured understanding* of a CV serves both the candidate (tailoring, interview prep) and the employer (ranked, explained shortlist) — sold at a local price point, handling local CV conventions.

---

## 11. Business model

| Segment | Plan | Price (indicative) | Includes |
|---|---|---|---|
| Candidate | Free | ৳0 | 3 tailored CVs + 1 mock interview / month |
| Candidate | Pro | ৳500 / month | Unlimited tailoring, 10 interviews, priority processing, all templates |
| Employer | Starter | ৳3,000 / month | 3 active jobs, ranking, 2 seats |
| Employer | Growth | ৳8,000 / month | 10 active jobs, unlimited seats, pipeline analytics, API access |
| Agency | Custom | — | White-label, multi-client workspaces |

Employer revenue is the real business; the candidate tier exists to create supply and a distribution loop. Do not build billing in v1 — invoice design partners manually until the value is proven.

---

## 12. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| CV fabrication damages a candidate's credibility | Critical | Grounded generation + automated fact validator + diff view the user must approve before export |
| Biased ranking causes discriminatory outcomes | Critical | Protected-attribute allowlist on scoring inputs; sort-never-filter; logged human decision; periodic disparity audit across the ranked set |
| Scraping job boards → ToS breach / IP ban | High | Rule 6: employer-owned content and official APIs only |
| CV corpus is dense PII | High | Encryption at rest, field-level redaction before LLM calls, retention policy, no raw CVs in provider logs (zero-retention endpoints) |
| LLM + voice cost outruns revenue | High | Model tiering, embedding and parse caching, per-org budget ceilings, hard per-run token caps, cost logged per agent run |
| Two-sided cold start | High | Launch employer-first with 3–5 design-partner companies; candidates follow the jobs. Candidate tools work standalone, so they have value even with zero listings |
| Voice latency/cost makes interviews unusable | Medium | Text-first in v1; voice only after the question and evaluation quality is proven |
| Scope sprawl across five pillars | Medium | Phase gates in `05-roadmap.md`; a phase does not start until the previous one's exit criteria pass |

---

## 13. Open questions

1. Does the first paying employer want a full ATS pipeline, or only the ranked shortlist bolted onto their existing email workflow?
2. Do candidates trust a tailored CV enough to send it unedited, or is the diff-approval step mandatory forever?
3. Is guest apply (no account) worth the drop in profile quality it causes?
4. Which of Bangla CV content, PDF-scan OCR, and multi-column CV layouts is the biggest parsing failure source? Needs a 100-CV sample study before P1 build.
5. Does the interview report have standalone paid value, independent of applying to anything?
