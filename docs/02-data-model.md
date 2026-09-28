# Data Model

> Postgres 16 + pgvector. Conventions: UUIDv7 primary keys, `created_at`/`updated_at` on every
> table, soft delete via `deleted_at` only where recovery matters, snake_case, plural table names.
> Last updated 2026-09-28.

## 1. Entity map

```
organizations ──┬── memberships ──── users ──┬── candidate_profiles ── profile_facts
                │                             │         │
                └── jobs ──┬── job_embeddings │         └── resumes ── resume_versions
                           │                  │
                           └── applications ──┴── application_scores
                                   │
                                   ├── application_events   (audit)
                                   └── interview_sessions ──┬── interview_turns
                                                            └── interview_reports

agent_runs      (every LLM invocation, cross-cutting)
files           (every uploaded/generated artifact)
audit_logs      (every human decision)
```

## 2. Identity & tenancy

### `organizations`
`id`, `name`, `slug` (unique), `logo_file_id`, `website`, `plan`, `monthly_token_budget`,
`tokens_used_this_period`, `created_at`

Candidates do **not** belong to an organization. Only employers do.

### `users`
`id`, `clerk_user_id` (unique), `email` (unique, citext), `full_name`, `type`
(`candidate` | `employer` | `platform_admin`), `created_at`, `last_active_at`

Auth lives in Clerk; this table is a local mirror for foreign keys and joins.

### `memberships`
`id`, `org_id`, `user_id`, `role` (`org_admin` | `recruiter` | `hiring_manager`), `invited_by`,
`accepted_at` — unique `(org_id, user_id)`

**Tenancy rule:** every employer-scoped query filters on `org_id` derived from the JWT, enforced
in the repository layer, with Postgres RLS on `jobs`, `applications`, and `application_scores`
as a second line of defence.

## 3. Candidate domain

### `candidate_profiles`
`id`, `user_id` (unique), `headline`, `summary`, `location`, `years_experience`,
`open_to_work`, `preferred_roles` (text[]), `expected_salary_min/max`, `embedding` vector(1536),
`embedding_model`, `embedding_updated_at`, `completeness_score`

### `profile_facts` — the grounding table
This is the backbone of the no-fabrication rule.

| Column | Notes |
|---|---|
| `id` | **The `fact_id` every generated CV bullet must cite** |
| `profile_id` | FK |
| `kind` | `experience` \| `education` \| `skill` \| `project` \| `certification` \| `award` \| `publication` \| `language` |
| `payload` | JSONB, shape varies by `kind` |
| `source` | `parsed_resume` \| `user_entered` \| `user_edited` |
| `source_resume_id` | nullable, provenance |
| `confidence` | parser confidence 0–1 |
| `verified_by_user` | boolean — user confirmed after parsing |
| `start_date` / `end_date` | nullable, for ordering and gap detection |

Example `payload` for `kind = 'experience'`:
```json
{
  "company": "Autofy Solution",
  "title": "AI Engineer",
  "employment_type": "full_time",
  "bullets": [
    { "id": "b1", "text": "Built a production RAG chatbot serving customer queries" }
  ],
  "tech": ["Python", "FastAPI", "pgvector"]
}
```

Bullet IDs are addressable as `fact_id#bullet_id`, so a tailored CV line cites exactly the source
it rephrases.

### `resumes` / `resume_versions`
`resumes`: `id`, `user_id`, `label`, `is_base`, `created_at`

`resume_versions`: `id`, `resume_id`, `version` (int), `kind` (`base` | `tailored`),
`target_job_id` (nullable), `content` JSONB (structured, render-agnostic), `citations` JSONB
(`{line_id: [fact_id, ...]}`), `template`, `pdf_file_id`, `agent_run_id`,
`validator_status` (`passed` | `passed_with_warnings` | `failed`),
`approved_by_user_at` (nullable), `created_at`

