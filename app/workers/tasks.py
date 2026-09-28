"""Agent tasks.

Every one follows the same shape: load the run, publish named progress steps, do the work,
persist. The step names are the copy the user reads while waiting, so they are written for a
person, not for a log (docs/03-ux-flows.md, "Waiting-state copy").
"""

from __future__ import annotations

import hashlib
import io
import logging
import uuid
from typing import Any

from sqlalchemy import select

from app.agents.cv_tailor.agent import CVTailorAgent
from app.agents.embeddings import content_hash, get_embedding_client
from app.agents.jd_parser.agent import JDParserAgent
from app.agents.jd_parser.mapping import slugify, to_job_fields
from app.agents.llm import get_llm_client
from app.agents.ranker.agent import DEFAULT_JUSTIFY_TOP_N, RankerJustifierAgent
from app.agents.resume_parser.agent import ResumeParserAgent
from app.agents.resume_parser.mapping import completeness_score, to_fact_rows
from app.core.config import settings
from app.models import (
    Application,
    ApplicationScore,
    CandidateProfile,
    Job,
    ProfileFact,
    Resume,
    ResumeVersion,
    StoredFile,
)
from app.repositories.ranking import score_applications
from app.schemas.resume import TailoredResume
from app.services import runs as run_service
from app.services.embedding_text import job_embedding_text, profile_corpus
from app.services.extraction import extract
from app.services.pdf.render import render_pdf
from app.services.resume_diff import compute_diff
from app.services.scoring_payload import build_scoring_payload
from app.services.storage import get_storage, storage_key
from app.workers.base import task_run


async def parse_resume(ctx: dict[str, Any], run_id: str, resume_id: str) -> dict[str, Any]:
    """Uploaded CV -> structured, citable profile facts."""
    async with task_run(run_id) as (session, run):
        resume = await session.get(Resume, uuid.UUID(resume_id))
        if resume is None:
            raise ValueError(f"Resume {resume_id} not found.")

        await run_service.mark_progress(session, run, step="reading_cv", pct=10)
        stored = await session.get(StoredFile, resume.source_file_id)
        if stored is None:
            raise ValueError("Resume has no source file.")

        raw = await get_storage().get(stored.storage_key)
        extraction = extract(io.BytesIO(raw), stored.mime)
        if not extraction.is_usable:
            # Say so rather than presenting a near-empty profile as complete.
            await run_service.mark_failed(
                session, run, code="unreadable_document",
                message=(
                    "We could not read enough text from this file. It may be a scanned "
                    "image — try a text PDF, or enter your details manually."
                ),
            )
            return {"ok": False, "needs_ocr": extraction.needs_ocr}

        await run_service.mark_progress(session, run, step="extracting", pct=35)
        agent = ResumeParserAgent(session, get_llm_client(), settings.model_small or "small")
        parsed = await agent.parse(run=run, text=extraction.text)

        await run_service.mark_progress(session, run, step="organizing", pct=75)
        profile = await _profile_for(session, resume.user_id)
        profile.headline = parsed.headline or profile.headline
        profile.summary = parsed.summary or profile.summary
        profile.location_city = parsed.contact.location_city or profile.location_city

        rows = to_fact_rows(parsed)
        for row in rows:
            session.add(
                ProfileFact(profile_id=profile.id, source_resume_id=resume.id, **row)
            )
        profile.completeness_score = completeness_score(rows)
        # Keep the full-text corpus in step with the facts; otherwise lexical ranking sees
        # only the headline (migration 0004).
        profile.search_text = profile_corpus(
            headline=profile.headline, summary=profile.summary, fact_rows=rows
        )
        await session.flush()

        await run_service.mark_succeeded(
            session, run,
            output_ref={
                "profile_id": str(profile.id),
                "facts": len(rows),
                "needs_review": sum(1 for r in rows if r["confidence"] < 0.7),
                "warnings": parsed.extraction_warnings + extraction.warnings,
            },
        )
        return {"ok": True, "facts": len(rows)}


