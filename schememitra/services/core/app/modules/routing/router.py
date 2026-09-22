from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.errors import not_found
from app.modules.routing import service
from app.modules.routing.districts import DISTRICTS, district_for_pincode

router = APIRouter(tags=["partners"])
Session = Annotated[AsyncSession, Depends(get_session)]


class PartnerCard(BaseModel):
    id: str
    name: str
    type: str
    state_code: str
    district_code: str
    district_name: str
    address: str
    lat: float
    lng: float
    distance_km: float
    languages: list[str]
    documents_needed: list[str]
    open_hours: str
    contact: dict[str, Any]
    schemes_supported: list[str]
    categories_supported: list[str]
    is_demo: bool
    health_score: int
    health_components: dict[str, float]
    avg_sanction_days: int | None
    rank_score: float


class ExcludedPartner(PartnerCard):
    reason: str


class NearbyResponse(BaseModel):
    engine: str
    center: dict[str, float]
    radius_km: float
    partners: list[PartnerCard]
    excluded: list[ExcludedPartner]
    cache: str
    took_ms: float


@router.get("/v1/partners/nearby", response_model=NearbyResponse)
async def nearby(
    session: Session,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
    scheme: Annotated[str | None, Query(max_length=48)] = None,
    category: Annotated[str | None, Query(max_length=24)] = None,
    radius_km: Annotated[float, Query(gt=0, le=300)] = 40,
    loan_paise: Annotated[int | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> Any:
    return await service.nearby(session, lat=lat, lng=lng, scheme=scheme, category=category, radius_km=radius_km,
                                loan_paise=loan_paise, limit=limit)


class DistrictOut(BaseModel):
    code: str
    name: str
    state_code: str
    lat: float
    lng: float
    pincode: str


@router.get("/v1/geo/pincode/{pincode}", response_model=DistrictOut)
async def locate_pincode(pincode: Annotated[str, Path(pattern=r"^\d{6}$")]) -> Any:
    district = district_for_pincode(pincode)
    if district is None:
        raise not_found("pincode")
    return district.__dict__


@router.get("/v1/geo/districts", response_model=list[DistrictOut])
async def districts(state: str | None = None) -> Any:
    return [d.__dict__ for d in DISTRICTS if state is None or d.state_code == state.upper()]
