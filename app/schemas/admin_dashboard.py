"""Pydantic schemas for platform admin dashboard (KPIs, trends, property performance, legacy summary)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class AdminDashboardKpisResponse(BaseModel):
    """Scalar KPI row for a reporting month (full calendar month, UTC) with MoM vs previous month."""

    month: str
    usersThisMonth: int
    usersMoMDelta: float
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
    """Top properties by views (descending by value)."""

    items: List[PropertyPerformanceItem]


class AdminDashboardSummaryResponse(BaseModel):
    """Legacy: platform-wide KPIs, 12-month series, lead mix, and top properties (current month UTC)."""

    month: str
    usersThisMonth: int
    usersMoMDelta: float
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
