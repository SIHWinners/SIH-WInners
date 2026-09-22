"""Demo personas (spec §14). All fictional. Social categories are assigned to exercise
specific schemes and are not inferred from names (see docs/DECISIONS.md ADR-015)."""

from dataclasses import dataclass, field
from typing import Any

from app.modules.routing.districts import BY_CODE

LAKH = 100_000_00  # ₹1 lakh in paise


@dataclass(frozen=True)
class Persona:
    key: str
    phone: str
    full_name: str
    lang: str
    district_code: str
    facts: dict[str, Any]
    expected_scheme: str
    story: str
    document_names: dict[str, str] = field(default_factory=dict)

    @property
    def location(self) -> tuple[float, float]:
        d = BY_CODE[self.district_code]
        return d.lat, d.lng


PERSONAS: dict[str, Persona] = {
    "savitaben": Persona(
        key="savitaben", phone="9000000001", full_name="Savitaben Rathwa", lang="gu", district_code="GJ-DAH",
        facts={"age": 34, "gender": "female", "social_category": "sc", "has_disability": False, "state_code": "GJ",
               "district_code": "GJ-DAH", "pincode": "389151", "annual_family_income_paise": 120_000_00,
               "education_level": "primary", "occupation": "farm_labour", "business_type": "dairy",
               "project_cost_paise": 60_000_00, "loan_needed_paise": 60_000_00, "existing_loans": False,
               "shg_member": True, "course_admitted": False},
        expected_scheme="NSFDC_MICRO_CREDIT",
        story="Two milch animals, SHG member, full voice flow in Gujarati with read-back.",
    ),
    "ramesh": Persona(
        key="ramesh", phone="9000000002", full_name="RAMESH KANARAM MEGHWAL", lang="hi", district_code="RJ-BAR",
        facts={"age": 41, "gender": "male", "social_category": "sc", "has_disability": False, "state_code": "RJ",
               "district_code": "RJ-BAR", "pincode": "344001", "annual_family_income_paise": 180_000_00,
               "education_level": "secondary", "occupation": "tailor", "business_type": "tailoring",
               "project_cost_paise": 450_000_00, "loan_needed_paise": 400_000_00, "existing_loans": False,
               "shg_member": False, "course_admitted": False},
        expected_scheme="NSFDC_TERM_LOAN",
        story="Tailoring unit; nearest bank skipped for weak recovery; faded caste certificate fetched from "
              "DigiLocker; 'Shri Ramesh S/O Late Kanaram' matched to the bank passbook name.",
        document_names={"caste_certificate": "Shri Ramesh S/O Late Kanaram", "bank_passbook": "RAMESH KANARAM MEGHWAL"},
    ),
    "kavya": Persona(
        key="kavya", phone="9000000003", full_name="Kavya Selvam", lang="ta", district_code="TN-MDU",
        facts={"age": 19, "gender": "female", "social_category": "obc", "has_disability": False, "state_code": "TN",
               "district_code": "TN-MDU", "pincode": "625001", "annual_family_income_paise": 150_000_00,
               "education_level": "higher_secondary", "occupation": "student", "business_type": "education",
               "project_cost_paise": 240_000_00, "loan_needed_paise": 200_000_00, "existing_loans": False,
               "shg_member": False, "course_admitted": True},
        expected_scheme="NBCFDC_EDUCATION_LOAN",
        story="Diploma admission; offline in the village; draft saved and sent by SMS; tracking ID returned.",
    ),
    "imran": Persona(
        key="imran", phone="9000000004", full_name="Imran Qureshi", lang="ur", district_code="UP-LKO",
        facts={"age": 32, "gender": "male", "social_category": "obc", "has_disability": True, "disability_pct": 60,
               "state_code": "UP", "district_code": "UP-LKO", "pincode": "226001",
               "annual_family_income_paise": 140_000_00, "education_level": "secondary", "occupation": "driver",
               "business_type": "e_rickshaw", "project_cost_paise": 180_000_00, "loan_needed_paise": 160_000_00,
               "existing_loans": False, "shg_member": False, "course_admitted": False},
        expected_scheme="NDFDC_DIVYANG_SELF_EMPLOYMENT",
        story="Divyang (UDID 60%), e-rickshaw; applies through the Lucknow CSC operator; Urdu RTL interface.",
    ),
    "edge": Persona(
        key="edge", phone="9000000005", full_name="Suresh Jatav", lang="hi", district_code="RJ-JAI",
        facts={"age": 36, "gender": "male", "social_category": "sc", "has_disability": False, "state_code": "RJ",
               "district_code": "RJ-JAI", "pincode": "302001", "annual_family_income_paise": 500_001_00,
               "education_level": "graduate", "occupation": "shopkeeper", "business_type": "retail_shop",
               "project_cost_paise": 350_000_00, "loan_needed_paise": 300_000_00, "existing_loans": False,
               "shg_member": False, "course_admitted": False},
        expected_scheme="MUDRA_KISHOR_BANK",
        story="Family income ₹5,00,001 — one rupee over the limit: near-miss explanation plus next-best option.",
    ),
}
