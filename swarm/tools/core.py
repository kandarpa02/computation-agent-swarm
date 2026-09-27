from agents import Agent, Runner, function_tool
from openai import AsyncOpenAI
from pydantic import BaseModel

class Planner(BaseModel):
    tools_needed:bool


def planner_tool(tools_needed:bool):
    return str(tools_needed)