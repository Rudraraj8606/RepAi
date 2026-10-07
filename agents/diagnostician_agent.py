"""
diagnostician_agent.py

Shows how Agent 1 (The Diagnostician) uses the WorkoutTools class.
Agent 1 is given the tools and the user's free-text note, and it decides
for itself which calculations it needs before writing a diagnosis.
Its text output then becomes the input to Agent 2 (The Prescriptive
Coach), which is a separate, unrelated class/prompt.
"""

from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent

from app_logic.workout_repository import WorkoutRepository
from agents.workout_tools import WorkoutTools
from dotenv import load_dotenv
_
load_dotenv()

DIAGNOSTICIAN_SYSTEM_PROMPT = """
You are RepIQ's Diagnostician. Use the available tools to pull whatever
training metrics you need for the exercise in question, then combine
those metrics with the user's free-text note to produce a short
diagnosis of the lifter's current state (e.g. systemic fatigue, form
breakdown, localized injury risk, or normal linear progression). Do not
prescribe a workout -- that is a separate agent's job. Just diagnose.
"""


def build_diagnostician_agent(repository: WorkoutRepository):
    tools = WorkoutTools(repository).get_tools()
    llm = ChatAnthropic(model="claude-sonnet-5")
    return create_react_agent(llm, tools, prompt=DIAGNOSTICIAN_SYSTEM_PROMPT)


def diagnose(repository: WorkoutRepository, exercise: str, user_note: str) -> str:
    agent = build_diagnostician_agent(repository)
    user_message = f"Exercise: {exercise}\nUser note: \"{user_note}\""
    result = agent.invoke({"messages": [("user", user_message)]})
    return result["messages"][-1].content


if __name__ == "__main__":
    repo = WorkoutRepository()
    diagnosis = diagnose(repo, "Bench Press", "shoulder felt off today")
    print(diagnosis)