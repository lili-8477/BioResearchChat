"""Docker execution layer — run scripts in containers with automatic dependency installation."""

import asyncio
import re
import threading
import uuid
from pathlib import Path

import docker

from config import settings

# Python import name → pip package name (common mismatches in bioinformatics)
IMPORT_TO_PACKAGE = {
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "Bio": "biopython",
    "PIL": "Pillow",
    "yaml": "pyyaml",
    "bs4": "beautifulsoup4",
    "leidenalg": "leidenalg",
    "umap": "umap-learn",
    "fa2": "fa2",
    "magic": "magic-impute",
    "scvi": "scvi-tools",
    "cellpose": "cellpose",
    "squidpy": "squidpy",
    "celltypist": "celltypist",
    "anndata": "anndata",
    "scanpy": "scanpy",
    "pydeseq2": "pydeseq2",
    "gseapy": "gseapy",
    "pybedtools": "pybedtools",
    "pysam": "pysam",
    "deeptools": "deeptools",
    "macs2": "macs2",
}

# Packages that must be installed with --no-deps to avoid pulling broken transitive
# dependencies (e.g., tiledb-vector-search fails to build from source in slim images).
NO_DEPS_PACKAGES = {"scimilarity"}

# Packages that should never be pip-installed at runtime because they're either
# pre-installed in base images or require special build tooling that isn't available.
# If missing, the user should switch to the correct base image instead.
SKIP_PACKAGES = {"tiledb-vector-search"}

# Packages that come with the Python stdlib — never try to pip install these
STDLIB_MODULES = {
    "os", "sys", "re", "json", "csv", "math", "random", "datetime", "time",
    "pathlib", "collections", "itertools", "functools", "typing", "io",
    "glob", "shutil", "tempfile", "subprocess", "multiprocessing", "threading",
    "logging", "warnings", "traceback", "copy", "pickle", "gzip", "zipfile",
    "tarfile", "hashlib", "base64", "string", "textwrap", "struct", "abc",
    "contextlib", "dataclasses", "enum", "statistics", "operator", "bisect",
    "heapq", "queue", "socket", "http", "urllib", "email", "html", "xml",
    "sqlite3", "argparse", "configparser", "pprint", "unittest", "inspect",
    "types", "platform", "signal", "locale", "decimal", "fractions",
}


def extract_requirements_comment(code: str) -> list[str]:
    """Extract packages from a # REQUIREMENTS: comment at the top of the script."""
    for line in code.splitlines()[:10]:
        line = line.strip()
        m = re.match(r'^#\s*REQUIREMENTS:\s*(.+)', line, re.IGNORECASE)
        if m:
            return [pkg.strip() for pkg in m.group(1).split() if pkg.strip()]
    return []


def extract_python_imports(code: str) -> list[str]:
    """Extract top-level package names from Python import statements."""
    imports = set()
    for line in code.splitlines():
        line = line.strip()
        # import foo / import foo.bar / import foo as f
        m = re.match(r'^import\s+([\w.]+)', line)
        if m:
            imports.add(m.group(1).split('.')[0])
        # from foo import bar / from foo.bar import baz
        m = re.match(r'^from\s+([\w.]+)\s+import', line)
        if m:
            imports.add(m.group(1).split('.')[0])
    # Remove stdlib
    imports -= STDLIB_MODULES
    return sorted(imports)


def extract_r_packages(code: str) -> list[str]:
    """Extract package names from R library() and require() calls."""
    packages = set()
    for m in re.finditer(r'(?:library|require)\s*\(\s*["\']?(\w+)["\']?\s*\)', code):
        packages.add(m.group(1))
    return sorted(packages)


def imports_to_pip_packages(imports: list[str]) -> list[str]:
    """Convert Python import names to pip package names."""
    packages = []
    for imp in imports:
        pkg = IMPORT_TO_PACKAGE.get(imp, imp)
        packages.append(pkg)
    return packages


def parse_missing_module(stderr: str) -> str | None:
    """Extract the missing module name from a ModuleNotFoundError or ImportError."""
    # ModuleNotFoundError: No module named 'foo'
    m = re.search(r"ModuleNotFoundError: No module named ['\"](\w+)['\"]", stderr)
    if m:
        return m.group(1)
    # ImportError: cannot import name 'bar' from 'foo'
    m = re.search(r"ImportError: cannot import name .+ from ['\"](\w+)['\"]", stderr)
    if m:
        return m.group(1)
    return None


def parse_missing_r_package(stderr: str) -> str | None:
    """Extract missing R package name from error output."""
    m = re.search(r"there is no package called ['\"](\w+)['\"]", stderr)
    if m:
        return m.group(1)
    return None


