"""Main agent orchestrator — coordinates the full analysis loop."""

import asyncio
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import AsyncGenerator, Callable

from agent.paper_parser import parse_url
from agent.planner import generate_plan
from agent.code_writer import generate_code, fix_code
from agent.evaluator import evaluate_output
from agent.image_resolver import resolve_image
from data.api import DataAPI
from container_runtime.executor import DockerExecutor
from config import settings
from skills.manager import SkillManager
from memory.manager import MemoryManager
from agent.analysis_log import write_analysis_log


class SessionState(str, Enum):
    IDLE = "idle"
    CONVERSING = "conversing"
    READY = "ready"
    PARSING = "parsing"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    RESOLVING_ENV = "resolving_env"
    WRITING_CODE = "writing_code"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


RECOVERABLE_ACTIVE_STATES = {
    SessionState.PARSING,
    SessionState.PLANNING,
    SessionState.RESOLVING_ENV,
    SessionState.WRITING_CODE,
    SessionState.EXECUTING,
    SessionState.EVALUATING,
}


@dataclass
class Message:
    role: str  # "user", "assistant", "system"
    content: str
    msg_type: str = "text"  # "text", "plan", "code", "output", "result", "error"
    data: dict = field(default_factory=dict)


@dataclass
class Session:
    id: str
    state: SessionState = SessionState.IDLE
    messages: list[Message] = field(default_factory=list)
    paper_info: dict = field(default_factory=dict)
    plan: dict = field(default_factory=dict)
    code: str = ""
    retry_count: int = 0
    max_retries: int = 3
    persist_callback: Callable[["Session"], None] | None = field(default=None, repr=False, compare=False)

    def add_message(self, role: str, content: str, msg_type: str = "text", data: dict = None) -> Message:
        msg = Message(role=role, content=content, msg_type=msg_type, data=data or {})
        self.messages.append(msg)
        if self.persist_callback:
            self.persist_callback(self)
        return msg


