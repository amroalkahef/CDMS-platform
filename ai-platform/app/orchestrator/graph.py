"""The AI Orchestrator's execution graph.

Per the PRD, the orchestrator does not itself search, generate, or modify
data — it wires the specialist agents together. This graph implements the
'draft' half of the AI Workflow: Retrieve Context -> Generate Draft ->
Validate Draft -> Return Result. The Execution/Communication half runs
separately, after a human approves the draft (see orchestrator/service.py).
"""

from functools import partial

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.agents import authoring_agent, retrieval_agent, validation_agent
from app.orchestrator.state import AgentState


def build_draft_graph(db: Session):
    builder = StateGraph(AgentState)

    builder.add_node("retrieval", partial(retrieval_agent.run, db=db))
    builder.add_node("authoring", partial(authoring_agent.run, db=db))
    builder.add_node("validation", partial(validation_agent.run, db=db))

    builder.set_entry_point("retrieval")
    builder.add_edge("retrieval", "authoring")
    builder.add_edge("authoring", "validation")
    builder.add_edge("validation", END)

    return builder.compile()