def build_setup_script(code: str, language: str, extra_requirements: list[str] | None = None) -> str:
    """Build a shell script that installs dependencies then runs the analysis.

    For Python: extracts imports, pip-installs missing ones, then runs the script.
    For R: extracts library() calls, installs missing ones, then runs the script.
    """
    extra_requirements = extra_requirements or []

    if language == "python":
        imports = extract_python_imports(code)
        pip_packages = imports_to_pip_packages(imports)
        # Also parse # REQUIREMENTS: comment from the code
        declared_requirements = extract_requirements_comment(code)
        # Merge all sources, remove packages that should be skipped
        all_packages = sorted(
            set(pip_packages + extra_requirements + declared_requirements) - SKIP_PACKAGES
        )

        if not all_packages:
            return "python /workspace/analysis.py"

        # Split into normal vs --no-deps packages
        normal_pkgs = [p for p in all_packages if p not in NO_DEPS_PACKAGES]
        no_deps_pkgs = [p for p in all_packages if p in NO_DEPS_PACKAGES]

        install_lines = []
        if normal_pkgs:
            install_lines.append(
                f"pip install --no-cache-dir --quiet {' '.join(normal_pkgs)} 2>&1 | tail -5 || true"
            )
        if no_deps_pkgs:
            install_lines.append(
                f"pip install --no-cache-dir --no-deps --quiet {' '.join(no_deps_pkgs)} 2>&1 | tail -5 || true"
            )
        install_cmd = "\n".join(install_lines)

        return f"""#!/bin/sh
set -e

echo "=== Installing dependencies ==="
{install_cmd}

echo "=== Running analysis ==="
python /workspace/analysis.py
"""
    else:
        # R
        packages = extract_r_packages(code)
        declared_requirements = extract_requirements_comment(code)
        all_packages = sorted(set(packages + extra_requirements + declared_requirements))

        if not all_packages:
            return "Rscript /workspace/analysis.R"

        # Build R install command — try CRAN first, then Bioconductor
        pkg_vector = ", ".join(f'"{p}"' for p in all_packages)
        return f"""#!/bin/sh
set -e

echo "=== Installing R dependencies ==="
R --no-save -e '
needed <- c({pkg_vector})
installed <- rownames(installed.packages())
missing <- setdiff(needed, installed)
if (length(missing) > 0) {{
  cat("Installing from CRAN:", paste(missing, collapse=", "), "\\n")
  install.packages(missing, repos="https://cran.r-project.org", quiet=TRUE)
  still_missing <- setdiff(missing, rownames(installed.packages()))
  if (length(still_missing) > 0) {{
    cat("Installing from Bioconductor:", paste(still_missing, collapse=", "), "\\n")
    if (!require("BiocManager", quietly=TRUE)) install.packages("BiocManager", repos="https://cran.r-project.org", quiet=TRUE)
    BiocManager::install(still_missing, ask=FALSE, quiet=TRUE)
  }}
}}
cat("All packages ready.\\n")
' 2>&1 | tail -10

echo "=== Running analysis ==="
Rscript /workspace/analysis.R
"""


