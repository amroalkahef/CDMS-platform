"""Chat Agent.

Purpose: an interactive, multi-turn Q&A assistant grounded in the system's
actual data (Circulars, Decisions, the general Knowledge Layer). Unlike
authoring_agent, this IS meant to converse — it resolves questions via
tool-calling (exact record lookup + semantic search) rather than the single
retrieval pass the draft pipeline uses, and streams its final answer.

This agent never writes to the database — find_records/get_record/
search_knowledge are all read-only, matching execution_agent being the only
writer in the platform.
"""

import json
import time
from typing import Generator

import openai
from sqlalchemy.orm import Session

from app.agents import execution_agent
from app.config import get_settings
from app.orchestrator.context_builder import build_context
from app.tools.audit import log_audit
from app.tools.llm import get_client
from app.tools.rerank import rerank
from app.tools.search import search_documents, search_entity_chunks

MAX_TOOL_ROUNDS = 4

CHAT_SYSTEM_PROMPT = """You are the CDMS Assistant, an interactive help agent for a \
Circular & Decision Management System. You answer questions about the \
organization's circulars, decisions, and knowledge base by calling tools to \
look up real records — you never guess or invent content.

Rules:
- Always use find_records / get_record / search_knowledge to ground your \
  answer before responding. Never state a circular/decision number, date, \
  department, or policy detail that didn't come from a tool result.
- When you reference a record, name its title (and decision number, if it \
  has one) so the user can identify it.
- If no tool call returns a relevant result, say plainly that you couldn't \
  find that record or information — do not fabricate a plausible-sounding \
  answer.
- Write in clear, conversational prose (not the formal circular/decision \
  document format) — you are explaining and discussing, not drafting.
- You may ask a brief clarifying question if the user's request is \
  ambiguous (e.g. multiple records could match).
"""

_LANGUAGE_DIRECTIVES = {
    "en": "\n\nRespond in English, regardless of the language of the retrieved records.",
    "ar": "\n\nRespond in Modern Standard Arabic (Arabic script), regardless of the language of "
    "the retrieved records.",
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "find_records",
            "description": (
                "Search for circulars or decisions by keyword, title, decision number, "
                "or topic/meaning. Returns lightweight summaries — use get_record to fetch "
                "full content once you've identified the right entity_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "enum": ["circular", "decision", "any"],
                        "description": "Restrict the search to one entity type, or 'any' for both.",
                    },
                    "query": {"type": "string", "description": "Search text: a title, number, or topic."},
                },
                "required": ["entity_type", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_record",
            "description": "Fetch the full content of one circular or decision by its exact id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_type": {"type": "string", "enum": ["circular", "decision"]},
                    "entity_id": {"type": "string", "description": "The record's id, from find_records."},
                },
                "required": ["entity_type", "entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "Search the general knowledge base (uploaded/ingested documents) for policy or "
                "background information not tied to one specific circular or decision."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "doc_type": {"type": "string", "description": "Optional document type filter."},
                },
                "required": ["query"],
            },
        },
    },
]


def _find_records(db: Session, entity_type: str, query: str) -> list[dict]:
    types = ["circular", "decision"] if entity_type not in ("circular", "decision") else [entity_type]

    keyword_hits: list[dict] = []
    for etype in types:
        keyword_hits.extend(execution_agent.search_entities(db, etype, query, limit=5))

    semantic_entity_type = entity_type if entity_type in ("circular", "decision") else None
    semantic_hits = search_entity_chunks(db, query, entity_type=semantic_entity_type, top_k=5)

    seen: set[str] = set()
    results: list[dict] = []
    for hit in keyword_hits:
        key = f"{hit['entity_type']}:{hit['id']}"
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "entity_type": hit["entity_type"],
                "id": hit["id"],
                "title": hit["title"],
                "decision_number": hit.get("decision_number"),
                "department": hit["department"],
                "status": hit["status"],
                "match": "keyword",
            }
        )
    for hit in semantic_hits:
        key = f"{hit.entity_type}:{hit.entity_id}"
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "entity_type": hit.entity_type,
                "id": hit.entity_id,
                "title": hit.title,
                "department": hit.department,
                "status": hit.status,
                "similarity": hit.similarity,
                "match": "semantic",
            }
        )
    return results[:8]


