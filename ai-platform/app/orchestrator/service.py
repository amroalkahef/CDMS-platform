"""Orchestrator entrypoints consumed by the API layer."""

from sqlalchemy.orm import Session

from app.agents import communication_agent, execution_agent
from app.agents.authoring_agent import CIRCULAR_REQUIRED_SECTIONS, DECISION_REQUIRED_SECTIONS
from app.orchestrator.graph import build_draft_graph
from app.orchestrator.state import AgentState

# create_and_submit() already registers the workflow and notifies approvers
# internally (see execution_agent.create_entity) — nothing else to do here.

_DEFAULT_REQUIRED_SECTIONS: dict[str, list[str]] = {
    "generate_circular": CIRCULAR_REQUIRED_SECTIONS,
    "generate_decision": DECISION_REQUIRED_SECTIONS,
}


def run_draft(
    db: Session,
    task_type: str,
    user_prompt: str,
    doc_type_filter: str | None = None,
    required_sections: list[str] | None = None,
    language: str | None = None,
) -> AgentState:
    graph = build_draft_graph(db)
    initial_state: AgentState = {
        "task_type": task_type,
        "user_prompt": user_prompt,
        "doc_type_filter": doc_type_filter,
        "required_sections": required_sections or _DEFAULT_REQUIRED_SECTIONS.get(task_type, []),
        "language": language,
        "trace": [],
    }
    return graph.invoke(initial_state)


def run_execute(
    db: Session,
    entity_type: str,
    title: str,
    content: str,
    references: list[dict],
    created_by: str = "dev-user",
) -> dict:
    return execution_agent.create_and_submit(db, entity_type, title, content, references, created_by)


def run_publish(db: Session, entity_type: str, entity_id: str, requested_by: str, title: str) -> dict:
    result = execution_agent.publish(db, entity_type, entity_id)
    communication_agent.notify_published(db, requested_by=requested_by, title=title, entity_type=entity_type)
    return result


def list_versions(db: Session, entity_type: str, entity_id: str):
    return execution_agent.list_versions(db, entity_type, entity_id)