async def parse_job(ctx: dict[str, Any], run_id: str, job_id: str) -> dict[str, Any]:
    """Pasted JD -> structured job, with discriminatory phrasing flagged."""
    async with task_run(run_id) as (session, run):
        job = await session.get(Job, uuid.UUID(job_id))
        if job is None:
            raise ValueError(f"Job {job_id} not found.")

        await run_service.mark_progress(session, run, step="reading_jd", pct=20)
        agent = JDParserAgent(session, get_llm_client(), settings.model_small or "small")
        parsed = await agent.parse(run=run, description=job.description_raw)

        for field, value in to_job_fields(parsed).items():
            setattr(job, field, value)
        job.slug = slugify(job.title, suffix=str(job.id)[:8])

        await run_service.mark_progress(session, run, step="embedding", pct=70)
        await _embed_job(session, job)

        await run_service.mark_succeeded(
            session, run,
            output_ref={
                "job_id": str(job.id),
                "must_have": job.must_have_skills,
                "red_flags": len(job.red_flags or []),
            },
        )
        return {"ok": True, "red_flags": len(job.red_flags or [])}


async def tailor_cv(
    ctx: dict[str, Any], run_id: str, resume_id: str, job_id: str | None, jd_text: str | None
) -> dict[str, Any]:
    """The candidate-side wedge. Fails closed: a validation failure renders no PDF."""
    async with task_run(run_id) as (session, run):
        resume = await session.get(Resume, uuid.UUID(resume_id))
        if resume is None:
            raise ValueError(f"Resume {resume_id} not found.")

        await run_service.mark_progress(session, run, step="reading_jd", pct=10)
        job_text = jd_text or ""
        job: Job | None = None
        if job_id:
            job = await session.get(Job, uuid.UUID(job_id))
            if job is None:
                raise ValueError(f"Job {job_id} not found.")
            job_text = job_embedding_text(
                title=job.title, seniority=job.seniority,
                structured=job.description_structured,
                must_have=job.must_have_skills, nice_to_have=job.nice_to_have_skills,
            )

        profile = await _profile_for(session, resume.user_id)
        facts = (
            await session.execute(
                select(ProfileFact)
                .where(ProfileFact.profile_id == profile.id)
                .order_by(ProfileFact.position)
            )
        ).scalars().all()

        fact_rows = [
            {
                "id": str(f.id), "kind": f.kind, "payload": f.payload,
                "start_date": f.start_date, "end_date": f.end_date,
            }
            for f in facts
        ]

        await run_service.mark_progress(session, run, step="matching", pct=35)
        agent = CVTailorAgent(session, get_llm_client(), settings.model_large or "large")

        # The runner publishes "validating" itself once generation returns; naming it here
        # keeps the step order honest for a client that reconnects mid-run.
        await run_service.mark_progress(session, run, step="validating", pct=80)
        tailored, context = await agent.tailor(
            run=run, fact_rows=fact_rows, job_text=job_text
        )

        base = await _base_version(session, resume)
        diff = compute_diff(base, tailored) if base else None

        version = ResumeVersion(
            resume_id=resume.id,
            version=await _next_version(session, resume.id),
            kind="tailored",
            target_job_id=job.id if job else None,
            target_jd_hash=hashlib.sha256((jd_text or "").encode()).hexdigest() if jd_text else None,
            content=tailored.model_dump(),
            citations={
                line.line_id: line.source_fact_ids for line in tailored.lines
            },
            agent_run_id=run.id,
            validator_status=run.validator_status,
            validator_findings=context.get("validator_findings"),
        )
        session.add(version)
        await session.flush()

        # Rendered here, in the worker, because validation has passed by this point and a
        # failed validation never reaches this line. Approval gates the *download*, not the
        # render — so "Approve and download" is instant rather than starting a second job.
        await run_service.mark_progress(session, run, step="rendering", pct=92)
        pdf_file_id = await _render_and_store(
            session, resume=resume, version=version, tailored=tailored,
            full_name=await _display_name(session, resume.user_id),
        )
        version.pdf_file_id = pdf_file_id
        await session.flush()

        await run_service.mark_succeeded(
            session, run,
            output_ref={
                "resume_version_id": str(version.id),
                "validator_status": run.validator_status,
                "diff": diff.summary.as_dict() if diff else None,
                "pdf_ready": pdf_file_id is not None,
            },
        )
        return {"ok": True, "resume_version_id": str(version.id)}


