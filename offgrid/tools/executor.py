"""
Tool executor: self-implemented per FLEX-1 fallback.
Provides read_file, write_file, run_bash, list_dir, git_commit, ssh_*.
Interface is fixed (RED-4: transparent to user).

Guardrails:
- Dangerous commands blocked (rm -rf, git push --force, drop database, etc.)
- Sensitive files auto-backed up before overwrite (.env, credentials.json, etc.)
- Write operations confined to project_root
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Deterministic tool execution layer. No LLM involved."""

    # ── Guardrails ──

    DANGEROUS_PATTERNS = [
        "rm -rf", "rm -r /", "rmdir /s",
        "git push --force", "git push -f",
        "git reset --hard",
        "drop database", "drop table", "truncate table",
        "format c:", "del /f /s /q",
        "> /dev/null", "mkfs",
    ]

    PROTECTED_FILES = [
        ".env", ".env.local", ".env.production",
        "credentials.json", "secrets.yaml", "id_rsa",
        ".ssh/", "token.json", "service_account.json",
    ]

    def __init__(self, project_root: str = "."):
        self.project_root = os.path.abspath(project_root)
        self._ssh_session = None  # Persistent SSH session

    def read_file(self, path: str) -> str:
        """Read file content. Path can be relative to project_root or absolute."""
        full = self._resolve(path)
        try:
            with open(full, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return f"[ERROR] File not found: {full}"
        except Exception as e:
            return f"[ERROR] Read failed: {e}"

    def write_file(self, path: str, content: str) -> bool:
        """Write content to file. Guardrails: backs up sensitive files, confines to project_root."""
        full = self._resolve(path)

        # Guardrail: prevent writing outside project root
        if not full.startswith(self.project_root):
            logger.warning("[guardrail] Blocked write outside project: %s", full)
            return False

        # Guardrail: sensitive files get backed up before overwrite (not blocked)
        if self._is_protected(full) and os.path.isfile(full):
            backup_path = full + ".bak"
            try:
                import shutil
                shutil.copy2(full, backup_path)
                logger.info("[guardrail] Backed up sensitive file: %s → %s", full, backup_path)
            except Exception as e:
                logger.warning("[guardrail] Failed to backup %s: %s", full, e)

        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("Wrote %d bytes to %s", len(content), full)
            return True
        except Exception as e:
            logger.error("Write failed: %s", e)
            return False

    def run_bash(self, command: str, cwd: Optional[str] = None, timeout: int = 60) -> tuple[str, str, int]:
        """
        Run a shell command. Returns (stdout, stderr, returncode).
        Guardrails: blocks dangerous commands.
        """
        # Guardrail: check for dangerous patterns
        blocked = self._check_dangerous(command)
        if blocked:
            logger.warning("[guardrail] Blocked dangerous command: %s", command[:80])
            return "", f"[BLOCKED] 危险操作被拦截: {blocked}。如需执行请手动在终端运行。", -2

        work_dir = cwd or self.project_root
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=work_dir,
                capture_output=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", f"[ERROR] Command timed out after {timeout}s", -1
        except Exception as e:
            return "", f"[ERROR] {e}", -1

    def list_dir(self, path: str = ".") -> list[str]:
        """List directory contents. Returns sorted list of names."""
        full = self._resolve(path)
        try:
            entries = os.listdir(full)
            return sorted(entries)
        except FileNotFoundError:
            return [f"[ERROR] Directory not found: {full}"]
        except Exception as e:
            return [f"[ERROR] {e}"]

    def git_commit(self, message: str, cwd: Optional[str] = None) -> bool:
        """Stage all changes and commit."""
        work_dir = cwd or self.project_root
        _, err1, rc1 = self.run_bash("git add -A", cwd=work_dir)
        if rc1 != 0:
            logger.error("git add failed: %s", err1)
            return False
        _, err2, rc2 = self.run_bash(f'git commit -m "{message}"', cwd=work_dir)
        if rc2 != 0:
            logger.error("git commit failed: %s", err2)
            return False
        return True

    def get_file_tree(self, path: str = ".", max_depth: int = 3, max_files: int = 200) -> str:
        """Generate a file tree string for Locator context injection."""
        root = self._resolve(path)
        lines = []
        count = 0
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip hidden dirs and common noise
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d not in ("node_modules", "__pycache__", ".git", "venv", ".venv")
            ]
            depth = dirpath.replace(root, "").count(os.sep)
            if depth >= max_depth:
                dirnames.clear()
                continue
            indent = "  " * depth
            dirname = os.path.basename(dirpath)
            if depth > 0:
                lines.append(f"{indent}{dirname}/")
            for fname in sorted(filenames):
                if count >= max_files:
                    lines.append(f"{indent}  ... (truncated at {max_files} files)")
                    return "\n".join(lines)
                lines.append(f"{indent}  {fname}")
                count += 1
        return "\n".join(lines)

    def _resolve(self, path: str) -> str:
        """Resolve path relative to project_root."""
        if os.path.isabs(path):
            return os.path.normpath(path)
        return os.path.normpath(os.path.join(self.project_root, path))

    def apply_patch(self, file_path: str, original: str, modified: str) -> bool:
        """Apply a text replacement patch. Exact match only — original is read from file."""
        if not original:
            logger.warning("apply_patch called with empty original, use write_file for new files")
            return False
        full = self._resolve(file_path)
        try:
            content = self.read_file(file_path)
            if content.startswith("[ERROR]"):
                return False
            if original not in content:
                logger.warning("Original text not found in %s", full)
                return False
            new_content = content.replace(original, modified, 1)
            return self.write_file(file_path, new_content)
        except Exception as e:
            logger.error("Patch apply failed: %s", e)
            return False

    def _check_dangerous(self, command: str) -> Optional[str]:
        """Check if command matches dangerous patterns. Returns matched pattern or None."""
        cmd_lower = command.lower().strip()
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern in cmd_lower:
                return pattern
        return None

    def _is_protected(self, full_path: str) -> bool:
        """Check if file path matches protected patterns."""
        path_lower = full_path.lower().replace("\\", "/")
        for protected in self.PROTECTED_FILES:
            if protected in path_lower:
                return True
        return False

    # ── SSH Session (persistent, paramiko) ──

    def ssh_connect(
        self,
        host: str,
        port: int = 22,
        username: str = "root",
        password: Optional[str] = None,
        key_path: Optional[str] = None,
    ) -> tuple[bool, str]:
        """建立持久 SSH 连接。后续用 ssh_exec 执行命令。"""
        from offgrid.tools.ssh_session import SSHSession

        # 关闭旧连接
        if self._ssh_session and self._ssh_session.connected:
            self._ssh_session.close()

        self._ssh_session = SSHSession(
            host=host, port=port, username=username,
            password=password, key_path=key_path,
        )
        return self._ssh_session.connect()

    def ssh_exec(self, command: str, timeout: float = 60.0) -> tuple[str, str, int]:
        """在远程 SSH 会话中执行命令。返回 (stdout, stderr, returncode)。"""
        if not self._ssh_session or not self._ssh_session.connected:
            return "", "[ERROR] SSH未连接，请先用 ssh_connect 建立连接", -1

        # Guardrail: 远程也拦截危险命令
        blocked = self._check_dangerous(command)
        if blocked:
            logger.warning("[guardrail] Blocked dangerous SSH command: %s", command[:80])
            return "", f"[BLOCKED] 远程危险操作被拦截: {blocked}", -2

        result = self._ssh_session.exec(command, timeout=timeout)
        return result["stdout"], result["stderr"], result["returncode"]

    def ssh_upload(self, local_path: str, remote_path: str) -> tuple[bool, str]:
        """上传本地文件到远程 SSH 服务器。"""
        if not self._ssh_session or not self._ssh_session.connected:
            return False, "SSH未连接"
        full_local = self._resolve(local_path)
        return self._ssh_session.upload(full_local, remote_path)

    def ssh_download(self, remote_path: str, local_path: str) -> tuple[bool, str]:
        """从远程 SSH 服务器下载文件到本地。"""
        if not self._ssh_session or not self._ssh_session.connected:
            return False, "SSH未连接"
        full_local = self._resolve(local_path)
        return self._ssh_session.download(remote_path, full_local)

    def ssh_close(self) -> str:
        """关闭 SSH 连接。"""
        if self._ssh_session:
            self._ssh_session.close()
            self._ssh_session = None
            return "SSH连接已关闭"
        return "无活跃SSH连接"

    @property
    def ssh_connected(self) -> bool:
        """检查 SSH 是否已连接。"""
        return bool(self._ssh_session and self._ssh_session.connected)
