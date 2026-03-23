"""Main agent orchestrator — coordinates the full analysis loop."""

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncGenerator

from agent.paper_parser import parse_paper
from agent.planner import generate_plan
from agent.code_writer import generate_code, fix_code
from agent.evaluator import evaluate_output
from agent.image_resolver import resolve_image
from data.api import DataAPI
from container_runtime.executor import DockerExecutor
from skills.manager import SkillManager
from memory.manager import MemoryManager


class SessionState(str, Enum):
    IDLE = "idle"
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

    def _find_skills(self, question: str, paper_info: dict) -> list[dict]:
        """Search for relevant skills based on question and paper info."""
        analysis_type = paper_info.get("analysis_type", "")
        tags = paper_info.get("packages", []) + paper_info.get("methods", [])
        skills = self.skill_manager.search_skills(
            query=question,
            analysis_type=analysis_type,
            tags=tags,
            limit=3,
        )
        return [s.model_dump() for s in skills]

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
        pdf_path: str | None = None,
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
                yield session.add_message("assistant", "Plan rejected. Send a new question or upload a new paper.")
                return
            else:
                async for msg in self._replan(session, content):
                    yield msg
                return

        # Auto-detect URL in message
        if not pdf_path and not paper_url:
            url_match = re.search(r'https?://\S+', content)
            if url_match:
                paper_url = url_match.group(0).rstrip(".,;:!?)")

        async for msg in self._start_analysis(session, content, pdf_path, paper_url):
            yield msg

    async def _start_analysis(
        self,
        session: Session,
        question: str,
        pdf_path: str | None = None,
        paper_url: str | None = None,
    ) -> AsyncGenerator[Message, None]:
        """Start a new analysis: parse paper → generate plan."""

        # Step 1: Parse paper
        if pdf_path or paper_url:
            session.state = SessionState.PARSING
            source = paper_url or pdf_path
            yield session.add_message("assistant", f"Parsing paper from {source}...", msg_type="system")

            try:
                session.paper_info = await parse_paper(pdf_path=pdf_path, paper_url=paper_url)
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

        # Find relevant skills and lessons
        skills = self._find_skills(question, session.paper_info)
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

        # Step 2: Generate plan (with skills + lessons context)
        session.state = SessionState.PLANNING
        yield session.add_message("assistant", "Generating analysis plan...", msg_type="system")

        try:
            # Pass skill metadata (no code templates) and lessons to planner
            skill_meta = [{k: v for k, v in s.items() if k != "code_template"} for s in skills]
            session.plan = await generate_plan(
                session.paper_info, question,
                skills=skill_meta,
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

        skills = self._find_skills(modified_question, session.paper_info)
        lessons = self._find_lessons(modified_question, session.paper_info)
        skill_meta = [{k: v for k, v in s.items() if k != "code_template"} for s in skills]

        try:
            session.plan = await generate_plan(
                session.paper_info, modified_question,
                skills=skill_meta, lessons=lessons,
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

        # Search skills with full code templates for code generation
        question = session.messages[0].content if session.messages else ""
        skills = self._find_skills(question, session.paper_info)
        lessons = self._find_lessons(question, session.paper_info)

        # Refine skill search using plan's analysis type / image
        plan_type = plan.get("base_image", "").replace("python-", "").replace("r-", "")
        if plan_type:
            type_skills = self.skill_manager.search_skills(
                query=plan.get("title", ""),
                analysis_type=plan_type,
                limit=2,
            )
            # Merge, dedup by name
            seen = {s["name"] for s in skills}
            for s in type_skills:
                d = s.model_dump()
                if d["name"] not in seen:
                    skills.append(d)

        # Also check if the plan references a specific skill
        skill_ref = plan.get("skill_reference")
        if skill_ref:
            ref_skill = self.skill_manager.get_skill(skill_ref)
            if ref_skill:
                ref_dict = ref_skill.model_dump()
                if ref_dict["name"] not in {s["name"] for s in skills}:
                    skills.insert(0, ref_dict)

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

        # Step 5: Write code (with skills + lessons)
        session.state = SessionState.WRITING_CODE
        yield session.add_message("assistant", "Writing analysis code...", msg_type="system")

        language = plan.get("language", "python")
        try:
            session.code = await generate_code(plan, language, skills=skills, lessons=lessons)
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
                    pass  # Lesson extraction failure shouldn't block results

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
