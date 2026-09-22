from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator

from app.errors import ProblemError
from app.modules.finance.calc import LoanInput, affordability, build_schedule, funding_split

router = APIRouter(prefix="/v1/finance", tags=["finance"])


class SplitIn(BaseModel):
    apex_bps: int = Field(ge=0, le=10_000)
    partner_bps: int = Field(ge=0, le=10_000)
    beneficiary_bps: int = Field(ge=0, le=10_000)

    @model_validator(mode="after")
    def _sums(self) -> "SplitIn":
        if self.apex_bps + self.partner_bps + self.beneficiary_bps != 10_000:
            raise ValueError("shares must add up to 10000 bps")
        return self


class EmiRequest(BaseModel):
    principal_paise: int = Field(gt=0, le=100_000_000_000, examples=[6_000_000])
    rate_bps: int = Field(ge=0, le=3000, examples=[650])
    tenure_months: int = Field(ge=1, le=360, examples=[36])
    moratorium_months: int = Field(default=0, ge=0, le=60)
    treatment: Literal["interest_capitalised", "interest_paid_monthly", "interest_waived"] = "interest_capitalised"
    frequency: Literal["monthly", "quarterly"] = "monthly"
    subsidy_paise: int = Field(default=0, ge=0)
    project_cost_paise: int | None = Field(default=None, gt=0)
    split: SplitIn | None = None
    monthly_income_paise: int | None = Field(default=None, ge=0)
    max_emi_ratio_bps: int = Field(default=4000, ge=500, le=10_000)
    max_tenure_months: int | None = Field(default=None, ge=1, le=360)
    include_schedule: bool = True


class RowOut(BaseModel):
    period: int
    month: int
    kind: str
    opening_paise: int
    payment_paise: int
    interest_paise: int
    principal_paise: int
    closing_paise: int


class SplitOut(BaseModel):
    project_cost_paise: int
    apex_paise: int
    partner_paise: int
    beneficiary_paise: int
    apex_bps: int
    partner_bps: int
    beneficiary_bps: int


class AffordabilityOut(BaseModel):
    affordable: bool
    ratio_bps: int
    max_ratio_bps: int
    monthly_income_paise: int
    suggest_tenure_months: int | None
    suggest_tenure_emi_paise: int | None
    suggest_principal_paise: int | None
    suggest_principal_emi_paise: int | None


class EmiResponse(BaseModel):
    emi_paise: int
    instalments: int
    period_months: int
    principal_paise: int
    principal_after_moratorium_paise: int
    moratorium_interest_paise: int
    total_interest_paise: int
    total_payable_paise: int
    schedule: list[RowOut]
    split_breakdown: SplitOut | None
    affordability: AffordabilityOut | None


def compute(req: EmiRequest) -> dict[str, Any]:
    loan = LoanInput(req.principal_paise, req.rate_bps, req.tenure_months, req.moratorium_months, req.treatment,
                     req.frequency, req.subsidy_paise)
    try:
        schedule = build_schedule(loan)
    except ValueError as err:
        raise ProblemError(422, "Invalid loan inputs", "errors.validation", str(err)) from err
    split = None
    if req.split is not None:
        split = asdict(funding_split(req.project_cost_paise or req.principal_paise, req.split.apex_bps,
                                     req.split.partner_bps, req.split.beneficiary_bps))
    afford = None
    if req.monthly_income_paise is not None:
        afford = asdict(affordability(loan, schedule, req.monthly_income_paise, req.max_emi_ratio_bps,
                                      req.max_tenure_months))
    return {
        "emi_paise": schedule.instalment_paise, "instalments": schedule.instalments,
        "period_months": schedule.period_months, "principal_paise": schedule.principal_paise,
        "principal_after_moratorium_paise": schedule.principal_after_moratorium_paise,
        "moratorium_interest_paise": schedule.moratorium_interest_paise,
        "total_interest_paise": schedule.total_interest_paise, "total_payable_paise": schedule.total_payable_paise,
        "schedule": [asdict(r) for r in schedule.rows] if req.include_schedule else [],
        "split_breakdown": split, "affordability": afford,
    }


@router.post("/emi", response_model=EmiResponse)
async def emi(body: EmiRequest) -> Any:
    return compute(body)


class CompareRequest(BaseModel):
    options: list[EmiRequest] = Field(min_length=1, max_length=3)


class CompareResponse(BaseModel):
    options: list[EmiResponse]


@router.post("/compare", response_model=CompareResponse)
async def compare(body: CompareRequest) -> Any:
    return {"options": [compute(o.model_copy(update={"include_schedule": False})) for o in body.options]}
