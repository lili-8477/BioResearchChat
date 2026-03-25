"""Main agent orchestrator — coordinates the full analysis loop."""

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncGenerator

from agent.paper_parser import parse_url
from agent.planner import generate_plan
from agent.code_writer import generate_code, fix_code
from agent.evaluator import evaluate_output
from agent.image_resolver import resolve_image
from data.api import DataAPI
from container_runtime.executor import DockerExecutor
from skills.manager import SkillManager
from memory.manager import MemoryManager
from agent.analysis_log import write_analysis_log


class SessionState(str, Enum):
    IDLE = "idle"
    CONVERSING = "conversing"
    PARSING = "parsing"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    RESOLVING_ENV = "resolving_env"
    WRITING_CODE = "writing_code"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


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

    def add_message(self, role: str, content: str, msg_type: str = "text", data: dict = None) -> Message:
        msg = Message(role=role, content=content, msg_type=msg_type, data=data or {})
        self.messages.append(msg)
        return msg


class Orchestrator:
    """Coordinates the agent loop: parse → plan → code → execute → evaluate.

    Integrates skills (pipeline templates) and memory (lessons) throughout.
    """

    def __init__(self):
        self.sessions: dict[str, Session] = {}
        self.executor = DockerExecutor()
        self.data_api = DataAPI()
        self.skill_manager = SkillManager()
        self.memory_manager = MemoryManager()

    def create_session(self) -> Session:
        session_id = str(uuid.uuid4())
        session = Session(id=session_id)
        self.sessions[session_id] = session
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
            session = self.create_session()
            session.id = session_id

        session.add_message("user", content)

        # If user is approving a plan
        if session.state == SessionState.AWAITING_APPROVAL:
            if content.lower() in ("approve", "yes", "go", "run", "execute", "ok"):
                async for msg in self._execute_plan(session):
                    yield msg
                return
            elif content.lower() in ("reject", "no", "cancel"):
                session.state = SessionState.IDLE
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

        # If we're in a conversation, continue guiding the user
        if session.state == SessionState.CONVERSING:
            # Check if user now has enough context to start analysis
            if paper_url or self._is_analysis_ready(session, content):
                async for msg in self._start_analysis(session, content, paper_url):
                    yield msg
            else:
                async for msg in self._converse(session, content):
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

    async def _converse(
        self,
        session: Session,
        content: str,
    ) -> AsyncGenerator[Message, None]:
        """Guide the user to clarify their request before starting analysis."""
        session.state = SessionState.CONVERSING
        content_lower = content.lower().strip()

        # Build a helpful response based on what's missing
        # Check what we know so far from conversation history
        has_data = any(
            re.search(r'GSE\d+|GSM\d+|SRR\d+|PRJNA\d+|TCGA|\.h5ad|\.csv|\.fastq', m.content, re.IGNORECASE)
            for m in session.messages if m.role == "user"
        )
        has_analysis_type = any(
            re.search(r'differential|clustering|enrichment|peak|trajectory|heatmap|expression', m.content, re.IGNORECASE)
            for m in session.messages if m.role == "user"
        )

        # Simple greetings
        greetings = ['hi', 'hello', 'hey', 'help', 'what can you do']
        if any(content_lower.startswith(g) for g in greetings) or content_lower in greetings:
            yield session.add_message(
                "assistant",
                "Hi! I'm a bioinformatics research agent. I can help you:\n\n"
                "- **Analyze a paper** — paste a paper URL and I'll extract the methods and reproduce the analysis\n"
                "- **Run an analysis** — describe what you want to do (e.g., \"Run DESeq2 differential expression on GSE12345\")\n"
                "- **Explore data** — tell me about your dataset and research question\n\n"
                "What would you like to work on?",
            )
            return

        # User asked something but it's vague
        response_parts = ["I'd like to help! To set up the right analysis, could you tell me:\n"]

        if not has_data:
            response_parts.append(
                "- **What data** are you working with? (e.g., a GEO accession like GSE12345, "
                "a file path, or a paper URL)"
            )
        if not has_analysis_type:
            response_parts.append(
                "- **What analysis** do you want to run? (e.g., differential expression, "
                "clustering, peak calling, trajectory analysis)"
            )

        if not has_data and not has_analysis_type:
            response_parts.append(
                "\nOr simply paste a **paper URL** and I'll extract the methods automatically."
            )

        yield session.add_message("assistant", "\n".join(response_parts))

    async def _start_analysis(
        self,
        session: Session,
        question: str,
        paper_url: str | None = None,
    ) -> AsyncGenerator[Message, None]:
        """Start a new analysis: parse paper → generate plan."""

        # Step 1: Parse paper from URL
        if paper_url:
            session.state = SessionState.PARSING
            yield session.add_message("assistant", f"Parsing paper from {paper_url}...", msg_type="system")

            try:
                session.paper_info = await parse_url(paper_url)
                yield session.add_message(
                    "assistant",
                    f"Paper parsed: {session.paper_info.get('summary', 'Analysis extracted')}",
                    msg_type="text",
                    data=session.paper_info,
                )
            except Exception as e:
                session.state = SessionState.FAILED
                yield session.add_message("assistant", f"Failed to parse paper: {e}", msg_type="error")
                return
        elif not session.paper_info:
            session.paper_info = {
                "analysis_type": "general",
                "methods": [],
                "packages": [],
                "language": "python",
                "datasets": [],
                "key_parameters": {},
                "summary": question,
            }

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
        session.state = SessionState.PLANNING
        yield session.add_message("assistant", "Generating analysis plan...", msg_type="system")

        try:
            # Pass lightweight skill registry (no code templates) to planner
            session.plan = await generate_plan(
                session.paper_info, question,
                skills=skills,
                lessons=lessons,
            )
            session.state = SessionState.AWAITING_APPROVAL

            plan_text = self._format_plan(session.plan)
            yield session.add_message("assistant", plan_text, msg_type="plan", data=session.plan)
            yield session.add_message(
                "assistant",
                "Review the plan above. Reply **approve** to execute, or describe changes you'd like.",
                msg_type="system",
            )
        except Exception as e:
            session.state = SessionState.FAILED
            yield session.add_message("assistant", f"Failed to generate plan: {e}", msg_type="error")

    async def _replan(self, session: Session, modifications: str) -> AsyncGenerator[Message, None]:
        """Regenerate plan with user modifications."""
        session.state = SessionState.PLANNING
        yield session.add_message("assistant", "Updating plan with your feedback...", msg_type="system")

        modified_question = (
            f"Original question: {session.messages[0].content if session.messages else ''}\n\n"
            f"User modifications: {modifications}"
        )

        skills = self._find_skill_registry(modified_question, session.paper_info)
        lessons = self._find_lessons(modified_question, session.paper_info)

        try:
            session.plan = await generate_plan(
                session.paper_info, modified_question,
                skills=skills, lessons=lessons,
            )
            session.state = SessionState.AWAITING_APPROVAL

            plan_text = self._format_plan(session.plan)
            yield session.add_message("assistant", plan_text, msg_type="plan", data=session.plan)
            yield session.add_message(
                "assistant",
                "Updated plan ready. Reply **approve** to execute, or describe more changes.",
                msg_type="system",
            )
        except Exception as e:
            session.state = SessionState.FAILED
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
        session.state = SessionState.RESOLVING_ENV
        yield session.add_message("assistant", "Setting up execution environment...", msg_type="system")

        try:
            base_image = plan.get("base_image", "python-general")
            extra_packages = plan.get("extra_packages", [])
            image_tag = await resolve_image(base_image, extra_packages)
            yield session.add_message("assistant", f"Using image: `{image_tag}`", msg_type="system")
        except Exception as e:
            session.state = SessionState.FAILED
            yield session.add_message("assistant", f"Environment setup failed: {e}", msg_type="error")
            return

        # Step 4: Mount data
        data_mounts = {}
        dataset_ids = [d["id"] if isinstance(d, dict) else d for d in plan.get("datasets", [])]
        if dataset_ids:
            yield session.add_message("assistant", f"Mounting datasets: {', '.join(dataset_ids)}", msg_type="system")
            try:
                data_mounts = await self.data_api.mount_datasets(dataset_ids)
            except Exception as e:
                yield session.add_message("assistant", f"Warning: Dataset mount failed: {e}", msg_type="error")

        # Step 5: Write code (with single skill content + lessons)
        session.state = SessionState.WRITING_CODE
        yield session.add_message("assistant", "Writing analysis code...", msg_type="system")

        language = plan.get("language", "python")
        try:
            session.code = await generate_code(plan, language, skill_content=skill_content, lessons=lessons)
            yield session.add_message("assistant", session.code, msg_type="code", data={"language": language})
        except Exception as e:
            session.state = SessionState.FAILED
            yield session.add_message("assistant", f"Code generation failed: {e}", msg_type="error")
            return

        # Step 6-8: Execute and evaluate loop
        session.retry_count = 0
        while session.retry_count <= session.max_retries:
            session.state = SessionState.EXECUTING
            attempt = session.retry_count + 1
            if attempt > 1:
                yield session.add_message("assistant", f"Retry attempt {attempt}/{session.max_retries + 1}...", msg_type="system")
            else:
                yield session.add_message("assistant", "Executing analysis...", msg_type="system")

            output_lines = []

            async def on_output(line: str):
                output_lines.append(line)

            try:
                result = await self.executor.run_script(
                    image=image_tag,
                    code=session.code,
                    language=language,
                    session_id=session.id,
                    data_mounts=data_mounts,
                    on_output=on_output,
                )
            except Exception as e:
                session.state = SessionState.FAILED
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
            session.state = SessionState.EVALUATING
            yield session.add_message("assistant", "Evaluating results...", msg_type="system")

            evaluation = await evaluate_output(
                stdout=result["stdout"],
                stderr=result["stderr"],
                exit_code=result["exit_code"],
                output_files=result["output_files"],
                plan=plan,
            )

            if evaluation.get("success"):
                session.state = SessionState.COMPLETED
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
            session.retry_count += 1
            if session.retry_count > session.max_retries:
                session.state = SessionState.FAILED
                yield session.add_message(
                    "assistant",
                    f"Analysis failed after {session.max_retries + 1} attempts.\n\n"
                    f"Last error: {evaluation.get('suggestion', 'Unknown error')}\n\n"
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
            yield session.add_message("assistant", f"Fixing code: {evaluation.get('suggestion', '')}", msg_type="system")
            error_text = result["stderr"] or result["stdout"]
            try:
                session.code = await fix_code(session.code, error_text, plan, language, lessons=lessons)
                yield session.add_message("assistant", session.code, msg_type="code", data={"language": language})
            except Exception as e:
                session.state = SessionState.FAILED
                yield session.add_message("assistant", f"Code fix failed: {e}", msg_type="error")
                return

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
