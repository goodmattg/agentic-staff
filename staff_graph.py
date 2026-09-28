"""Staff control flow. Native harness actions are suspended graph nodes.

The graph owns routing and gates; the host owns tools and agent execution.
Only an explicit start creates a run. Results resume that run by action ID.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic_graph import BaseNode, End, GraphBuilder, GraphRunContext

import agentic_staff as jev

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Harness = Literal["claude", "codex", "pi", "grok"]
REVIEWERS = ("Jeff", "Elon", "Bezos", "Mark", "Steve")


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Conversation(Result):
    harness: Harness
    reference: Text
    text: Text


class ContextResult(Result):
    summary: Text
    files: list[str]
    conversations: list[Conversation]
    unavailable_harnesses: list[Harness]


class PlanResult(Result):
    plan: Text


class ExecutionResult(Result):
    summary: Text
    pr_url: Annotated[str, StringConstraints(pattern=r"^https://[^\s]+/pull/\d+$")]
    worktree: Text
    tests: list[Text]
    draft: Literal[True]


class ReviewResult(Result):
    reviews: dict[str, list[Text]]

    @model_validator(mode="after")
    def complete_panel(self):
        if set(self.reviews) != set(REVIEWERS):
            raise ValueError(f"Return each reviewer exactly once: {', '.join(REVIEWERS)}")
        return self


class FinalizeResult(Result):
    pr_url: Text
    pr_state: Literal["draft", "ready"]
    worktree_removed: bool


RESULTS = {
    "context": ContextResult,
    "plan": PlanResult,
    "execute": ExecutionResult,
    "review": ReviewResult,
    "finalize": FinalizeResult,
}


class Action(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: str
    instructions: str
    payload: dict
    result_schema: dict


class RunState(BaseModel):
    version: Literal[1] = 1
    id: str = Field(default_factory=lambda: str(uuid4()))
    query: str
    harness: Harness
    workspace: str
    phase: str = "classify"
    status: Literal["running", "waiting", "blocked", "complete", "cancelled"] = "running"
    pending: Action | None = None
    incoming: dict | None = None
    blocked_reason: str | None = None
    query_kind: str | None = None
    ticket: dict = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)
    plan: str = ""
    execution: dict = Field(default_factory=dict)
    findings: list[dict] = Field(default_factory=list)
    loops: int = 0
    confidence: Literal["low", "high"] | None = None
    history: list[dict] = Field(default_factory=list)


def response(state: RunState) -> dict:
    value = {
        "run_id": state.id,
        "status": state.status,
        "query_kind": state.query_kind,
        "loops": state.loops,
        "confidence": state.confidence,
        "blocked_reason": state.blocked_reason,
        "action": state.pending.model_dump() if state.pending else None,
    }
    if state.status == "complete":
        if state.query_kind == "kq":
            value["reply_instruction"] = "Answer the knowledge question directly as the parent."
        elif state.confidence == "high":
            value["reply_instruction"] = "Reply 'good to ship' with at most three evidence bullets."
        else:
            value["reply_instruction"] = (
                "Report LOW CONFIDENCE and the evidence in a few sentences."
            )
        value["evidence"] = {"execution": state.execution, "findings": state.findings}
        value["followups"] = "Use the base model. Start another run only on explicit invocation."
    return value


def exchange(state: RunState, kind: str, instructions: str, payload: dict):
    """Consume a validated host result or yield a persistent request for one."""
    state.phase = kind
    if state.incoming is not None:
        result = RESULTS[kind].model_validate(state.incoming)
        state.incoming = None
        return result
    state.status = "waiting"
    state.pending = Action(
        kind=kind,
        instructions=instructions,
        payload={"query": state.query, "workspace": state.workspace, **payload},
        result_schema=RESULTS[kind].model_json_schema(),
    )
    return None


class Classify(BaseNode[RunState, None, dict]):
    async def run(self, ctx: GraphRunContext[RunState, None]) -> Context | Answer:
        state = ctx.state
        decision = jev.classify(state.query)
        state.query_kind = decision["query_kind"]
        state.history.append({"classification": decision})
        if state.query_kind == "kq":
            return Answer()
        state.ticket = decision["ticket"]
        return Context()


class Context(BaseNode[RunState, None, dict]):
    async def run(self, ctx: GraphRunContext[RunState, None]) -> Plan | AwaitHost:
        state = ctx.state
        result = exchange(
            state,
            "context",
            "In the parent, inspect relevant repo files and discover candidate prior conversations "
            "in Claude, Codex, Pi, and Grok in parallel. Return candidate excerpts and references; "
            "the graph filters relevance. Report unreadable histories in unavailable_harnesses. "
            "Preserve user changes. Return empty lists where there is no evidence.",
            {"ticket": state.ticket},
        )
        if result is None:
            return AwaitHost()
        selected = []
        for conversation in result.conversations:
            if jev.relevance(state.query, conversation.text)["relevant"]:
                selected.append(conversation.model_dump())
        state.context = {**result.model_dump(), "conversations": selected}
        return Plan()


def agent_instructions(state: RunState, role: str) -> str:
    spec = state.ticket[role]
    if state.harness == "codex":
        return (
            f"Spawn custom agent {spec['agent']} with its configured model and effort. "
            "Do not substitute a default worker or inherit the parent's model. "
        )
    return (
        f"Use {spec['model']} at {spec['effort']} effort when the harness supports selection. "
        f"Otherwise use its {'strongest' if role == 'planning' else 'normal coding'} model "
        f"at {spec['effort']} effort. "
    )


class Plan(BaseNode[RunState, None, dict]):
    async def run(self, ctx: GraphRunContext[RunState, None]) -> Execute | AwaitHost:
        state = ctx.state
        result = exchange(
            state,
            "plan",
            "Load the selected conversations and their referenced files when available. "
            + agent_instructions(state, "planning")
            + "Keep the parent and planning agent in normal execution mode. "
            "Do not enter Plan mode or request a mode switch. "
            "Ask it to return an implementation plan. "
            "Give it the query, context, testing instruction, current PR, "
            "and kept findings. It must not edit or execute the entire workflow.",
            {
                "ticket": state.ticket,
                "context": state.context,
                "previous_execution": state.execution,
                "findings": state.findings,
                "pass": state.loops + 1,
            },
        )
        if result is None:
            return AwaitHost()
        state.plan = result.plan
        return Execute()


class Execute(BaseNode[RunState, None, dict]):
    async def run(self, ctx: GraphRunContext[RunState, None]) -> Review | AwaitHost:
        state = ctx.state
        result = exchange(
            state,
            "execute",
            agent_instructions(state, "execution")
            + "Assign implementation ownership and tell it to preserve other people's edits. "
            "Implement the plan using isolated-pr-workflow and the ticket's testing instruction. "
            "Open the PR as a draft and keep the worktree. On revisions, use the same PR and "
            "worktree. Return actual tests and PR evidence. If blocked, use the block command "
            "instead of inventing evidence.",
            {
                "ticket": state.ticket,
                "plan": state.plan,
                "previous_execution": state.execution,
                "findings": state.findings,
                "pass": state.loops + 1,
            },
        )
        if result is None:
            return AwaitHost()
        if state.execution and (
            result.pr_url != state.execution["pr_url"]
            or result.worktree != state.execution["worktree"]
        ):
            raise ValueError("A revision must use the existing PR and worktree")
        state.execution = result.model_dump()
        return Review()


def reviewer_jobs() -> list[dict]:
    source = Path(__file__).parent / "skills/staff/references/reviewers.md"
    sections = source.read_text().split("\n## ")[1:]
    rubrics = {name: body.strip() for name, body in (part.split("\n", 1) for part in sections)}
    return [{"reviewer": name, "instructions": rubrics[name]} for name in REVIEWERS]


class Review(BaseNode[RunState, None, dict]):
    async def run(self, ctx: GraphRunContext[RunState, None]) -> Synthesize | AwaitHost:
        state = ctx.state
        result = exchange(
            state,
            "review",
            "Run the five reviewer jobs as isolated subagents, in parallel as capacity permits. "
            "Each gets only its own rubric and the implementation evidence. They do not edit. "
            "Return all five reviews; an empty list means that reviewer found no defects.",
            {"jobs": reviewer_jobs(), "execution": state.execution, "plan": state.plan},
        )
        if result is None:
            return AwaitHost()
        state.findings = [
            {"reviewer": name, "finding": finding}
            for name in REVIEWERS
            for finding in result.reviews[name]
        ]
        return Synthesize()


class Synthesize(BaseNode[RunState, None, dict]):
    async def run(self, ctx: GraphRunContext[RunState, None]) -> Plan | Confidence:
        state = ctx.state
        state.findings = jev.filter_findings(state.query, state.findings)
        state.loops += 1
        state.history.append({"pass": state.loops, "kept_findings": state.findings})
        if state.findings and state.loops < state.ticket["max_loops"]:
            return Plan()
        return Confidence()


class Confidence(BaseNode[RunState, None, dict]):
    async def run(self, ctx: GraphRunContext[RunState, None]) -> Finalize:
        state = ctx.state
        evidence = {
            "execution": state.execution,
            "kept_findings": state.findings,
            "passes": state.loops,
            "max_loops": state.ticket["max_loops"],
            "testing": state.ticket["testing"],
        }
        verdict = jev.confidence(state.query, json.dumps(evidence))["confidence"]
        # A probabilistic confidence vote cannot override unresolved reviewer findings.
        state.confidence = "low" if state.findings else verdict
        state.history.append({"confidence": state.confidence})
        return Finalize()


class Finalize(BaseNode[RunState, None, dict]):
    async def run(self, ctx: GraphRunContext[RunState, None]) -> Done | AwaitHost:
        state = ctx.state
        high = state.confidence == "high"
        result = exchange(
            state,
            "finalize",
            (
                "Mark the PR ready for review. Verify the worktree is clean and fully pushed, "
                "then remove only that temporary worktree. Return verified state."
                if high
                else "Leave the PR as a draft and retain the worktree. Return verified state."
            ),
            {"confidence": state.confidence, "execution": state.execution},
        )
        if result is None:
            return AwaitHost()
        expected = "ready" if high else "draft"
        if (
            result.pr_url != state.execution["pr_url"]
            or result.pr_state != expected
            or result.worktree_removed != high
        ):
            raise ValueError(f"Expected the existing PR {expected}, worktree_removed={high}")
        return Done()


class AwaitHost(BaseNode[RunState, None, dict]):
    async def run(self, ctx: GraphRunContext[RunState, None]) -> End[dict]:
        return End(response(ctx.state))


class Answer(BaseNode[RunState, None, dict]):
    async def run(self, ctx: GraphRunContext[RunState, None]) -> End[dict]:
        ctx.state.status = "complete"
        return End(response(ctx.state))


class Done(BaseNode[RunState, None, dict]):
    async def run(self, ctx: GraphRunContext[RunState, None]) -> End[dict]:
        ctx.state.status = "complete"
        return End(response(ctx.state))


NODES = {
    "classify": Classify,
    "context": Context,
    "plan": Plan,
    "execute": Execute,
    "review": Review,
    "synthesize": Synthesize,
    "confidence": Confidence,
    "finalize": Finalize,
    "done": Done,
    "answer": Answer,
    "await_host": AwaitHost,
}


class Resume(BaseNode[RunState, None, dict]):
    async def run(
        self, ctx: GraphRunContext[RunState, None]
    ) -> Classify | Context | Plan | Execute | Review | Finalize:
        return NODES[ctx.state.phase]()


def build_graph():
    builder = GraphBuilder(
        name="staff",
        state_type=RunState,
        input_type=Resume,
        output_type=dict,
        auto_instrument=False,
    )
    builder.add(builder.edge_from(builder.start_node).to(Resume), builder.node(Resume))
    for node in NODES.values():
        builder.add(builder.node(node))
    return builder.build()


GRAPH = build_graph()


class RunStore:
    """Atomic local checkpoints; host callbacks cannot change server-owned state."""

    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "runs.sqlite3"
        with self.connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, state TEXT)")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
        finally:
            connection.close()

    def load(self, connection, run_id: str) -> RunState:
        row = connection.execute("SELECT state FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown run {run_id}; use the ID returned by start")
        return RunState.model_validate_json(row[0])

    def save(self, connection, state: RunState):
        connection.execute(
            "INSERT OR REPLACE INTO runs VALUES (?, ?)", (state.id, state.model_dump_json())
        )

    def start(self, query: str, harness: Harness, workspace: Path, *, explicit: bool = False):
        if not explicit:
            return {"status": "direct", "instruction": "Handle this request with the base model."}
        if not query.strip():
            raise ValueError("A staff invocation needs a nonempty query")
        state = RunState(query=query, harness=harness, workspace=str(workspace.resolve()))
        with self.connect() as connection:
            result = asyncio.run(GRAPH.run(state=state, inputs=Resume()))
            self.save(connection, state)
        return result

    def status(self, run_id: str):
        with self.connect() as connection:
            return response(self.load(connection, run_id))

    def advance(self, run_id: str, action_id: str, result: dict):
        with self.connect() as connection:
            state = self.load(connection, run_id)
            self.check_action(state, action_id)
            action = state.pending
            validated = RESULTS[action.kind].model_validate(result)
            state.incoming = validated.model_dump()
            state.history.append({"action_id": action.id, "kind": action.kind, "result": result})
            state.pending = None
            state.blocked_reason = None
            state.status = "running"
            output = asyncio.run(GRAPH.run(state=state, inputs=Resume()))
            self.save(connection, state)
            return output

    @staticmethod
    def check_action(state: RunState, action_id: str):
        if state.status not in {"waiting", "blocked"} or state.pending is None:
            raise ValueError(f"Run is {state.status}; it has no pending action")
        if state.pending.id != action_id:
            raise ValueError(
                "Stale or incorrect action ID; use status to retrieve the pending action"
            )

    def block(self, run_id: str, action_id: str, reason: str):
        if not reason.strip():
            raise ValueError("A block needs a reason")
        with self.connect() as connection:
            state = self.load(connection, run_id)
            self.check_action(state, action_id)
            state.status = "blocked"
            state.blocked_reason = reason
            self.save(connection, state)
            return response(state)

    def cancel(self, run_id: str):
        with self.connect() as connection:
            state = self.load(connection, run_id)
            if state.status in {"complete", "cancelled"}:
                raise ValueError(f"Run is already {state.status}")
            state.status = "cancelled"
            state.pending = None
            self.save(connection, state)
            return response(state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_store = (
        Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local/state")) / "agentic-staff"
    )
    parser.add_argument("--state-dir", type=Path, default=default_store)
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="Start an explicitly invoked staff request")
    start.add_argument("--explicit", action="store_true")
    start.add_argument("--harness", choices=jev.HARNESSES, required=True)
    start.add_argument("--workspace", type=Path, default=Path.cwd())
    query = start.add_mutually_exclusive_group(required=True)
    query.add_argument("--query")
    query.add_argument("--query-file", type=Path)
    advance = commands.add_parser("advance", help="Return evidence for the pending host action")
    advance.add_argument("--run", required=True)
    advance.add_argument("--action", required=True)
    advance.add_argument("--result-file", type=Path, required=True)
    status = commands.add_parser("status", help="Show the pending action without rerunning it")
    status.add_argument("--run", required=True)
    block = commands.add_parser(
        "block", help="Record a blocker while preserving the pending action"
    )
    block.add_argument("--run", required=True)
    block.add_argument("--action", required=True)
    block.add_argument("--reason", required=True)
    cancel = commands.add_parser("cancel", help="Cancel a run at the user's request")
    cancel.add_argument("--run", required=True)
    commands.add_parser("diagram", help="Render the executable graph as Mermaid, locally")
    args = parser.parse_args()
    try:
        if args.command == "diagram":
            print(GRAPH.render(direction="LR"))
            return
        # The default path performs no classification and creates no local state.
        if args.command == "start" and not args.explicit:
            print(json.dumps({"status": "direct", "instruction": "Use the base model."}))
            return
        store = RunStore(args.state_dir)
        if args.command == "start":
            query = args.query_file.read_text() if args.query_file else args.query
            output = store.start(query, args.harness, args.workspace, explicit=args.explicit)
        elif args.command == "advance":
            output = store.advance(args.run, args.action, json.loads(args.result_file.read_text()))
        elif args.command == "status":
            output = store.status(args.run)
        elif args.command == "block":
            output = store.block(args.run, args.action, args.reason)
        else:
            output = store.cancel(args.run)
        print(json.dumps(output, indent=2))
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
