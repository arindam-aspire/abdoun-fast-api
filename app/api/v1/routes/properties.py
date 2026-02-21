from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.property import Property
from app.schemas.property import (
    PropertyDetail,
    PropertySearchResult,
    PropertyListResponse,
)
from app.utils.constants import ErrorMessages, Defaults
from app.utils.status_codes import STATUS_NOT_FOUND
 
router = APIRouter()

DBSessionDep = Annotated[Session, Depends(get_db)]


@router.get("", response_model=PropertyListResponse)
def list_properties(
    db: DBSessionDep,
    limit: int = Defaults.DEFAULT_LIMIT,
    offset: int = Defaults.DEFAULT_OFFSET,
) -> PropertyListResponse:
    stmt = (
        select(Property)
        .order_by(Property.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    results = db.execute(stmt).scalars().all()

    items = [
        PropertySearchResult.from_orm_obj(p)
        for p in results
    ]
    return PropertyListResponse(items=items, total=len(items))


@router.get("/{property_id}", response_model=PropertyDetail)
def get_property(
    property_id: int,
    db: DBSessionDep,
) -> PropertyDetail:
    prop = db.get(Property, property_id)
    if not prop:
        raise HTTPException(
            status_code=STATUS_NOT_FOUND,
            detail=ErrorMessages.PROPERTY_NOT_FOUND
        )
    return PropertyDetail.from_orm_obj(prop)