A tailored version is never auto-sent. `approved_by_user_at` must be set before it can attach to
an application — Product Brief §8 rule 1 enforced at the data layer.

## 4. Employer domain

### `jobs`
`id`, `org_id`, `created_by`, `title`, `slug` (unique per org), `description_raw`,
`description_structured` JSONB, `seniority`, `employment_type`, `work_mode`
(`onsite`|`hybrid`|`remote`), `location`, `salary_min/max`, `currency`,
`must_have_skills` text[], `nice_to_have_skills` text[], `min_years`, `max_years`,
`status` (`draft`|`published`|`paused`|`closed`), `published_at`, `closes_at`,
`embedding` vector(1536), `search_vector` tsvector (generated)

Indexes: `GIN(search_vector)`, `HNSW(embedding vector_cosine_ops)`, `(org_id, status)`,
`(status, published_at DESC)` for the public board.

`description_structured` shape:
```json
{
  "responsibilities": ["..."],
  "requirements": [{ "text": "3+ years Python", "type": "must", "skill": "Python", "years": 3 }],
  "benefits": ["..."],
  "team_context": "...",
  "red_flags": []
}
```

### `applications`
`id`, `job_id`, `candidate_user_id`, `resume_version_id`, `cover_note`,
`stage` (`new`|`shortlisted`|`interview`|`offer`|`hired`|`rejected`|`withdrawn`),
`stage_changed_at`, `stage_changed_by`, `source` (`platform`|`guest`|`email_import`),
`profile_snapshot` JSONB, `created_at` — unique `(job_id, candidate_user_id)`

`profile_snapshot` freezes the candidate's data at apply time. The candidate editing their
profile next week must not silently change what the recruiter evaluated.

### `application_scores`
`id`, `application_id` (unique per `scoring_version`), `scoring_version`,
`composite` numeric(5,2), `lexical`, `semantic`, `rules` (all numeric),
`weights` JSONB, `justification` text (nullable — generated lazily),
`evidence` JSONB (`[{claim, fact_id, job_requirement}]`),
`missing_requirements` text[], `agent_run_id`, `created_at`

Scores are **versioned, not overwritten**. Re-ranking after a weight change writes a new row, so
"why was this candidate #3 last week?" stays answerable.

### `application_events` — audit trail
`id`, `application_id`, `actor_user_id` (nullable for system), `actor_type` (`user`|`system`),
`event` (`created`|`viewed`|`stage_changed`|`note_added`|`scored`|`email_sent`),
`payload` JSONB, `created_at`

Product Brief §8 rule 3 lives here: every stage change carries a named human actor.

## 5. Interview domain

### `interview_sessions`
`id`, `candidate_user_id`, `job_id` (nullable — practice against a pasted JD),
`application_id` (nullable), `mode` (`text`|`voice`), `status`
(`created`|`in_progress`|`completed`|`abandoned`), `question_set` JSONB,
`current_index`, `started_at`, `completed_at`, `duration_seconds`,
`consent_recording` boolean, `audio_retention_until` (nullable)

`question_set` is generated up front and frozen, so a dropped connection resumes the same
interview rather than a new one.

### `interview_turns`
`id`, `session_id`, `index`, `question_id`, `question_text`, `competency`,
`answer_text`, `answer_audio_file_id` (nullable), `answer_duration_seconds`,
`is_followup`, `parent_turn_id` (nullable), `asked_at`, `answered_at`

### `interview_reports`
`id`, `session_id` (unique), `overall_score` numeric(4,2),
`competency_scores` JSONB (`{communication: 3.5, technical_depth: 4.0, ...}`),
`strengths` text[], `gaps` text[],
`suggestions` JSONB (`[{priority, area, action, resource}]`),
`per_turn_feedback` JSONB, `agent_run_id`, `share_token` (nullable, unique), `created_at`

`share_token` allows a read-only public report link; revocable by nulling it.

## 6. Cross-cutting

