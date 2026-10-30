"""Explicit, bounded contracts for the opt-in local test runner."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Name = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
PathText = Annotated[str, Field(min_length=1, max_length=1000)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CheckProfile(Strict):
    kind: Literal["python_unittest"]
    start_dir: PathText
    pattern: Annotated[str, Field(pattern=r"^[A-Za-z0-9_*?-]{1,64}\.py$")] = "test_*.py"
    timeout_seconds: Annotated[int, Field(ge=1, le=60)] = 20


class CheckConfiguration(Strict):
    profiles: Annotated[dict[Name, CheckProfile], Field(min_length=1, max_length=20)]


class CheckRun(Strict):
    profile: Name
    sources: Annotated[list[PathText], Field(max_length=20)] = []


class CheckResult(Strict):
    run_id: Name


class CheckProfiles(Strict):
    pass


QUERY_SCHEMAS = {"check_result": CheckResult, "check_profiles": CheckProfiles}
MANAGE_SCHEMAS = {"check_run": CheckRun}
