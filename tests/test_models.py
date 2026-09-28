"""Model-level behaviour. Needs SQLAlchemy, so it lives outside the pure suites in
tests/agents/, which are runnable with nothing but pydantic installed.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.models import Job, ResumeVersion, StoredFile
from app.schemas.enums import ValidatorStatus


def test_unresolved_red_flag_blocks_publishing() -> None:
    job = Job(
        org_id=None, title="x", slug="x", description_raw="x",
        red_flags=[{"text": "Age below 30", "resolved": False}],
    )
    assert job.has_unresolved_red_flags is True

    job.red_flags = [{"text": "Age below 30", "resolved": True}]
    assert job.has_unresolved_red_flags is False

    job.red_flags = None
    assert job.has_unresolved_red_flags is False


def test_a_failed_validation_is_never_sendable() -> None:
    version = ResumeVersion(
        resume_id=None, content={},
        validator_status=ValidatorStatus.FAILED.value,
        approved_by_user_at=datetime.now(UTC),
    )
    assert version.is_sendable is False, "approval must not override a failed validation"


def test_unapproved_version_is_never_sendable() -> None:
    version = ResumeVersion(
        resume_id=None, content={},
        validator_status=ValidatorStatus.PASSED.value,
        approved_by_user_at=None,
    )
    assert version.is_sendable is False


def test_approved_and_validated_version_is_sendable() -> None:
    version = ResumeVersion(
        resume_id=None, content={},
        validator_status=ValidatorStatus.PASSED.value,
        approved_by_user_at=datetime.now(UTC),
    )
    assert version.is_sendable is True


def test_warned_version_can_still_be_sent_once_approved() -> None:
    version = ResumeVersion(
        resume_id=None, content={},
        validator_status=ValidatorStatus.PASSED_WITH_WARNINGS.value,
        approved_by_user_at=datetime.now(UTC),
    )
    assert version.is_sendable is True


def test_file_is_not_servable_until_scanned() -> None:
    file = StoredFile(
        kind="resume_upload", storage_key="k", mime="application/pdf",
        size_bytes=1, checksum_sha256="c", av_scan_status="pending",
    )
    assert file.is_servable is False
    file.av_scan_status = "clean"
    assert file.is_servable is True
