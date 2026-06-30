from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DBSessionDep, RequestContext, get_request_context
from app.services.public_properties import (
    apply_public_filters,
    favorite_lookup,
    get_public_submission_or_404,
    list_public_submissions,
    pagination_meta,
    serialize_property_detail,
    serialize_property_listing,
    sort_public_rows,
)
from app.utils.api_response import success_response

router = APIRouter()
ContextDep = Annotated[RequestContext, Depends(get_request_context)]


@router.get("")
def list_properties(
    db: DBSessionDep,
    context: ContextDep,
    page: int = 1,
    pageSize: int = 10,
    category: str | None = None,
    status: str | None = None,
    sort: str | None = "newest",
    type: str | None = None,
    location: str | None = None,
    city: str | None = None,
    locations: str | None = None,
    budgetMin: float | None = None,
    budgetMax: float | None = None,
    bedrooms: int | None = None,
    rooms: int | None = None,
    bathrooms: int | None = None,
    parking: int | None = None,
    propertyAge: str | None = None,
    floorLevel: str | None = None,
    furnitureStatus: str | None = None,
    minArea: float | None = None,
    maxArea: float | None = None,
    minPlotArea: float | None = None,
    maxPlotArea: float | None = None,
    governorate: str | None = None,
    directorate: str | None = None,
    village: str | None = None,
    parcelName: str | None = None,
    amenities: str | None = None,
    similar_to: str | None = None,
) -> dict:
    page = max(page, 1)
    pageSize = max(min(pageSize, 100), 1)
    rows = list_public_submissions(db)
    rows = apply_public_filters(
        rows,
        category=category,
        status=status,
        type=type,
        city=city or location,
        locations=locations,
        budgetMin=budgetMin,
        budgetMax=budgetMax,
        bedrooms=bedrooms,
        rooms=rooms,
        bathrooms=bathrooms,
        parking=parking,
        propertyAge=propertyAge,
        floorLevel=floorLevel,
        furnitureStatus=furnitureStatus,
        minArea=minArea,
        maxArea=maxArea,
        minPlotArea=minPlotArea,
        maxPlotArea=maxPlotArea,
        governorate=governorate,
        directorate=directorate,
        village=village,
        parcelName=parcelName,
        amenities=amenities,
        similar_to=similar_to,
        db=db,
    )
    rows = sort_public_rows(rows, sort)
    total = len(rows)
    page_rows = rows[(page - 1) * pageSize : page * pageSize]
    favorites = favorite_lookup(db, context.user_id) if context.user_id else {}
    items = []
    for submission, user in page_rows:
        favorite = favorites.get(submission.property_id or submission.id)
        items.append(
            serialize_property_listing(
                db,
                submission,
                submitter=user,
                favorite_id=favorite.id if favorite else None,
                user_id=context.user_id,
            )
        )
    pagination = pagination_meta(total, page, pageSize)
    return success_response({"items": items}, meta={"pagination": pagination})


@router.get("/{property_id}/similar")
def get_similar_properties(property_id: str, db: DBSessionDep, context: ContextDep) -> dict:
    rows = list_public_submissions(db)
    rows = apply_public_filters(rows, similar_to=property_id, db=db)
    rows = sort_public_rows(rows, "newest")[:6]
    favorites = favorite_lookup(db, context.user_id) if context.user_id else {}
    items = []
    for submission, user in rows:
        favorite = favorites.get(submission.property_id or submission.id)
        items.append(
            serialize_property_listing(
                db,
                submission,
                submitter=user,
                favorite_id=favorite.id if favorite else None,
                user_id=context.user_id,
            )
        )
    return success_response({"items": items})


@router.get("/{property_id}")
def get_property(property_id: str, db: DBSessionDep) -> dict:
    submission, user = get_public_submission_or_404(db, property_id)
    return success_response(serialize_property_detail(db, submission, submitter=user))
