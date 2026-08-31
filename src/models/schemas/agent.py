"""Agent schema -- describes an agent role, not an executing instance."""
from pydantic import BaseModel, Field


class Agent(BaseModel):
    agent_id: str
    name: str
    role: str
    system_prompt: str
    allowed_tools: list[str] = Field(default_factory=list)
