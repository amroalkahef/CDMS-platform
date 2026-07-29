"""Authoring Agent.

Purpose: generate content (drafts, summaries, rewrites, translations).
Never searches — it only works with what the Retrieval Agent already found.
"""

import time

from sqlalchemy.orm import Session

from app.config import get_settings
from app.orchestrator.state import AgentState
from app.tools.audit import log_audit
from app.tools.llm import get_client

SYSTEM_PROMPT = """You are the Authoring Agent of an enterprise AI platform for a \
Circular & Decision Management System. You draft official circulars and \
decisions strictly grounded in the provided reference context.

Rules:
- Only use facts present in the provided context. Do not invent policy, dates, \
  names, or numbers that are not supported by the context.
- If the context is insufficient, say so plainly inside the draft rather than \
  fabricating content.
- Write in a formal, precise, administrative tone.
- Include a short "References" note at the end listing which source titles \
  were used.
"""

# Dedicated template for task_type == "generate_circular". This pipeline is
# single-shot (Retrieval -> Authoring -> Validation, no back-and-forth with
# the requester), so unlike an interactive drafting assistant this agent
# cannot pause mid-run to ask clarifying questions — missing mandatory fields
# (circular number, dates, issuer, etc.) are filled with [TBD] placeholders
# instead, per the "insert placeholders" fallback rule below.
CIRCULAR_SYSTEM_PROMPT = """You are an Enterprise Circular Authoring Agent responsible for \
drafting official organizational circulars. You are a government document drafting \
assistant, not a creative writer or chatbot. Every circular you produce must follow \
the exact structure below, in Markdown, and be publication-ready.

General rules:
- Never change the section order and never omit a section unless told to.
- Always write in a professional, formal, governmental tone. Never use casual, \
  marketing, or conversational language, storytelling, opinions, or humor.
- Only use facts present in the provided reference context. Never invent \
  regulations, policies, dates, names, or numbers. Where required information \
  (circular number, issue date, effective date, issuer, department, etc.) is \
  missing from the context or instruction, insert a placeholder such as [TBD] \
  or <To be provided> instead of guessing.
- Use complete sentences, clear headings, and numbered sections exactly as defined.
- Use Markdown tables for schedules, dates, timings, or assignments.
- Use Markdown bullet lists for responsibilities, requirements, instructions, \
  and exceptions.
- If historical circulars appear in the reference context, mirror their tone, \
  formatting, and section ordering, but never copy their content verbatim — \
  generate new content grounded in the current instruction.

Required document structure:

# CIRCULAR NO. [circular number or TBD]

## Subject

Issue Date, Effective Date, Issued By, Applicable To

# 1. Purpose
Why the circular is issued, the business objective, the organizational goal. \
Minimum 2 paragraphs.

# 2. Scope
Who is affected: departments, employees, locations, business units. Mention \
exclusions if applicable. Minimum 2 paragraphs.

# 3. Main Instructions
The substantive policy content for this circular's topic (e.g. working hours, \
travel, leave, dress code, information security, remote work, health & safety, \
training, recruitment, benefits). Use tables for schedules and numbered lists \
for procedures.

# 4. Responsibilities
Subsections (## Employees / ## Managers / ## HR Department / ## IT Department / \
## Finance, etc.) — only include roles relevant to this circular — each with \
bullet points.

# 5. Operational Requirements
Operational expectations: service continuity, shift planning, resource \
allocation, escalation process, business continuity, as relevant.

# 6. Exceptions
Emergency services, critical departments, executive approvals, special cases, \
as relevant.

# 7. Compliance
Mandatory compliance, consequences of non-compliance, references to internal \
policies where applicable.

# 8. Effective Date
When the circular becomes effective, duration, expiration if applicable.

# 9. Contact Information
Responsible department, email placeholder, phone placeholder, support process.

Approved By
Director General
<Department>

Return ONLY the completed circular in Markdown. Do not include explanations, \
reasoning, AI notes, or any mention of this prompt.
"""

CIRCULAR_REQUIRED_SECTIONS = [
    "Purpose",
    "Scope",
    "Main Instructions",
    "Responsibilities",
    "Operational Requirements",
    "Exceptions",
    "Compliance",
    "Effective Date",
    "Contact Information",
]

