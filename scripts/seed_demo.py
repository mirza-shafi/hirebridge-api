"""Seed a demo organisation, job and applicants.

Idempotent: re-running replaces the demo rows rather than duplicating them, so it is safe
to run on every `make demo`.

    uv run python scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.agents.embeddings import get_embedding_client
from app.core.config import settings
from app.db.session import SessionFactory, dispose_engine
from app.models import (
    Application,
    ApplicationScore,
    CandidateProfile,
    Job,
    JobStatus,
    Membership,
    Organization,
    ProfileFact,
    User,
)
from app.repositories.ranking import score_applications
from app.services.embedding_text import job_embedding_text, profile_corpus

DEMO_ORG_SLUG = "autofy-demo"
DEV_CLERK_USER = "user_dev_local"
# Must match DEV_PRINCIPAL.org_id, or org-scoped endpoints cannot resolve the caller.
DEV_CLERK_ORG = "org_dev_local"

JD = """\
Senior Backend Engineer — Autofy Solution, Dhaka (hybrid)

We are looking for a backend engineer to own the retrieval and ranking services behind our
customer support assistant.

Responsibilities:
- Own the retrieval and ranking services behind our customer-support assistant
- Take FastAPI services from prototype to production, including on-call
- Work directly with the two engineers who built the current pipeline

Requirements:
- 3+ years building backend services in Python (required)
- Production experience with PostgreSQL (required)
- Comfortable owning a service end to end (required)
- Familiarity with vector search or retrieval systems is a plus
- Exposure to Next.js is a bonus