class DockerExecutor:
    """Manages container lifecycle for running analysis scripts."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def _create_workspace(self, session_id: str) -> Path:
        """Create a workspace directory for a session."""
        workspace = settings.WORKSPACE_DIR / session_id
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "output").mkdir(exist_ok=True)
        return workspace

    async def run_script(
        self,
        image: str,
        code: str,
        language: str = "python",
        session_id: str | None = None,
        data_mounts: dict[str, str] | None = None,
        on_output: callable = None,
        extra_requirements: list[str] | None = None,
    ) -> dict:
        """Run a script in a Docker container with automatic dependency installation.

        The executor:
        1. Writes the analysis script to the workspace
        2. Generates a setup script that installs all imported packages
        3. Runs the setup script (install + execute) in the container
        4. Streams output back in real-time

        Args:
            image: Docker image tag
            code: Script content
            language: python or r
            session_id: Unique session ID (auto-generated if None)
            data_mounts: Additional volume mounts {host_path: container_path}
            on_output: Async callback for streaming output lines
            extra_requirements: Additional packages to install beyond what's in imports

        Returns:
            dict with exit_code, stdout, stderr, output_files
        """
        session_id = session_id or str(uuid.uuid4())
        workspace = self._create_workspace(session_id)

        # Write analysis script
        ext = "py" if language == "python" else "R"
        script_name = f"analysis.{ext}"
        script_path = workspace / script_name
        script_path.write_text(code)

        # Write setup script (handles dependency installation + execution)
        setup_script = build_setup_script(code, language, extra_requirements)
        setup_path = workspace / "setup.sh"
        setup_path.write_text(setup_script)

        # Build volume mounts
        volumes = {
            str(workspace): {"bind": "/workspace", "mode": "rw"},
        }

        # Mount all cached data directories (models, references, atlases, user)
        data_root = settings.DATA_CACHE_DIR.parent
        for subdir in ["user", "models", "references", "atlases"]:
            host_dir = data_root / subdir
            if host_dir.exists():
                volumes[str(host_dir.resolve())] = {"bind": f"/data/{subdir}", "mode": "ro"}

        if data_mounts:
            for host_path, container_path in data_mounts.items():
                volumes[host_path] = {"bind": container_path, "mode": "ro"}

        # Run the setup script which installs deps then runs analysis
        cmd = "sh /workspace/setup.sh"

        # Run container
        container = await asyncio.to_thread(
            self.client.containers.run,
            image,
            command=cmd,
            volumes=volumes,
            working_dir="/workspace",
            mem_limit=settings.CONTAINER_MEMORY_LIMIT,
            nano_cpus=settings.CONTAINER_CPU_LIMIT * 1_000_000_000,
            detach=True,
            remove=False,
        )

        # Stream output
        stdout_parts = []
        stderr_parts = []
        loop = asyncio.get_running_loop()
        stream_queue: asyncio.Queue[str | None] = asyncio.Queue()
        wait_task = None
        stream_done = False

        try:
            def _stream_logs():
                try:
                    for chunk in container.logs(stream=True, follow=True, timestamps=False):
                        line = chunk.decode("utf-8", errors="replace")
                        stdout_parts.append(line)
                        loop.call_soon_threadsafe(stream_queue.put_nowait, line)
                except Exception as exc:
                    stderr_parts.append(str(exc))
                finally:
                    loop.call_soon_threadsafe(stream_queue.put_nowait, None)

            threading.Thread(target=_stream_logs, daemon=True).start()
            wait_task = asyncio.create_task(
                asyncio.to_thread(container.wait, timeout=settings.EXECUTION_TIMEOUT_SECONDS)
            )

            while True:
                if wait_task.done() and stream_done and stream_queue.empty():
                    break
                try:
                    line = await asyncio.wait_for(stream_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if line is None:
                    stream_done = True
                    continue
                if on_output:
                    await on_output(line)

            result = await wait_task
            exit_code = result["StatusCode"]

            stderr_log = await asyncio.to_thread(
                lambda: container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
            )
            if stderr_log:
                stderr_parts.append(stderr_log)

        except Exception as e:
            exit_code = 1
            stderr_parts.append(str(e))
            if wait_task:
                wait_task.cancel()
            try:
                await asyncio.to_thread(container.kill)
            except Exception:
                pass
        finally:
            try:
                await asyncio.to_thread(container.remove)
            except Exception:
                pass

        # List output files
        output_dir = workspace / "output"
        output_files = []
        if output_dir.exists():
            for f in output_dir.rglob("*"):
                if f.is_file():
                    output_files.append(str(f.relative_to(workspace)))

        return {
            "exit_code": exit_code,
            "stdout": "".join(stdout_parts),
            "stderr": "".join(stderr_parts),
            "output_files": output_files,
            "workspace": str(workspace),
            "session_id": session_id,
        }

    async def install_and_retry(
        self,
        image: str,
        code: str,
        language: str,
        stderr: str,
        session_id: str,
        data_mounts: dict[str, str] | None = None,
        on_output: callable = None,
    ) -> dict | None:
        """Detect missing package from stderr, install it, and re-run.

        Returns new result dict if a missing package was found and installed,
        or None if the error wasn't a missing package.
        """
        if language == "python":
            missing = parse_missing_module(stderr)
            if not missing or missing in STDLIB_MODULES:
                return None
            pkg = IMPORT_TO_PACKAGE.get(missing, missing)
            if pkg in SKIP_PACKAGES:
                return None
            extra = [pkg]
        else:
            missing = parse_missing_r_package(stderr)
            if not missing:
                return None
            extra = [missing]

        # Re-run with the missing package added to extra_requirements
        return await self.run_script(
            image=image,
            code=code,
            language=language,
            session_id=session_id,
            data_mounts=data_mounts,
            on_output=on_output,
            extra_requirements=extra,
        )

    def cleanup_workspace(self, session_id: str):
        """Remove a session workspace."""
        import shutil
        workspace = settings.WORKSPACE_DIR / session_id
        if workspace.exists():
            shutil.rmtree(workspace)
