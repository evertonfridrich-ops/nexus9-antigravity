"""Strict, bounded schemas for evidence-linked investigations."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Name = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
PathText = Annotated[str, Field(min_length=1, max_length=1000)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

Statement = Annotated[str, Field(min_length=1, max_length=2000)]
Short = Annotated[str, Field(min_length=1, max_length=800)]
References = Annotated[list[Name], Field(min_length=1, max_length=20)]


class Hypothesis(Strict):
    id: Name
    statement: Statement


class Note(Strict):
    id: Name
    text: Statement


class Evidence(Strict):
    id: Name
    summary: Statement
    hypothesis_ids: References
    result: Literal["supports", "refutes", "inconclusive"]
    files: Annotated[list[PathText], Field(max_length=20)] = []
    run_id: Name | None = None


class Conclusion(Strict):
    id: Name
    statement: Statement
    evidence_ids: References
    hypothesis_ids: References


class Criterion(Strict):
    id: Name
    requirement: Statement
    conclusion_ids: References
    requires_observed_test: bool = False


class Regression(Strict):
    id: Name
    note_id: Name
    hypothesis_id: Name
    description: Statement
    tags: Annotated[list[Name], Field(max_length=10)] = []
    check_profile: Name | None = None


class InvestigationBody(Strict):
    objective: Statement
    domain: Name = "generic"
    hypotheses: Annotated[list[Hypothesis], Field(max_length=20)] = []
    notes: Annotated[list[Note], Field(max_length=20)] = []
    evidence: Annotated[list[Evidence], Field(max_length=30)] = []
    conclusions: Annotated[list[Conclusion], Field(max_length=20)] = []
    criteria: Annotated[list[Criterion], Field(max_length=20)] = []
    regressions: Annotated[list[Regression], Field(max_length=20)] = []


class InvestigationSave(Strict):
    name: Name
    expected_revision: Annotated[int, Field(ge=0, le=1000000000)] = 0
    body: InvestigationBody


class InvestigationGet(Strict):
    name: Name
    conclusion_id: Annotated[str, Field(pattern=r"^$|^[A-Za-z0-9_-]{1,64}$")] = ""
    offset: Annotated[int, Field(ge=0, le=100)] = 0
    limit: Annotated[int, Field(ge=1, le=20)] = 5


class RegressionCases(Strict):
    tags: Annotated[list[Name], Field(max_length=10)] = []
    limit: Annotated[int, Field(ge=1, le=20)] = 20
    offset: Annotated[int, Field(ge=0, le=10000)] = 0


QUERY_SCHEMAS = {"investigation": InvestigationGet, "regression_cases": RegressionCases}
MANAGE_SCHEMAS = {"investigation_save": InvestigationSave}