Salary: BDT 90,000-140,000 per month.
"""

CANDIDATES: list[dict] = [
    {
        "name": "Rakib Hasan", "city": "Dhaka", "years": 4.0,
        "headline": "Backend Engineer",
        "experience": [
            ("Autofy Solution", "AI Engineer", ["python", "fastapi", "postgres"],
             ["Built a retrieval chatbot for customer support",
              "Owned the ranking service end to end"]),
        ],
        "education": ("BRAC University", "B.Sc.", "Computer Science"),
    },
    {
        "name": "Nusrat Jahan", "city": "Dhaka", "years": 5.0,
        "headline": "Senior Backend Developer",
        "experience": [
            ("SmartData Technologies", "Senior Backend Developer",
             ["python", "postgres", "kubernetes", "docker"],
             ["Ran the payments service on Kubernetes",
              "Migrated a monolith to Postgres with zero downtime"]),
        ],
        "education": ("NSU", "B.Sc.", "Computer Science"),
    },
    {
        "name": "Tanvir Ahmed", "city": "Chittagong", "years": 4.0,
        "headline": "Node.js Engineer",
        "experience": [
            ("Beximco IT", "Backend Engineer", ["nodejs", "mongodb", "rest_api"],
             ["Owned three Node services in production",
              "Designed the public REST API"]),
        ],
        "education": ("CUET", "B.Sc.", "Computer Science"),
    },
    {
        "name": "Sadia Islam", "city": "Dhaka", "years": 1.0,
        "headline": "Frontend Developer",
        "experience": [
            ("Freelance", "Frontend Developer", ["react", "nextjs", "tailwind"],
             ["Built marketing sites in Next.js"]),
        ],
        "education": ("AIUB", "B.Sc.", "Computer Science"),
    },
    {
        "name": "Imran Kabir", "city": "Dhaka", "years": 3.0,
        "headline": "Python Developer",
        "experience": [
            ("Mevrik", "Python Developer", ["python", "django", "postgres"],
             ["Maintained a Django platform with Postgres",
              "Assisted with an async migration"]),
        ],
        "education": ("DU", "B.Sc.", "Computer Science"),
    },
]


async def main() -> None:
    random.seed(7)
    async with SessionFactory() as session:
        org = (
            await session.execute(
                select(Organization).where(Organization.slug == DEMO_ORG_SLUG)
            )
        ).scalar_one_or_none()

        if org:
            org.clerk_org_id = DEV_CLERK_ORG
            jobs = (
                await session.execute(select(Job).where(Job.org_id == org.id))
            ).scalars().all()
            for job in jobs:
                await session.delete(job)
            await session.flush()
            print("cleared previous demo job(s)")
        else:
            org = Organization(name="Autofy Solution", slug=DEMO_ORG_SLUG,
                               clerk_org_id=DEV_CLERK_ORG,
                               website="https://autofybit.tech")
            session.add(org)
            await session.flush()

        # The DEV_AUTH identity, so the seeded org is the one you land in.
        dev_user = (
            await session.execute(select(User).where(User.clerk_user_id == DEV_CLERK_USER))
        ).scalar_one_or_none()
        if dev_user is None:
            dev_user = User(clerk_user_id=DEV_CLERK_USER, email="dev@hirebridge.local",
                            full_name="Demo Recruiter", type="employer")
            session.add(dev_user)
            await session.flush()
            session.add(Membership(org_id=org.id, user_id=dev_user.id, role="org_admin"))

        job = Job(
            org_id=org.id, created_by=dev_user.id,
            title="Senior Backend Engineer",
            slug="senior-backend-engineer-demo",
            description_raw=JD,
            seniority="senior", employment_type="full_time", work_mode="hybrid",
            location="Dhaka", salary_min=90000, salary_max=140000, currency="BDT",
            must_have_skills=["python", "postgres", "rest_api"],
            nice_to_have_skills=["vector_search", "nextjs"],
            min_years=3,
            description_structured={
                "responsibilities": [
                    "Own the retrieval and ranking services behind our customer-support assistant",
                    "Take FastAPI services from prototype to production, including on-call",
                    "Work directly with the two engineers who built the current pipeline",
                ],
                "requirements": [
                    {"text": "3+ years building backend services in Python", "type": "must",
                     "skill": "Python", "years": 3},
                    {"text": "Production experience with PostgreSQL", "type": "must",
                     "skill": "PostgreSQL", "years": None},
                    {"text": "Comfortable owning a service end to end", "type": "must",
                     "skill": None, "years": None},
                    {"text": "Familiarity with vector search or retrieval systems", "type": "nice",
                     "skill": "vector search", "years": None},
                    {"text": "Exposure to Next.js", "type": "nice", "skill": "Next.js",
                     "years": None},
                ],
                "benefits": [],
                "team_context": "A small backend team that owns the assistant end to end.",
            },
            red_flags=[],
            status=JobStatus.PUBLISHED.value,
            published_at=datetime.now(UTC) - timedelta(days=8),
            closes_at=datetime.now(UTC) + timedelta(days=60),
        )
        session.add(job)
        await session.flush()

        embedder = get_embedding_client()
        job.embedding = (
            await embedder.embed(
                job_embedding_text(
                    title=job.title, seniority=job.seniority,
                    structured=job.description_structured,
                    must_have=job.must_have_skills, nice_to_have=job.nice_to_have_skills,
                ),
                model=settings.embedding_model,
            )
        ).vector
        job.embedding_model = settings.embedding_model

        for index, spec in enumerate(CANDIDATES):
            email = f"demo{index}@hirebridge.local"
            user = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if user is None:
                user = User(clerk_user_id=f"user_demo_{index}", email=email,
                            full_name=spec["name"], type="candidate")
                session.add(user)
                await session.flush()

            profile = (
                await session.execute(
                    select(CandidateProfile).where(CandidateProfile.user_id == user.id)
                )
            ).scalar_one_or_none()
            if profile is None:
                profile = CandidateProfile(user_id=user.id)
                session.add(profile)
                await session.flush()
            else:
                await session.execute(
                    delete(ProfileFact).where(ProfileFact.profile_id == profile.id)
                )

            profile.headline = spec["headline"]
            profile.location_city = spec["city"]
            profile.years_experience = spec["years"]
            profile.completeness_score = 80

            fact_rows: list[dict] = []
            for position, (company, title, tech, bullets) in enumerate(spec["experience"]):
                payload = {
                    "company": company, "title": title, "tech": tech,
                    "bullets": [{"id": f"b{i+1}", "text": b} for i, b in enumerate(bullets)],
                }
                session.add(ProfileFact(
                    profile_id=profile.id, kind="experience", payload=payload,
                    source="user_entered", confidence=1.0, verified_by_user=True,
                    position=position,
                ))
                fact_rows.append({"kind": "experience", "payload": payload})

            institution, degree, field = spec["education"]
            edu_payload = {"institution": institution, "degree": degree, "field": field}
            session.add(ProfileFact(
                profile_id=profile.id, kind="education", payload=edu_payload,
                source="user_entered", confidence=1.0, verified_by_user=True, position=90,
            ))
            fact_rows.append({"kind": "education", "payload": edu_payload})

            corpus = profile_corpus(
                headline=profile.headline, summary=None, fact_rows=fact_rows
            )
            # One corpus feeds both halves of ranking: the tsvector and the embedding.
            profile.search_text = corpus
            profile.embedding = (
                await embedder.embed(corpus, model=settings.embedding_model)
            ).vector
            profile.embedding_model = settings.embedding_model

            session.add(Application(
                job_id=job.id, candidate_user_id=user.id,
                created_at=datetime.now(UTC) - timedelta(days=random.randint(1, 7)),
            ))

        await session.flush()

        # Score them with the real ranking pipeline, so the list you see is genuine output.
        scored = await score_applications(session, job)
        for application_id, result in scored:
            session.add(ApplicationScore(application_id=application_id, **result.as_row()))

        await session.commit()

        print(f"seeded org={org.slug} job={job.slug} applicants={len(scored)}")
        for rank_index, (_, result) in enumerate(scored, start=1):
            print(f"  #{rank_index}  composite={result.composite:>6}  "
                  f"missing={result.coverage.missing_must or '-'}")

    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
