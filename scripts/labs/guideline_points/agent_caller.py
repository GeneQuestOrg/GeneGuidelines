"""A ``PointsCaller`` whose model is a person-operated agent, not the Anthropic API: for prompt work that must not spend API money.

Each model call becomes a request file an agent (a Claude Code subagent, Sonnet for the writers and Opus for the checkers) reads and answers by writing a JSON file. The pipeline is not kept alive between calls. It is replayed: a call whose answer file exists returns it, the first call without one writes its request and stops the run with ``NeedAnswer``. The pipeline is deterministic given its answers, so every replay reaches the same next call, and the product code runs unchanged.

This is not the production request: no pinned effort, no response schema enforced by the API, no prompt cache, and the agent reads the documents with a file tool. It measures what the prompts select and write, not cost or latency. Anything decided here is confirmed with the real adapter before it goes live.
"""

from __future__ import annotations

import hashlib
import json
import sys
import textwrap
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from backend.guidelines.points.bricks.base import CheckerOutput
from backend.guidelines.points.bricks.documents import DocumentReading
from backend.guidelines.points.bricks.question_en import QuestionOutput
from backend.guidelines.points.bricks.select import CoverageReview
from backend.guidelines.points.bricks.summary_en import SummaryOutput
from backend.guidelines.points.bricks.translate_pl import PolishOutput

from .common import REPO_ROOT

# Longest line of a documents file written for an agent (a tool limit, not a limit on content).
MAX_LINE = 1500

RESULT_TYPES: dict[str, type[BaseModel]] = {cls.__name__: cls for cls in (DocumentReading, CoverageReview, CheckerOutput, SummaryOutput, QuestionOutput, PolishOutput)}

REQUEST_TEMPLATE = """# Model call {key} ({role})

You are standing in for one call to a language model inside a pipeline. Do exactly what the system prompt and the task below ask, and nothing else. Use only what is in this file and in the documents file it names; do not open any other file, and do not rely on what you may know about the disease from elsewhere.

## System prompt

{system}

## Documents

{documents}

## Task

{user}

## Your answer

Write one JSON object that matches the JSON Schema below to this file:

{answer_path}

```json
{schema}
```

Then check it with this command, from the directory `{repo}`:

```
{python} -m scripts.labs.guideline_points.lab bricks-agent-check --request {request_json}
```

It prints `OK` or what is wrong. Correct the file until it prints `OK`.
"""


class NeedAnswer(Exception):
    """The run stopped at a call no agent has answered yet; its request file is ready."""

    def __init__(self, key: str, model: str, role: str, request_path: Path) -> None:
        super().__init__(f"{role} ({model}) needs an answer: {request_path}")
        self.key, self.model, self.role, self.request_path = key, model, role, request_path


def _digest(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def _wrapped(text: str) -> str:
    """The same text with long lines broken at spaces: a file-reading tool may cut a line of several thousand characters, and the checks compare text with whitespace normalised."""
    lines: list[str] = []
    for line in text.split("\n"):
        lines.extend(textwrap.wrap(line, MAX_LINE, break_long_words=False, break_on_hyphens=False) if len(line) > MAX_LINE else [line])
    return "\n".join(lines)


class AgentFileCaller:
    """One model role answered through files in ``work``; ``model`` is the agent's model name (``sonnet`` or ``opus``)."""

    def __init__(self, model: str, work: Path) -> None:
        self.model, self.work = model, work
        for sub in ("requests", "answers"):
            (work / sub).mkdir(parents=True, exist_ok=True)

    async def call(self, *, role: str, system: str, prefix: str, user: str, result_type: type[BaseModel], cache: bool = True) -> tuple[BaseModel | None, dict[str, Any]]:
        key = _digest(self.model, role, system, prefix, user, result_type.__name__)
        answer_path = self.work / "answers" / f"{key}.json"
        record: dict[str, Any] = {"role": role, "model": f"agent:{self.model}", "key": key, "prompt_chars": len(system) + len(prefix) + len(user), "ok": False, "error": None, "usage_total": {}, "cost_usd_total": 0.0}
        if answer_path.is_file():
            try:
                output = result_type.model_validate_json(answer_path.read_text(encoding="utf-8"))
            except ValidationError:
                answer_path.rename(answer_path.with_suffix(".invalid.json"))
            else:
                record["ok"], record["output"] = True, output.model_dump()
                return output, record
        raise NeedAnswer(key, self.model, role, self._write_request(key, role, system, prefix, user, result_type, answer_path))

    def _write_request(self, key: str, role: str, system: str, prefix: str, user: str, result_type: type[BaseModel], answer_path: Path) -> Path:
        documents = "(this call has no documents)"
        if prefix:
            documents_path = self.work / f"documents-{_digest(prefix)}.txt"
            if not documents_path.is_file():
                documents_path.write_text(_wrapped(prefix), encoding="utf-8")
            documents = f"The documents are in this file. Read the whole file, to its last line, before you answer (it is long: read it in consecutive parts, and do not search it or skim it instead of reading it). Paragraphs are separated by blank lines; a long paragraph runs over several lines.\n\n{documents_path}"
        request_json = self.work / "requests" / f"{key}.json"
        request_json.write_text(json.dumps({"key": key, "role": role, "model": self.model, "result_type": result_type.__name__, "answer_path": str(answer_path)}), encoding="utf-8")
        request_md = self.work / "requests" / f"{key}.md"
        request_md.write_text(
            REQUEST_TEMPLATE.format(
                key=key, role=role, system=system, documents=documents, user=user, answer_path=answer_path,
                schema=json.dumps(result_type.model_json_schema(), indent=1), repo=REPO_ROOT, python=sys.executable, request_json=request_json,
            ),
            encoding="utf-8",
        )
        return request_md


def check_answer(request_json: Path) -> str | None:
    """What is wrong with the answer to a request, or None when it parses as the result type the call expects."""
    request = json.loads(request_json.read_text(encoding="utf-8"))
    answer = Path(request["answer_path"])
    if not answer.is_file():
        return f"no answer file at {answer}"
    try:
        RESULT_TYPES[request["result_type"]].model_validate_json(answer.read_text(encoding="utf-8"))
    except ValidationError as exc:
        return str(exc)
    return None


__all__ = ["AgentFileCaller", "NeedAnswer", "check_answer"]
