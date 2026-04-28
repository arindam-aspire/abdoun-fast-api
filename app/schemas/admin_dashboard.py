"""Pydantic schemas for platform admin dashboard (KPIs, trends, property performance, legacy summary)."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.user import PaginationInfo


class PropertyPerformancePeriod(str, Enum):
    """Time window for aggregating property_views; exposed as query param ``limit`` on the API."""

    ALL = "all"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"

    @classmethod
    def _missing_(cls, value: object):
        """Accept ``WEEKLY`` / `` Monthly `` etc. from query strings (case- and whitespace-insensitive)."""
        if isinstance(value, str):
            key = value.strip().lower()
            for member in cls:
                if member.value == key:
                    return member
        return None


class AdminDashboardKpisResponse(BaseModel):
    """Scalar KPI row for a reporting month (full calendar month, UTC) with MoM vs previous month."""

    month: str
    registerUsersThisMonth: int
    registerUsersMoMDelta: float
    agentsThisMonth: int
    agentsMoMDelta: float
    pendingApprovals: int
    pendingApprovalsToday: int
    listingsThisMonth: int
    listingsMoMDelta: float
    leadsThisMonth: int
    leadsMoMDelta: float
    closedDealsThisMonth: int


class AdminDashboardTrendsResponse(BaseModel):
    """Aligned monthly series; months are full calendar buckets, oldest index first."""

    months: int
    monthLabels: List[str]
    userGrowthSeries: List[int]
    listingGrowthSeries: List[int]
    leadGrowthSeries: List[int]


class PropertyPerformanceItem(BaseModel):
    """Row for the property performance chart (view counts, trailing window on server)."""

    label: str
    value: int = Field(ge=0)
    propertyId: str
    propertyTitle: str = ""
    propertyType: str = ""
    agentId: Optional[str] = None
    agentName: str


class AdminDashboardPropertyPerformanceResponse(BaseModel):
    """Top properties by views (descending by value), paginated."""

    items: List[PropertyPerformanceItem]
    pagination: PaginationInfo


class AdminDashboardRecentActivityItem(BaseModel):
    """Recent activity item displayed in dashboard timeline."""

    text: str
    time: str
    tone: str


class AdminDashboardSummaryResponse(BaseModel):
    """Legacy: platform-wide KPIs, 12-month series, lead mix, and top properties (current month UTC)."""

    month: str
    totalRegisterUserCount: int = Field(default=0, ge=0)
    totalAgentCount: int = Field(default=0, ge=0)
    totalAdminCount: int = Field(default=0, ge=0)
    registerUsersThisMonth: int
    registerUsersMoMDelta: float
    agentsThisMonth: int
    agentsMoMDelta: float
    pendingApprovals: int
    pendingApprovalsToday: int
    listingsThisMonth: int
    listingsMoMDelta: float
    leadsThisMonth: int
    leadsMoMDelta: float
    closedDealsThisMonth: int
    monthLabels: List[str]
    userGrowthSeries: List[int]
    listingGrowthSeries: List[int]
    leadGrowthSeries: List[int]
    leadSourceLabels: List[str]
    leadSourceValues: List[int]
    propertyPerformanceSeries: List[PropertyPerformanceItem]
    recentActivity: List[AdminDashboardRecentActivityItem] = Field(default_factory=list)