### `agent_runs` — audit log, cost ledger, and eval dataset in one table
`id`, `agent` (`resume_parser`|`jd_parser`|`cv_tailor`|`question_gen`|`interview_conductor`|
`evaluator`|`improver`|`ranker_justifier`), `prompt_version`, `model`, `provider`,
`subject_type` + `subject_id` (polymorphic), `org_id` (nullable), `user_id`,
`status` (`queued`|`running`|`succeeded`|`failed`|`aborted_budget`),
`input_ref` JSONB, `output_ref` JSONB, `input_tokens`, `output_tokens`, `cost_usd`,
`latency_ms`, `attempt`, `validator_status`, `error_code`, `error_message`,
`trace_id`, `created_at`, `finished_at`

Indexes: `(agent, created_at DESC)`, `(org_id, created_at DESC)`, `(status)`.

Never delete rows here. Partition by month once it grows.

### `files`
`id`, `owner_user_id`, `org_id` (nullable), `kind` (`resume_upload`|`generated_pdf`|
`interview_audio`|`org_logo`), `storage_key`, `mime`, `size_bytes`, `checksum_sha256`,
`av_scan_status`, `retention_until`, `created_at`

`checksum_sha256` doubles as the parse cache key — the same CV uploaded twice is parsed once.

### `audit_logs`
`id`, `actor_user_id`, `org_id`, `action`, `target_type`, `target_id`, `ip`, `user_agent`,
`payload` JSONB, `created_at` — append-only, for anything a regulator or an employer might ask about.

## 7. Search & ranking implementation

```sql
-- hybrid candidate scoring against a job (conceptual)
SELECT a.id,
       ts_rank(cp.search_vector, websearch_to_tsquery(:must_have_terms))      AS lexical,
       1 - (cp.embedding <=> :job_embedding)                                  AS semantic,
       rules_score(cp.years_experience, :min_years, cp.location, :job_location) AS rules
FROM applications a
JOIN candidate_profiles cp ON cp.user_id = a.candidate_user_id
WHERE a.job_id = :job_id;
```

Composite = `0.25·lexical + 0.45·semantic + 0.30·rules`, weights stored per job in
`application_scores.weights` so they are tunable and auditable rather than buried in code.

**Embedding dimension** is pinned at 1536 with the model recorded in `embedding_model`.
Changing models requires a backfill job — never mix dimensions or models in one index.

## 8. Protected-attribute exclusion

Scoring input is an **allowlist**, not a denylist:

```
ALLOWED_SCORING_FIELDS = {
  years_experience, skills, job_titles, employers, education_level,
  field_of_study, certifications, project_descriptions, languages_spoken,
  location_city (work-authorization / commute only)
}
```

Never passed to a scoring model: `full_name`, `email`, `phone`, `photo`, `date_of_birth`, `age`,
`gender`, `marital_status`, `religion`, `nationality`, `father_name`, `address`, `nid`.

A unit test asserts that the scoring payload builder emits no key outside the allowlist. That test
failing is a release blocker.

## 9. Retention

| Data | Retention |
|---|---|
| Candidate profile & CVs | Until the user deletes; full export on request |
| Application + snapshot | 2 years after the job closes, then anonymized |
| Interview audio | 30 days default, `audit_retention_until` enforced by a nightly job |
| Interview transcripts & reports | Until the user deletes |
| `agent_runs` inputs/outputs | 90 days for payload refs, metadata kept indefinitely |
| `audit_logs` | 5 years, append-only |

Account deletion cascades to profiles, resumes, sessions, and files; it anonymizes rather than
deletes `applications` (the employer's hiring record is their legitimate business record) and
leaves `audit_logs` intact with the actor tokenized.

## 10. Migration rules

1. Expand/contract only — add nullable, backfill, then switch reads, then drop in a later deploy.
2. No destructive change in the same deploy as the code that depends on it.
3. Every migration is reversible or explicitly documented as irreversible in its docstring.
4. Index creation on a populated table uses `CONCURRENTLY`.