async def rank_job(ctx: dict[str, Any], run_id: str, job_id: str) -> dict[str, Any]:
    """Score every applicant, then justify the top N.

    Scores all; hides none (product rule 2). Justification is lazy because most of a long
    list is never opened.
    """
    async with task_run(run_id) as (session, run):
        job = await session.get(Job, uuid.UUID(job_id))
        if job is None:
            raise ValueError(f"Job {job_id} not found.")

        await run_service.mark_progress(session, run, step="scoring", pct=15)
        scored = await score_applications(session, job)

        version = 1 + await _latest_scoring_version(session, job.id)
        for application_id, result in scored:
            session.add(
                ApplicationScore(
                    application_id=application_id,
                    **{**result.as_row(), "scoring_version": version},
                )
            )
        await session.flush()

        await run_service.mark_progress(session, run, step="justifying", pct=60)
        justifier = RankerJustifierAgent(session, get_llm_client(), settings.model_mid or "mid")
        job_text = job_embedding_text(
            title=job.title, seniority=job.seniority,
            structured=job.description_structured,
            must_have=job.must_have_skills, nice_to_have=job.nice_to_have_skills,
        )

        justified = 0
        for index, (application_id, result) in enumerate(scored[:DEFAULT_JUSTIFY_TOP_N]):
            neighbour = scored[index + 1][1] if index + 1 < len(scored) else None
            payload = await _scoring_payload_for(session, application_id)
            justification = await justifier.justify(
                run=run, job_text=job_text, candidate_payload=payload,
                result=result, neighbour=neighbour,
            )
            row = (
                await session.execute(
                    select(ApplicationScore).where(
                        ApplicationScore.application_id == application_id,
                        ApplicationScore.scoring_version == version,
                    )
                )
            ).scalar_one()
            row.justification = justification.summary
            row.evidence = [m.model_dump() for m in justification.matched]
            justified += 1

            if index % 5 == 0:
                pct = 60 + int(35 * index / max(1, min(len(scored), DEFAULT_JUSTIFY_TOP_N)))
                await run_service.mark_progress(session, run, step="justifying", pct=pct)

        await run_service.mark_succeeded(
            session, run,
            output_ref={
                "job_id": str(job.id), "scored": len(scored),
                "justified": justified, "scoring_version": version,
            },
        )
        return {"ok": True, "scored": len(scored)}


# --- helpers ----------------------------------------------------------------


async def _display_name(session: Any, user_id: uuid.UUID) -> str:
    from app.models import User

    user = await session.get(User, user_id)
    return (user.full_name if user and user.full_name else "") or "Candidate"


async def _render_and_store(
    session: Any,
    *,
    resume: Resume,
    version: ResumeVersion,
    tailored: TailoredResume,
    full_name: str,
) -> uuid.UUID | None:
    """Render the CV and store it.

    A rendering failure must not fail the whole run: the candidate still has a verified
    tailored CV and a diff to read, and the PDF can be regenerated. Losing the tailoring
    work over a font problem would be the worse outcome.
    """
    try:
        rendered = render_pdf(tailored, full_name=full_name, template=version.template)
    except Exception:
        logging.getLogger("hirebridge.worker").exception(
            "PDF rendering failed for version %s", version.id
        )
        return None

    key = storage_key(user_id=str(resume.user_id), kind="generated_pdf", filename="cv.pdf")
    await get_storage().put(key, rendered.content, content_type="application/pdf")

    stored = StoredFile(
        owner_user_id=resume.user_id,
        kind="generated_pdf",
        storage_key=key,
        mime="application/pdf",
        size_bytes=len(rendered.content),
        checksum_sha256=hashlib.sha256(rendered.content).hexdigest(),
        av_scan_status="clean",  # we generated it
    )
    session.add(stored)
    await session.flush()
    return stored.id