class Orchestrator:
    """Coordinates the agent loop: parse → plan → code → execute → evaluate.

    Integrates skills (pipeline templates) and memory (lessons) throughout.
    """

    def __init__(self):
        self.sessions_dir = settings.SESSION_STATE_DIR
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.executor = DockerExecutor()
        self.data_api = DataAPI()
        self.skill_manager = SkillManager()
        self.memory_manager = MemoryManager()
        self.sessions = self._load_sessions()

    def _session_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def _bind_session(self, session: Session) -> Session:
        session.persist_callback = self.persist_session
        return session

    def _serialize_session(self, session: Session) -> dict:
        return {
            "id": session.id,
            "state": session.state.value,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "msg_type": msg.msg_type,
                    "data": msg.data,
                }
                for msg in session.messages
            ],
            "paper_info": session.paper_info,
            "plan": session.plan,
            "code": session.code,
            "retry_count": session.retry_count,
            "max_retries": session.max_retries,
        }

    def _deserialize_session(self, data: dict) -> Session:
        messages = [
            Message(
                role=msg.get("role", "assistant"),
                content=msg.get("content", ""),
                msg_type=msg.get("msg_type", "text"),
                data=msg.get("data", {}) or {},
            )
            for msg in data.get("messages", [])
        ]
        state_value = data.get("state", SessionState.IDLE.value)
        try:
            state = SessionState(state_value)
        except ValueError:
            state = SessionState.IDLE

        if state in RECOVERABLE_ACTIVE_STATES:
            state = SessionState.FAILED
            messages.append(
                Message(
                    role="assistant",
                    content="The backend restarted while this run was active. Review the saved plan and replay it if needed.",
                    msg_type="system",
                    data={},
                )
            )

        session = Session(
            id=data["id"],
            state=state,
            messages=messages,
            paper_info=data.get("paper_info", {}) or {},
            plan=data.get("plan", {}) or {},
            code=data.get("code", "") or "",
            retry_count=int(data.get("retry_count", 0) or 0),
            max_retries=int(data.get("max_retries", 3) or 3),
        )
        return self._bind_session(session)

    def _load_sessions(self) -> dict[str, Session]:
        sessions: dict[str, Session] = {}
        for path in sorted(self.sessions_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
                session = self._deserialize_session(data)
                sessions[session.id] = session
            except Exception:
                continue
        return sessions

    def persist_session(self, session: Session):
        path = self._session_path(session.id)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(self._serialize_session(session), indent=2))
        tmp_path.replace(path)

    def _update_session(self, session: Session, **updates) -> Session:
        for key, value in updates.items():
            setattr(session, key, value)
        self.persist_session(session)
        return session

    def create_session(self, session_id: str | None = None) -> Session:
        session_id = session_id or str(uuid.uuid4())
        session = self._bind_session(Session(id=session_id))
        self.sessions[session_id] = session
        self.persist_session(session)
        return session

    def get_session(self, session_id: str) -> Session | None:
        return self.sessions.get(session_id)

    def _find_skill_registry(self, question: str, paper_info: dict) -> list[dict]:
        """Search for relevant skills using lightweight registry metadata only.

        Returns dicts with name/description/tags — no code_template.
        Used for planning phase to minimize tokens.
        """
        analysis_type = paper_info.get("analysis_type", "")
        tags = paper_info.get("packages", []) + paper_info.get("methods", [])
        return self.skill_manager.search_registry(
            query=question,
            analysis_type=analysis_type,
            tags=tags,
            limit=3,
        )

    def _find_lessons(self, question: str, paper_info: dict) -> list[dict]:
        """Search for relevant lessons based on question and paper info."""
        tags = paper_info.get("packages", []) + paper_info.get("methods", [])
        lessons = self.memory_manager.search_lessons(
            query=question,
            tags=tags,
            limit=5,
        )
        return [l.model_dump() for l in lessons]

    async def handle_message(
        self,
        session_id: str,
        content: str,
        paper_url: str | None = None,
    ) -> AsyncGenerator[Message, None]:
        """Handle a user message and yield response messages as they're generated."""
        session = self.get_session(session_id)
        if not session:
            session = self.create_session(session_id=session_id)

        session.add_message("user", content)

        # If user is approving a plan
        if session.state == SessionState.AWAITING_APPROVAL:
            if content.lower() in ("approve", "yes", "go", "run", "execute", "ok"):
                async for msg in self._execute_plan(session):
                    yield msg
                return
            elif content.lower() in ("reject", "no", "cancel"):
                self._update_session(session, state=SessionState.IDLE)
                yield session.add_message("assistant", "Plan rejected. Send a new question or paste a new URL.")
                return
            else:
                async for msg in self._replan(session, content):
                    yield msg
                return

        # Auto-detect URL in message
        if not paper_url:
            url_match = re.search(r'https?://\S+', content)
            if url_match:
                paper_url = url_match.group(0).rstrip(".,;:!?)")

        # If we're in a conversation, continue the checklist flow.
        if session.state == SessionState.CONVERSING:
            async for msg in self._converse(session, content):
                yield msg
            return

        # Checklists done — user is adding details or saying "go"
        if session.state == SessionState.READY:
            all_user_text = " ".join(
                m.content for m in session.messages if m.role == "user"
            )
            async for msg in self._start_analysis(session, all_user_text, paper_url):
                yield msg
            return

        # Triage: decide whether to start analysis or converse first
        if paper_url or self._is_analysis_ready(session, content):
            async for msg in self._start_analysis(session, content, paper_url):
                yield msg
        else:
            async for msg in self._converse(session, content):
                yield msg

    def _is_analysis_ready(self, session: Session, content: str) -> bool:
        """Check if the user's message has enough context to start analysis.

        Returns True when the message contains clear analysis intent with
        specific details like dataset IDs, analysis types, or tool names.
        Simple greetings or vague questions return False.
        """
        content_lower = content.lower().strip()

        # Short/vague messages — not ready
        if len(content_lower.split()) < 5:
            return False

        # Check for specific bioinformatics signals
        analysis_signals = [
            # Dataset references
            r'GSE\d+', r'GSM\d+', r'SRR\d+', r'PRJNA\d+', r'TCGA',
            # Specific analysis requests with detail
            r'differential\s+expression', r'gene\s+set\s+enrichment',
            r'peak\s+calling', r'clustering', r'trajectory',
            r'heatmap', r'volcano\s+plot', r'PCA',
            # Tool/package names indicating concrete intent
            r'DESeq2', r'scanpy', r'seurat', r'deeptools', r'macs2',
            r'edgeR', r'limma', r'cellranger',
        ]

        import re as _re
        for pattern in analysis_signals:
            if _re.search(pattern, content, _re.IGNORECASE):
                return True

        # If the user has already been conversing and provides a longer message
        # with analysis-like keywords, treat as ready
        if session.state == SessionState.CONVERSING and len(content_lower.split()) >= 10:
            broad_signals = [
                'analyz', 'analysis', 'compare', 'identify', 'quantif',
                'run', 'execute', 'perform', 'process', 'pipeline',
                'rnaseq', 'rna-seq', 'chipseq', 'chip-seq', 'atacseq',
                'atac-seq', 'scrna', 'single.cell', 'bulk',
            ]
            if any(kw in content_lower for kw in broad_signals):
                return True

        return False

    def _checklist_step(self, session: Session) -> int:
        """Count how many checklists have been answered.

        A checklist is 'answered' when a user message appears after it.
        Step 0: seq type, Step 1: analysis method, Step 2: input format, Step 3: output.
        Returns 4 when all answered → triggers summary.
        """
        checklists_answered = 0
        waiting_for_answer = False
        for m in session.messages:
            if m.msg_type == "checklist":
                waiting_for_answer = True
            elif m.role == "user" and waiting_for_answer:
                checklists_answered += 1
                waiting_for_answer = False
        return min(checklists_answered, 4)

    def _get_checklist_answers(self, session: Session) -> dict:
        """Extract checklist answers from session messages as {checklist_id: answer}."""
        answers = {}
        current_id = None
        for m in session.messages:
            if m.msg_type == "checklist":
                current_id = m.data.get("id")
            elif m.role == "user" and current_id:
                answers[current_id] = m.content
                current_id = None
        return answers

    async def _converse(
        self,
        session: Session,
        content: str,
    ) -> AsyncGenerator[Message, None]:
        """Guide the user through 4 dynamic checklists adapted to their seq type.

        Steps: seq type → analysis method → input format → expected output.
        Options for steps 2-4 adapt based on the user's previous selections.
        """
        from agent.guidance import SEQ_TYPES, get_output_options

        self._update_session(session, state=SessionState.CONVERSING)

        step = self._checklist_step(session)
        answers = self._get_checklist_answers(session)

        # Step 0: What sequencing type?
        if step == 0:
            if len([m for m in session.messages if m.role == "user"]) <= 1:
                yield session.add_message("assistant", "Hi! Let's set up your analysis.")
            yield session.add_message(
                "assistant",
                "What type of sequencing data?",
                msg_type="checklist",
                data={
                    "id": "seq_type",
                    "title": "What type of data are you working with?",
                    "options": [
                        {"value": key, "label": cfg["label"]}
                        for key, cfg in SEQ_TYPES.items()
                    ],
                    "allow_custom": True,
                    "custom_placeholder": "Or type your data type...",
                },
            )
            return

        # Resolve the seq type config for adaptive steps
        seq_type_answer = answers.get("seq_type", "")
        seq_key = self._resolve_seq_type(seq_type_answer)
        seq_config = SEQ_TYPES.get(seq_key, {})

        # Step 1: What analysis method? (adapts to seq type)
        if step == 1:
            methods = seq_config.get("methods", [
                {"value": "general", "label": "General analysis"},
            ])
            yield session.add_message(
                "assistant",
                "What analysis would you like to run?",
                msg_type="checklist",
                data={
                    "id": "method",
                    "title": "What analysis method? (or paste a paper/GitHub URL)",
                    "options": methods,
                    "allow_custom": True,
                    "custom_placeholder": "Or type a method / paste a URL...",
                },
            )
            return

        # Step 2: Input data format? (adapts to seq type)
        if step == 2:
            inputs = seq_config.get("inputs", [
                {"value": "file", "label": "Upload a file"},
                {"value": "geo", "label": "GEO accession (GSExxxxx)"},
            ])
            yield session.add_message(
                "assistant",
                "What's your input data?",
                msg_type="checklist",
                data={
                    "id": "input_format",
                    "title": "What input data do you have?",
                    "options": inputs,
                    "allow_custom": True,
                    "custom_placeholder": "Or describe your data source...",
                },
            )
            return

        # Step 3: Expected output? (adapts to seq type + method)
        if step == 3:
            method_answer = answers.get("method", "")
            method_key = self._resolve_method(method_answer, seq_config)
            output_options = get_output_options(seq_key, method_key)
            yield session.add_message(
                "assistant",
                "What output do you want?",
                msg_type="checklist",
                data={
                    "id": "output",
                    "title": "What output do you expect?",
                    "options": output_options,
                    "allow_custom": True,
                    "custom_placeholder": "Or describe what you need...",
                },
            )
            return

        # All 4 answered — store in paper_info and show summary
        self._update_session(session, state=SessionState.READY)

        # Store structured checklist data into paper_info for downstream use
        if seq_config:
            session.paper_info["analysis_type"] = seq_config.get("analysis_type", "general")
        session.paper_info["seq_type"] = answers.get("seq_type", "")
        session.paper_info["method"] = answers.get("method", "")
        session.paper_info["input_format"] = answers.get("input_format", "")
        session.paper_info["expected_output"] = answers.get("output", "")
        self.persist_session(session)

        labels = ["Data type", "Method", "Input", "Output"]
        keys = ["seq_type", "method", "input_format", "output"]
        summary_lines = []
        for label, key in zip(labels, keys):
            val = answers.get(key, "")
            if val:
                summary_lines.append(f"- **{label}:** {val}")

        summary = "\n".join(summary_lines)
        yield session.add_message(
            "assistant",
            f"Got it! Here's what I have:\n\n{summary}\n\n"
            "You can now:\n"
            "- **Paste a paper or GitHub URL** for me to extract methods from\n"
            "- **Add more details** (dataset IDs, comparisons, specific parameters)\n"
            "- Or just type **go** to start planning",
        )

    @staticmethod
    def _resolve_seq_type(answer: str) -> str:
        """Match a user's free-text seq type answer to a SEQ_TYPES key."""
        from agent.guidance import SEQ_TYPES

        answer_lower = answer.lower().strip()
        # Exact key match
        if answer_lower in SEQ_TYPES:
            return answer_lower
        # Match by label
        for key, cfg in SEQ_TYPES.items():
            if answer_lower == cfg["label"].lower():
                return key
        # Fuzzy keyword match
        keywords = {
            "scrna": ["single", "scrna", "sc-rna", "10x", "single-cell", "singlecell"],
            "bulk_rna": ["bulk", "deseq", "rna-seq", "rnaseq"],
            "chipseq": ["chip", "atac", "peak", "histone", "tf binding"],
            "spatial": ["spatial", "visium", "slide", "merfish", "stereo"],
        }
        for key, kws in keywords.items():
            if any(kw in answer_lower for kw in kws):
                return key
        return answer_lower  # fallback

    @staticmethod
    def _resolve_method(answer: str, seq_config: dict) -> str:
        """Match a user's free-text method answer to a method value."""
        answer_lower = answer.lower().strip()
        for m in seq_config.get("methods", []):
            if answer_lower == m["value"] or answer_lower == m["label"].lower():
                return m["value"]
            if m["value"] in answer_lower or answer_lower in m["label"].lower():
                return m["value"]
        return answer_lower

    async def _start_analysis(
        self,
        session: Session,
        question: str,
        paper_url: str | None = None,
    ) -> AsyncGenerator[Message, None]:
        """Start a new analysis: parse paper → generate plan."""

        # Step 1: Parse paper from URL
        if paper_url:
            self._update_session(session, state=SessionState.PARSING)
            yield session.add_message("assistant", f"Parsing paper from {paper_url}...", msg_type="system")

            try:
                self._update_session(session, paper_info=await parse_url(paper_url))
                yield session.add_message(
                    "assistant",
                    f"Paper parsed: {session.paper_info.get('summary', 'Analysis extracted')}",
                    msg_type="text",
                    data=session.paper_info,
                )
            except Exception as e:
                self._update_session(session, state=SessionState.FAILED)
                yield session.add_message("assistant", f"Failed to parse paper: {e}", msg_type="error")
                return
        elif not session.paper_info:
            self._update_session(
                session,
                paper_info={
                    "analysis_type": "general",
                    "methods": [],
                    "packages": [],
                    "language": "python",
                    "datasets": [],
                    "key_parameters": {},
                    "summary": question,
                },
            )

        # Find relevant skills (registry metadata only — no code templates)
        skills = self._find_skill_registry(question, session.paper_info)
        lessons = self._find_lessons(question, session.paper_info)

        if skills:
            skill_names = [s["name"] for s in skills]
            yield session.add_message(
                "assistant",
                f"Found matching skills: {', '.join(skill_names)}",
                msg_type="system",
            )

        if lessons:
            yield session.add_message(
                "assistant",
                f"Loaded {len(lessons)} relevant lessons from memory",
                msg_type="system",
            )

        # Step 2: Generate plan (with skills registry + lessons context)
        self._update_session(session, state=SessionState.PLANNING)
        yield session.add_message("assistant", "Generating analysis plan...", msg_type="system")

        try:
            # Pass lightweight skill registry (no code templates) to planner
            self._update_session(
                session,
                plan=await generate_plan(
                    session.paper_info, question,
                    skills=skills,
                    lessons=lessons,
                ),
            )
            self._update_session(session, state=SessionState.AWAITING_APPROVAL)

            plan_text = self._format_plan(session.plan)
            yield session.add_message("assistant", plan_text, msg_type="plan", data=session.plan)
            yield session.add_message(
                "assistant",
                "Review the plan above. Reply **approve** to execute, or describe changes you'd like.",
                msg_type="system",
            )
        except Exception as e:
            self._update_session(session, state=SessionState.FAILED)
            yield session.add_message("assistant", f"Failed to generate plan: {e}", msg_type="error")

    async def _replan(self, session: Session, modifications: str) -> AsyncGenerator[Message, None]:
        """Regenerate plan with user modifications."""
        self._update_session(session, state=SessionState.PLANNING)
        yield session.add_message("assistant", "Updating plan with your feedback...", msg_type="system")

        modified_question = (
            f"Original question: {session.messages[0].content if session.messages else ''}\n\n"
            f"User modifications: {modifications}"
        )

        skills = self._find_skill_registry(modified_question, session.paper_info)
        lessons = self._find_lessons(modified_question, session.paper_info)

        try:
            self._update_session(
                session,
                plan=await generate_plan(
                    session.paper_info, modified_question,
                    skills=skills, lessons=lessons,
                ),
            )
            self._update_session(session, state=SessionState.AWAITING_APPROVAL)

            plan_text = self._format_plan(session.plan)
            yield session.add_message("assistant", plan_text, msg_type="plan", data=session.plan)
            yield session.add_message(
                "assistant",
                "Updated plan ready. Reply **approve** to execute, or describe more changes.",
                msg_type="system",
            )
        except Exception as e:
            self._update_session(session, state=SessionState.FAILED)
            yield session.add_message("assistant", f"Failed to update plan: {e}", msg_type="error")

    async def _execute_plan(self, session: Session) -> AsyncGenerator[Message, None]:
        """Execute an approved plan: resolve env → write code → run → evaluate."""
        plan = session.plan

        # Progressive loading: only load the chosen skill's full content
        question = session.messages[0].content if session.messages else ""
        lessons = self._find_lessons(question, session.paper_info)

        # Load only the skill the planner selected (if any)
        skill_ref = plan.get("skill_reference")
        skill_content = None
        if skill_ref:
            skill_content = self.skill_manager.load_skill_content(skill_ref)

        # Track skill names for logging
        skills_used = [skill_ref] if skill_ref else []

        # Step 3: Resolve environment
        self._update_session(session, state=SessionState.RESOLVING_ENV)
        yield session.add_message("assistant", "Setting up execution environment...", msg_type="system")

        try:
            base_image = plan.get("base_image", "python-general")
            extra_packages = plan.get("extra_packages", [])
            image_tag = await resolve_image(base_image, extra_packages)
            yield session.add_message("assistant", f"Using image: `{image_tag}`", msg_type="system")
        except Exception as e:
            self._update_session(session, state=SessionState.FAILED)
            yield session.add_message("assistant", f"Environment setup failed: {e}", msg_type="error")
            return

        # Step 4: Mount data (only for downloadable datasets — GEO/TCGA)
        # Local data (models, user files) is auto-mounted by the executor.
        data_mounts = {}
        dataset_ids = [d["id"] if isinstance(d, dict) else d for d in plan.get("datasets", [])]
        # Filter to only downloadable dataset formats
        downloadable = [d for d in dataset_ids if d.upper().startswith("GSE") or d.upper().startswith("TCGA-")]
        skipped = [d for d in dataset_ids if d not in downloadable]
        if skipped:
            yield session.add_message(
                "assistant",
                f"Skipping non-downloadable dataset IDs (already auto-mounted or not supported): {', '.join(skipped)}",
                msg_type="system",
            )
        if downloadable:
            yield session.add_message("assistant", f"Mounting datasets: {', '.join(downloadable)}", msg_type="system")
            try:
                data_mounts = await self.data_api.mount_datasets(downloadable)
            except Exception as e:
                yield session.add_message("assistant", f"Warning: Dataset mount failed: {e}", msg_type="error")

        # Step 5: Write code (with single skill content + lessons)
        self._update_session(session, state=SessionState.WRITING_CODE)
        yield session.add_message("assistant", "Writing analysis code...", msg_type="system")

        language = plan.get("language", "python")
        try:
            self._update_session(
                session,
                code=await generate_code(plan, language, skill_content=skill_content, lessons=lessons),
            )
            yield session.add_message("assistant", session.code, msg_type="code", data={"language": language})
        except Exception as e:
            self._update_session(session, state=SessionState.FAILED)
            yield session.add_message("assistant", f"Code generation failed: {e}", msg_type="error")
            return

        # Step 6-8: Execute and evaluate loop
        total_attempts = session.max_retries + 1
        self._update_session(session, retry_count=0)

        # Loop detection: track error signatures to break repeated failures
        _error_hashes: list[str] = []

        while session.retry_count <= session.max_retries:
            self._update_session(session, state=SessionState.EXECUTING)
            attempt = session.retry_count + 1
            yield session.add_message(
                "assistant",
                f"Running analysis (attempt {attempt}/{total_attempts})..."
                if attempt > 1 else
                f"Running analysis...",
                msg_type="system",
            )

            output_lines = []
            # Buffer for streaming: accumulate lines and flush periodically
            _stream_buffer = []
            _last_flush = [0.0]  # mutable ref for closure

            async def on_output(line: str):
                import time
                output_lines.append(line)
                _stream_buffer.append(line)
                # Flush every 2 seconds or every 20 lines to avoid message spam
                now = time.time()
                if now - _last_flush[0] > 2.0 or len(_stream_buffer) >= 20:
                    chunk = "".join(_stream_buffer)
                    _stream_buffer.clear()
                    _last_flush[0] = now
                    session.add_message("assistant", chunk.rstrip(), msg_type="output")

            try:
                result = await self.executor.run_script(
                    image=image_tag,
                    code=session.code,
                    language=language,
                    session_id=session.id,
                    data_mounts=data_mounts,
                    on_output=on_output,
                )
                # Flush remaining buffer
                if _stream_buffer:
                    session.add_message("assistant", "".join(_stream_buffer).rstrip(), msg_type="output")
                    _stream_buffer.clear()
            except Exception as e:
                self._update_session(session, state=SessionState.FAILED)
                yield session.add_message("assistant", f"Execution error: {e}", msg_type="error")
                return

            yield session.add_message(
                "assistant",
                result["stdout"][-3000:] if result["stdout"] else "(no output)",
                msg_type="output",
            )

            if result["stderr"]:
                yield session.add_message(
                    "assistant",
                    f"Stderr:\n{result['stderr'][-2000:]}",
                    msg_type="output",
                )

            # Auto-install missing packages without burning a retry
            if result["exit_code"] != 0:
                stderr_text = result["stderr"] or result["stdout"]
                from container_runtime.executor import parse_missing_module, parse_missing_r_package, IMPORT_TO_PACKAGE

                missing_pkg = (
                    parse_missing_module(stderr_text) if language == "python"
                    else parse_missing_r_package(stderr_text)
                )

                if missing_pkg:
                    pkg_name = IMPORT_TO_PACKAGE.get(missing_pkg, missing_pkg) if language == "python" else missing_pkg
                    yield session.add_message(
                        "assistant",
                        f"Missing package detected: `{pkg_name}`. Installing and re-running...",
                        msg_type="system",
                    )

                    try:
                        retry_result = await self.executor.install_and_retry(
                            image=image_tag,
                            code=session.code,
                            language=language,
                            stderr=stderr_text,
                            session_id=session.id,
                            data_mounts=data_mounts,
                            on_output=on_output,
                        )
                        if retry_result:
                            result = retry_result
                            yield session.add_message(
                                "assistant",
                                result["stdout"][-3000:] if result["stdout"] else "(no output)",
                                msg_type="output",
                            )
                    except Exception:
                        pass

            # Step 8: Evaluate
            self._update_session(session, state=SessionState.EVALUATING)
            exit_status = "exit 0" if result["exit_code"] == 0 else f"exit {result['exit_code']}"
            n_files = len(result["output_files"])
            yield session.add_message(
                "assistant",
                f"Evaluating results ({exit_status}, {n_files} output file{'s' if n_files != 1 else ''})...",
                msg_type="system",
            )

            try:
                evaluation = await evaluate_output(
                    stdout=result["stdout"],
                    stderr=result["stderr"],
                    exit_code=result["exit_code"],
                    output_files=result["output_files"],
                    plan=plan,
                )
            except Exception as eval_err:
                # Evaluator failed (API down) — use simple heuristic
                has_outputs = len(result["output_files"]) > 0
                evaluation = {
                    "success": result["exit_code"] == 0 and has_outputs,
                    "summary": f"Evaluation API unavailable ({eval_err}). "
                               f"Exit code: {result['exit_code']}, "
                               f"output files: {len(result['output_files'])}.",
                    "outputs": result["output_files"],
                    "errors": [],
                    "suggestion": None if result["exit_code"] == 0 else "Check error output.",
                }

            if evaluation.get("success"):
                self._update_session(session, state=SessionState.COMPLETED)
                yield session.add_message(
                    "assistant",
                    evaluation.get("summary", "Analysis completed successfully."),
                    msg_type="result",
                    data={
                        "output_files": result["output_files"],
                        "workspace": result["workspace"],
                        "evaluation": evaluation,
                    },
                )

                # Auto-extract lessons from successful analysis
                new_lessons = []
                try:
                    new_lessons = await self.memory_manager.extract_lessons(
                        plan=plan,
                        code=session.code,
                        stdout=result["stdout"],
                        stderr=result["stderr"],
                        evaluation=evaluation,
                        session_id=session.id,
                    )
                    if new_lessons:
                        titles = [l.title for l in new_lessons]
                        yield session.add_message(
                            "assistant",
                            f"Saved {len(new_lessons)} lessons: {'; '.join(titles)}",
                            msg_type="system",
                            data={"lessons": [l.model_dump() for l in new_lessons]},
                        )
                except Exception:
                    pass

                # Write analysis log
                try:
                    question = session.messages[0].content if session.messages else ""
                    log_path = write_analysis_log(
                        session_id=session.id,
                        question=question,
                        paper_info=session.paper_info,
                        plan=plan,
                        code=session.code,
                        language=language,
                        result=result,
                        evaluation=evaluation,
                        lessons=[l.model_dump() for l in new_lessons],
                        skills_used=skills_used,
                        retries=session.retry_count,
                    )
                    yield session.add_message(
                        "assistant",
                        f"Analysis log saved: `{log_path}`",
                        msg_type="system",
                    )
                except Exception:
                    pass

                return

            # Failed — try to fix
            self._update_session(session, retry_count=session.retry_count + 1)

            # Loop detection: hash the error signature to detect repeated failures.
            # If the same error appears twice, the fix isn't working — bail early.
            suggestion = evaluation.get("suggestion", "")
            raw_error = result["stderr"] or result["stdout"]
            error_sig = self._error_signature(raw_error, suggestion)
            if error_sig in _error_hashes:
                self._update_session(session, state=SessionState.FAILED)
                yield session.add_message(
                    "assistant",
                    f"Detected repeated error — the same failure occurred twice, "
                    f"stopping to avoid wasting retries.\n\n"
                    f"Error: {suggestion or raw_error[-500:]}\n\n"
                    "Try modifying the plan or providing more details.",
                    msg_type="error",
                    data={"evaluation": evaluation, "loop_detected": True},
                )
                # Write failure log
                try:
                    question = session.messages[0].content if session.messages else ""
                    write_analysis_log(
                        session_id=session.id,
                        question=question,
                        paper_info=session.paper_info,
                        plan=plan,
                        code=session.code,
                        language=language,
                        result=result,
                        evaluation=evaluation,
                        skills_used=skills_used,
                        retries=session.retry_count,
                    )
                except Exception:
                    pass
                return
            _error_hashes.append(error_sig)

            if session.retry_count > session.max_retries:
                self._update_session(session, state=SessionState.FAILED)
                yield session.add_message(
                    "assistant",
                    f"Analysis failed after {session.max_retries + 1} attempts.\n\n"
                    f"Last error: {suggestion or 'Unknown error'}\n\n"
                    "You can try modifying the plan or asking a different question.",
                    msg_type="error",
                    data={"evaluation": evaluation},
                )

                # Write failure log
                try:
                    question = session.messages[0].content if session.messages else ""
                    write_analysis_log(
                        session_id=session.id,
                        question=question,
                        paper_info=session.paper_info,
                        plan=plan,
                        code=session.code,
                        language=language,
                        result=result,
                        evaluation=evaluation,
                        skills_used=skills_used,
                        retries=session.retry_count,
                    )
                except Exception:
                    pass

                return

            # Fix code (with lessons context to avoid repeating mistakes)
            yield session.add_message(
                "assistant",
                f"Fixing code (attempt {attempt}/{total_attempts}): {suggestion}",
                msg_type="system",
            )
            # Build focused error context: evaluator suggestion + last 2000 chars of stderr
            error_context = ""
            if suggestion:
                error_context += f"Evaluator diagnosis: {suggestion}\n\n"
            error_context += f"Error output (last 2000 chars):\n{raw_error[-2000:]}"

            # Include previous error signatures so the LLM avoids the same fix
            if len(_error_hashes) > 1:
                error_context += (
                    f"\n\nWARNING: Previous fix attempts failed with similar errors. "
                    f"Try a fundamentally different approach."
                )

            try:
                self._update_session(
                    session,
                    code=await fix_code(session.code, error_context, plan, language, lessons=lessons),
                )
                yield session.add_message("assistant", session.code, msg_type="code", data={"language": language})
            except Exception as e:
                self._update_session(session, state=SessionState.FAILED)
                yield session.add_message("assistant", f"Code fix failed: {e}", msg_type="error")
                return

    @staticmethod
    def _error_signature(stderr: str, suggestion: str) -> str:
        """Hash the core error pattern to detect repeated failures.

        Normalizes the error by extracting the exception type and key message,
        stripping variable parts like line numbers, timestamps, and paths.
        """
        # Extract the core error line (last Traceback exception, or R error)
        core = suggestion or ""
        for pattern in [
            # Python: "ModuleNotFoundError: No module named 'foo'"
            r'(\w+Error): (.+)',
            # Python: "TypeError: ..."
            r'(\w+Exception): (.+)',
            # R: "Error in foo(...) : something"
            r'(Error in .+?) :',
            # Generic fatal
            r'(fatal|FATAL|Killed|OOM)',
        ]:
            m = re.search(pattern, stderr[-2000:])
            if m:
                core = m.group(0)
                break

        # Strip variable parts: line numbers, hex addresses, timestamps, paths
        normalized = re.sub(r'line \d+', 'line N', core)
        normalized = re.sub(r'0x[0-9a-fA-F]+', '0xADDR', normalized)
        normalized = re.sub(r'/[\w/.\-]+', '/PATH', normalized)
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}', 'TIMESTAMP', normalized)

        return hashlib.md5(normalized.encode()).hexdigest()

    def _format_plan(self, plan: dict) -> str:
        """Format a plan dict as readable markdown."""
        lines = []
        lines.append(f"## {plan.get('title', 'Analysis Plan')}")
        lines.append("")
        lines.append(f"**Image:** `{plan.get('base_image', 'python-general')}`")

        extra = plan.get("extra_packages", [])
        if extra:
            lines.append(f"**Extra packages:** {', '.join(extra)}")

        skill_ref = plan.get("skill_reference")
        if skill_ref:
            lines.append(f"**Based on skill:** `{skill_ref}`")

        datasets = plan.get("datasets", [])
        if datasets:
            ds_list = []
            for d in datasets:
                if isinstance(d, dict):
                    ds_list.append(f"{d.get('id', '?')} — {d.get('description', '')}")
                else:
                    ds_list.append(str(d))
            lines.append(f"**Datasets:** {'; '.join(ds_list)}")

        lines.append(f"**Language:** {plan.get('language', 'python')}")
        lines.append(f"**Est. runtime:** ~{plan.get('estimated_runtime_minutes', '?')} min")
        lines.append("")
        lines.append("### Steps")

        for step in plan.get("steps", []):
            lines.append(f"{step.get('step', '?')}. **{step.get('title', '')}**")
            lines.append(f"   {step.get('description', '')}")
            if step.get("expected_output"):
                lines.append(f"   → _{step['expected_output']}_")
            lines.append("")

        expected = plan.get("expected_results", [])
        if expected:
            lines.append("### Expected outputs")
            for e in expected:
                lines.append(f"- {e}")

        return "\n".join(lines)
