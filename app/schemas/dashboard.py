from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DashboardActivity(BaseModel):
    id: str
    type: Literal["lead", "listing", "deal", "agent", "user", "approval"]
    text: str
    time: str
    tone: Literal["info", "success", "warning", "error"]


class DashboardSummaryData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    month: str
    total_register_user_count: int = Field(alias="totalRegisterUserCount")
    total_agent_count: int = Field(alias="totalAgentCount")
    total_admin_count: int = Field(alias="totalAdminCount")
    register_users_this_month: int = Field(alias="registerUsersThisMonth")
    register_users_mom_delta: float = Field(alias="registerUsersMoMDelta")
    agents_this_month: int = Field(alias="agentsThisMonth")
    agents_mom_delta: float = Field(alias="agentsMoMDelta")
    pending_approvals: int = Field(alias="pendingApprovals")
    pending_approvals_today: int = Field(alias="pendingApprovalsToday")
    listings_this_month: int = Field(alias="listingsThisMonth")
    listings_mom_delta: float = Field(alias="listingsMoMDelta")
    leads_this_month: int = Field(alias="leadsThisMonth")
    leads_mom_delta: float = Field(alias="leadsMoMDelta")
    closed_deals_this_month: int = Field(alias="closedDealsThisMonth")
    month_labels: list[str] = Field(alias="monthLabels")
    user_growth_series: list[int] = Field(alias="userGrowthSeries")
    listing_growth_series: list[int] = Field(alias="listingGrowthSeries")
    lead_growth_series: list[int] = Field(alias="leadGrowthSeries")
    lead_source_labels: list[str] = Field(alias="leadSourceLabels")
    lead_source_values: list[int] = Field(alias="leadSourceValues")
    recent_activity: list[DashboardActivity] = Field(alias="recentActivity")
    health_alerts: list[str] = Field(alias="healthAlerts")


class DashboardSummaryResponse(BaseModel):
    success: Literal[True] = True
    message: str = "Dashboard summary retrieved successfully"
    data: DashboardSummaryData
    meta: None = None