async def _profile_for(session: Any, user_id: uuid.UUID) -> CandidateProfile:
    profile = (
        await session.execute(
            select(CandidateProfile).where(CandidateProfile.user_id == user_id)
        )
    ).scalar_one_or_none()
    if profile is None:
        profile = CandidateProfile(user_id=user_id)
        session.add(profile)
        await session.flush()
    return profile


async def _base_version(session: Any, resume: Resume) -> TailoredResume | None:
    row = (
        await session.execute(
            select(ResumeVersion)
            .where(ResumeVersion.resume_id == resume.id, ResumeVersion.kind == "base")
            .order_by(ResumeVersion.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return TailoredResume.model_validate(row.content) if row else None


async def _next_version(session: Any, resume_id: uuid.UUID) -> int:
    latest = (
        await session.execute(
            select(ResumeVersion.version)
            .where(ResumeVersion.resume_id == resume_id)
            .order_by(ResumeVersion.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return (latest or 0) + 1


async def _latest_scoring_version(session: Any, job_id: uuid.UUID) -> int:
    latest = (
        await session.execute(
            select(ApplicationScore.scoring_version)
            .join(Application, Application.id == ApplicationScore.application_id)
            .where(Application.job_id == job_id)
            .order_by(ApplicationScore.scoring_version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return latest or 0


async def _scoring_payload_for(session: Any, application_id: uuid.UUID) -> dict[str, Any]:
    application = await session.get(Application, application_id)
    profile = await _profile_for(session, application.candidate_user_id)
    facts = (
        await session.execute(
            select(ProfileFact).where(ProfileFact.profile_id == profile.id)
        )
    ).scalars().all()
    return build_scoring_payload(
        facts=[],
        raw_facts=[{"kind": f.kind, "payload": f.payload} for f in facts],
        years_experience=float(profile.years_experience) if profile.years_experience else None,
        location_city=profile.location_city,
    )


async def _embed_job(session: Any, job: Job) -> None:
    client = get_embedding_client()
    text = job_embedding_text(
        title=job.title, seniority=job.seniority,
        structured=job.description_structured,
        must_have=job.must_have_skills, nice_to_have=job.nice_to_have_skills,
    )
    result = await client.embed(text, model=settings.embedding_model)
    job.embedding = result.vector
    job.embedding_model = result.model


async def embed_profile(ctx: dict[str, Any], profile_id: str) -> dict[str, Any]:
    """Refresh a candidate's vector. Cheap, idempotent, safe to re-run."""
    async with SessionFactoryScope() as session:
        profile = await session.get(CandidateProfile, uuid.UUID(profile_id))
        if profile is None:
            return {"ok": False}
        facts = (
            await session.execute(
                select(ProfileFact).where(ProfileFact.profile_id == profile.id)
            )
        ).scalars().all()
        text = profile_corpus(
            headline=profile.headline,
            summary=profile.summary,
            fact_rows=[{"kind": f.kind, "payload": f.payload} for f in facts],
        )
        profile.search_text = text
        digest = content_hash(text, settings.embedding_model)
        if profile.embedding is not None and profile.embedding_model == digest:
            return {"ok": True, "cached": True}

        result = await get_embedding_client().embed(text, model=settings.embedding_model)
        profile.embedding = result.vector
        profile.embedding_model = result.model
        await session.commit()
        return {"ok": True, "cached": False}


class SessionFactoryScope:
    """Small async-context wrapper so `embed_profile` reads like the other tasks."""

    async def __aenter__(self) -> Any:
        from app.db.session import SessionFactory

        self._session = SessionFactory()
        return await self._session.__aenter__()

    async def __aexit__(self, *exc: Any) -> None:
        await self._session.__aexit__(*exc)