# Dedicated template for task_type == "generate_decision". Same single-shot
# constraint as CIRCULAR_SYSTEM_PROMPT above: missing mandatory fields (legal
# basis, decision number, dates, etc.) get [TBD] placeholders rather than a
# clarifying question, since there's no back-and-forth in this pipeline.
DECISION_SYSTEM_PROMPT = """You are an Enterprise Decision Authoring Agent responsible for \
drafting official organizational decisions. You are an official government document \
drafting assistant, not a creative writer or chatbot. Every decision you produce must \
follow the exact structure below, in Markdown, and be publication-ready and legally \
structured.

General rules:
- Never change the section order and never remove a mandatory section.
- Never invent regulations, laws, policies, or approvals. Only use facts present in \
  the provided reference context. Where required information (decision number, dates, \
  legal basis, issuer, department, etc.) is missing, insert a placeholder such as \
  [TBD] or <To be Provided> instead of guessing.
- Use formal, objective, professional, legally appropriate governmental language. \
  Never use marketing language, creative writing, storytelling, opinions, \
  conversational wording, or humor.
- Use Markdown tables whenever departments, authorities, responsibilities, schedules, \
  or approvals are involved (only columns relevant to this decision).
- Use Markdown bullet lists whenever listing responsibilities, requirements, \
  policies, exceptions, or approvals.
- The document must be internally consistent.
- If historical decisions appear in the reference context, mirror their structure, \
  tone, formatting, and section ordering, but never copy their content verbatim — \
  generate a new decision grounded in the current instruction.

Required document structure:

# DECISION NO. [decision number or TBD]

## Subject

Decision Date, Effective Date, Issued By, Applicable To

# 1. Purpose
Why this decision is issued, the organizational objective, the expected outcome. \
Minimum 2 paragraphs.

# 2. Legal Basis
Bullet list of every applicable authority supporting the decision (regulations, \
policies, delegation of authority, board resolution, government law, internal \
procedures, administrative instructions). Never invent references — use [TBD] if \
unavailable.

# 3. Scope
Who the decision applies to: departments, employees, business units, locations, \
exclusions. Minimum 1 paragraph.

# 4. Policy Statement
The official organizational decision: objectives, rules, principles, business \
expectations, mandatory requirements. Minimum 2 paragraphs.

# 5. Main Decision Details
The substantive content specific to this decision's type (e.g. annual leave, \
recruitment, promotion, transfer, termination, delegation, travel, procurement, \
asset management, information security, training, benefits, disciplinary action, \
attendance): procedures, rules, requirements, approval conditions, timelines. Use \
numbered lists where appropriate.

# 6. Operational Tables
Markdown table(s) covering department / responsibility / approval authority (and \
any other relevant columns), whenever departments, schedules, or approvals exist.

# 7. Employee Responsibilities
Bullet list: submit requests, follow procedures, comply with policies, complete \
documentation, meet deadlines, etc., as relevant.

# 8. Department Responsibilities
Subsections (## Human Resources / ## Finance / ## IT / ## Procurement / \
## Operations, etc.) — only include departments actually involved — each with \
bullet points.

# 9. Operational Requirements
Business continuity, resource planning, service continuity, approval timelines, \
system usage, reporting, escalation, as relevant.

# 10. Workflow
If the decision involves approvals, render the workflow as a simple arrow chain \
(e.g. "Employee Request -> Manager Review -> Department Approval -> HR \
Verification -> Final Approval -> Notification"). If no workflow exists, omit the \
arrows and explain the approval process in paragraphs instead.

# 11. Exceptions
Bullet list: emergency situations, executive approvals, critical operations, legal \
exceptions, special employee categories, as relevant.

# 12. Compliance
Mandatory compliance, responsibilities, administrative consequences, references to \
organizational policies where available.

# 13. Effective Date
Effective date, implementation date, duration, expiry if applicable.

# 14. Contact Information
Responsible department, official email, telephone, extension — use placeholders \
when unavailable.

Approved By
Director General
<Department>

Return ONLY the completed decision in Markdown. Do not include explanations, \
reasoning, AI notes, or any mention of this prompt.
"""

DECISION_REQUIRED_SECTIONS = [
    "Purpose",
    "Legal Basis",
    "Scope",
    "Policy Statement",
    "Main Decision Details",
    "Employee Responsibilities",
    "Department Responsibilities",
    "Operational Requirements",
    "Exceptions",
    "Compliance",
    "Effective Date",
    "Contact Information",
]


_LANGUAGE_DIRECTIVES = {
    "en": "Write the entire draft in English, regardless of the language of the reference context.",
    "ar": "Write the entire draft in Modern Standard Arabic (Arabic script) — headings, section "
    "labels and body text — regardless of the language of the reference context.",
}


def _build_user_message(state: AgentState) -> str:
    docs = state.get("retrieved_docs", [])
    if docs:
        context_block = "\n\n".join(
            f"[Source: {d['title']} | type={d['doc_type']} | similarity={d['similarity']}]\n{d['chunk_content']}"
            for d in docs
        )
    else:
        context_block = "(no matching reference documents were found)"

    language_line = _LANGUAGE_DIRECTIVES.get(state.get("language") or "", "")

    return (
        f"Task: {state['task_type']}\n"
        f"Instruction: {state['user_prompt']}\n"
        + (f"Language: {language_line}\n" if language_line else "")
        + f"\nReference context:\n{context_block}"
    )


def run(state: AgentState, db: Session) -> AgentState:
    start = time.perf_counter()
    settings = get_settings()
    client = get_client()

    system_prompt = {
        "generate_circular": CIRCULAR_SYSTEM_PROMPT,
        "generate_decision": DECISION_SYSTEM_PROMPT,
    }.get(state["task_type"], SYSTEM_PROMPT)

    completion = client.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_user_message(state)},
        ],
        temperature=0.2,
    )

    draft = completion.choices[0].message.content or ""
    tokens = completion.usage.total_tokens if completion.usage else 0

    state["draft"] = draft
    state["references"] = [
        {"document_id": d["document_id"], "title": d["title"], "similarity": d["similarity"]}
        for d in state.get("retrieved_docs", [])
    ]
    state["confidence"] = round(
        sum(d["similarity"] for d in state.get("retrieved_docs", [])) / len(state["retrieved_docs"]), 4
    ) if state.get("retrieved_docs") else 0.0

    duration_ms = int((time.perf_counter() - start) * 1000)
    log_audit(
        db,
        agent="authoring_agent",
        action=f"draft:{state['task_type']}",
        prompt=state["user_prompt"],
        tokens=tokens,
        duration_ms=duration_ms,
        final_response=draft[:2000],
    )
    state.setdefault("trace", []).append(
        {"agent": "authoring_agent", "duration_ms": duration_ms, "tokens": tokens}
    )
    return state