def _search_knowledge(db: Session, query: str, doc_type: str | None) -> list[dict]:
    candidates = search_documents(db, query=query, top_k=15, doc_type=doc_type)
    hits = build_context(rerank(query, candidates, top_k=5))
    return [
        {"title": h.title, "doc_type": h.doc_type, "content": h.chunk_content, "similarity": h.similarity}
        for h in hits
    ]


def _execute_tool(db: Session, name: str, arguments: dict) -> dict:
    try:
        if name == "find_records":
            return {"results": _find_records(db, arguments.get("entity_type", "any"), arguments["query"])}
        if name == "get_record":
            return execution_agent.get_entity(db, arguments["entity_type"], arguments["entity_id"])
        if name == "search_knowledge":
            return {"results": _search_knowledge(db, arguments["query"], arguments.get("doc_type"))}
        return {"error": f"Unknown tool '{name}'"}
    except Exception as exc:  # noqa: BLE001 - tool errors must never crash the chat turn
        db.rollback()
        return {"error": str(exc)}


def run_chat(db: Session, messages: list[dict], language: str | None = None) -> Generator[dict, None, None]:
    """Public entrypoint — wraps the actual chat turn so any failure (rate
    limit, provider error, ...) becomes an in-stream {"type":"error"} event
    instead of an exception, since HTTP errors can't be raised once
    StreamingResponse has already sent headers/bytes to the client."""
    try:
        yield from _run_chat_turn(db, messages, language)
    except openai.RateLimitError:
        yield {"type": "error", "error_code": "ai_quota_exceeded"}
        yield {"type": "done"}
    except openai.APIStatusError:
        yield {"type": "error", "error_code": "ai_provider_error"}
        yield {"type": "done"}
    except Exception:  # noqa: BLE001 - must never let the generator raise past this point
        yield {"type": "error", "error_code": "request_failed"}
        yield {"type": "done"}


def _run_chat_turn(db: Session, messages: list[dict], language: str | None = None) -> Generator[dict, None, None]:
    start = time.perf_counter()
    settings = get_settings()
    client = get_client()

    system_prompt = CHAT_SYSTEM_PROMPT + _LANGUAGE_DIRECTIVES.get(language or "", "")
    convo: list[dict] = [{"role": "system", "content": system_prompt}] + messages
    tool_call_log: list[dict] = []
    total_tokens = 0

    for round_index in range(MAX_TOOL_ROUNDS):
        use_tools = round_index < MAX_TOOL_ROUNDS - 1
        completion = client.chat.completions.create(
            model=settings.chat_model,
            messages=convo,
            tools=TOOLS if use_tools else None,
            tool_choice="auto" if use_tools else None,
            temperature=0.2,
        )
        total_tokens += completion.usage.total_tokens if completion.usage else 0
        message = completion.choices[0].message

        if not message.tool_calls:
            convo.append({"role": "assistant", "content": message.content or ""})
            break

        convo.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in message.tool_calls
                ],
            }
        )
        for tool_call in message.tool_calls:
            yield {"type": "tool_call", "tool": tool_call.function.name}
            try:
                arguments = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            result = _execute_tool(db, tool_call.function.name, arguments)
            tool_call_log.append({"tool": tool_call.function.name, "arguments": arguments})
            convo.append({"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(result)[:4000]})
    else:
        convo.append({"role": "user", "content": "Answer now in prose, without calling any more tools."})

    stream = client.chat.completions.create(
        model=settings.chat_model,
        messages=convo,
        temperature=0.2,
        stream=True,
    )
    full_answer = ""
    for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            full_answer += delta
            yield {"type": "token", "content": delta}

    yield {"type": "done"}

    duration_ms = int((time.perf_counter() - start) * 1000)
    log_audit(
        db,
        agent="chat_agent",
        action="chat_turn",
        prompt=messages[-1]["content"] if messages else "",
        tokens=total_tokens,
        duration_ms=duration_ms,
        tool_calls=tool_call_log,
        final_response=full_answer[:2000],
    )
