from __future__ import annotations

from fastapi import APIRouter

from app.recruitment.api import RecruitmentApiCapabilities, get_recruitment_api_capabilities


router = APIRouter(tags=["recruitment"])


@router.get("/api/recruitment/capabilities", response_model=RecruitmentApiCapabilities)
def recruitment_capabilities() -> RecruitmentApiCapabilities:
    """Expose Recruitment contracts and safety boundaries without mutating state."""

    return get_recruitment_api_capabilities()


__all__ = ["router"]
