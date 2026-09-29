
from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Literal
from datetime import datetime, timezone
import json
from agents import function_tool, RunContextWrapper

class WorkflowState(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    run_id: str
    problem: str

    status: Literal[
        "pending", "running", "completed", "failed"
    ] = "pending"

    current_agent: str | None = None

    analysis: dict | None = None
    critique: dict | None = None
    approved_model: dict | None = None
    pseudocode: str | None = None

    use_python: bool | None = None
    generated_code: str | None = None
    execution_result: dict | None = None
    verification: dict | None = None
    final_answer: str | None = None

    attempts: dict[str, int] = Field(default_factory=dict)
    errors: list[dict] = Field(default_factory=list)
    action_history: list[dict] = Field(default_factory=list)

    def record(
        self,
        action: str,
        agent: str | None = None,
        details: Any = None,
    ):
        self.action_history.append({
            "action": action,
            "agent": agent,
            "details": details,
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
        })

@function_tool
async def read_state(
    ctx: RunContextWrapper[WorkflowState],
) -> str:
    """Read the complete shared workflow state."""

    state = ctx.context

    state.record(
        action="read_state",
        agent="Orchestrator",
    )

    return state.model_dump_json(indent=2)


@function_tool
async def update_state(
    ctx: RunContextWrapper[WorkflowState],
    field: str,
    value: str,
) -> str:
    """
    Update a permitted field in the shared workflow state.
    The value must be valid JSON.
    """

    state = ctx.context

    allowed = {
        "analysis",
        "critique",
        "approved_model",
        "pseudocode",
        "use_python",
        "generated_code",
        "execution_result",
        "verification",
        "final_answer",
    }

    if field not in allowed:
        return f"Rejected: {field} is not writable."

    try:
        parsed = json.loads(value)
        setattr(state, field, parsed)
    except (ValueError, TypeError) as exc:
        return f"Rejected invalid value: {exc}"

    state.record(
        action="update_state",
        agent="Orchestrator",
        details={"field": field},
    )

    return f"Successfully updated {field}."