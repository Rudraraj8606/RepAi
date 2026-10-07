"""
coach_agent.py  --  Agent 2: The Prescriptive Coach  (OWNER: friend / B)

Takes Agent 1's diagnosis TEXT as input and returns a specific
next-session plan (exercise swaps, target weights/reps). Same pattern
as diagnostician_agent.py, but this agent does NOT need tools -- it only
reasons over the diagnosis string Agent 1 produced, so a plain LLM call
is enough; no ReAct loop needed.
"""

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()

COACH_SYSTEM_PROMPT = """
You are RepIQ's Prescriptive Coach. You will be given a diagnosis of a
lifter's current physical state, written by a separate diagnostic
agent. Turn that diagnosis into a specific, actionable plan for their
next training session: name exact exercises, target weights, sets, and
reps (or an explicit deload/substitution if the diagnosis calls for
one). Do not restate or re-explain the diagnosis -- just prescribe the
plan.
"""


def build_coach_agent() -> ChatAnthropic:
    return ChatAnthropic(model="claude-sonnet-5")


def coach(diagnosis: str) -> str:
    llm = build_coach_agent()
    messages = [
        ("system", COACH_SYSTEM_PROMPT),
        ("user", f"Diagnosis: {diagnosis}"),
    ]
    result = llm.invoke(messages)
    return result.content


if __name__ == "__main__":
    sample_diagnosis = (
        "Localized shoulder strain suspected rather than a general "
        "strength plateau, based on a volume drop paired with the "
        "user's note that their shoulder felt off."
    )
    plan = coach(sample_diagnosis)
    print(plan)