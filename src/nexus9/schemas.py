from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

Name = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
Text = Annotated[str, Field(max_length=16000)]
PathText = Annotated[str, Field(min_length=1, max_length=1000)]
Budget = Annotated[int, Field(ge=2048, le=24576)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Empty(Strict):
    pass


class Plan(Strict):
    task: Annotated[str, Field(min_length=1, max_length=2000)]
    profile: Literal["economy", "balanced", "rigorous"] = "balanced"


class Context(Plan):
    paths: Annotated[list[PathText], Field(max_length=12)] = []
    constraints: Annotated[list[Text], Field(max_length=20)] = []
    known_hashes: Annotated[dict[PathText, str], Field(max_length=30)] = {}
    budget_bytes: Budget = 12000
    memory: Name | None = None
    focus_symbols: Annotated[dict[PathText, str], Field(max_length=12)] = {}


class Index(Strict):
    max_files: Annotated[int, Field(ge=1, le=1000)] = 250


class Outline(Strict):
    path: PathText


class Snippet(Outline):
    symbol: Annotated[str, Field(max_length=200)] = ""
    start: Annotated[int, Field(ge=1, le=1000000)] = 1
    count: Annotated[int, Field(ge=1, le=500)] = 100


class Impact(Outline):
    depth: Annotated[int, Field(ge=1, le=3)] = 1


class Delta(Outline):
    base_revision: Annotated[int, Field(ge=1)] | None = None


class ToolDescriptor(Strict):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    tags: Annotated[list[str], Field(max_length=20)]
    schema_bytes: Annotated[int, Field(ge=0, le=1000000)] = 0


class Route(Plan):
    external_tools: Annotated[list[ToolDescriptor], Field(max_length=50)] = []


class Log(Outline):
    max_groups: Annotated[int, Field(ge=1, le=50)] = 15
    include_warnings: bool = True


class Block(Strict):
    id: Name
    text: Text
    priority: Annotated[int, Field(ge=0, le=100)] = 50
    pinned: bool = False


class Compress(Strict):
    blocks: Annotated[list[Block], Field(max_length=80)]
    budget_bytes: Budget = 12000


class Fact(Strict):
    text: Text
    source: Literal["user", "agent", "verified_file", "test_result"]


class MemoryBody(Strict):
    goal: Text
    constraints: Annotated[list[Fact], Field(max_length=20)] = []
    decisions: Annotated[list[Fact], Field(max_length=40)] = []
    pending: Annotated[list[Text], Field(max_length=40)] = []
    files: Annotated[list[PathText], Field(max_length=30)] = []
    validation: Annotated[list[Fact], Field(max_length=30)] = []


class MemorySave(Strict):
    name: Name = "default"
    expected_revision: Annotated[int, Field(ge=0, le=1000000000)] = 0
    body: MemoryBody


class MemoryGet(Strict):
    name: Name = "default"


class Handoff(Context):
    role: Annotated[str, Field(min_length=1, max_length=120)] = "Implementer"
    deliverable: Annotated[str, Field(min_length=1, max_length=500)] = "Report changes, validation and unresolved issues"


class Session(Strict):
    name: Name
    profile: Literal["economy", "balanced", "rigorous"] = "balanced"
    call_budget_bytes: Budget = 12000
    total_budget_bytes: Annotated[int, Field(ge=2048, le=10000000)] = 250000


class SessionClose(Strict):
    name: Name


class RememberRead(Outline):
    expected_revision: Annotated[int, Field(ge=0)] = 0


class CacheSave(Strict):
    key: Name
    answer: Text
    files: Annotated[list[PathText], Field(min_length=1, max_length=20)]
    ttl_seconds: Annotated[int, Field(ge=1, le=86400)] = 3600


class CacheGet(Strict):
    key: Name


class Usage(Strict):
    request_id: Name
    provider: Annotated[str, Field(min_length=1, max_length=80)]
    model: Annotated[str, Field(min_length=1, max_length=120)]
    input_tokens: Annotated[int, Field(ge=0, le=1000000000)]
    output_tokens: Annotated[int, Field(ge=0, le=1000000000)]
    cached_input_tokens: Annotated[int, Field(ge=0, le=1000000000)] = 0
    source: Literal["provider_response", "manual"]


class Trial(Strict):
    task_id: Name
    variant: Literal["baseline", "nexus"]
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    passed: bool
    evidence: Annotated[str, Field(min_length=1, max_length=500)]


class Evaluate(Strict):
    trials: Annotated[list[Trial], Field(min_length=2, max_length=100)]


QUERY_SCHEMAS = {"plan": Plan, "context": Context, "index": Index, "outline": Outline, "snippet": Snippet,
                 "impact": Impact, "route": Route, "logs": Log, "compress": Compress, "delta": Delta,
                 "verify": Outline, "memory": MemoryGet, "resume": MemoryGet, "cache": CacheGet,
                 "handoff": Handoff, "metrics": Empty, "health": Empty, "evaluate": Evaluate}
MANAGE_SCHEMAS = {"session_open": Session, "session_close": SessionClose, "memory_save": MemorySave,
                  "remember_read": RememberRead, "cache_save": CacheSave, "usage_record": Usage}
