"""Dependency providers for feature taxonomy routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.feature_repository import FeatureRepository
from app.services.feature_service import FeatureService

DBSessionDep = Annotated[Session, Depends(get_db)]


def get_feature_repository(db: DBSessionDep) -> FeatureRepository:
    return FeatureRepository(db)


def get_feature_service(
    repo: FeatureRepository = Depends(get_feature_repository),
) -> FeatureService:
    return FeatureService(repo)
