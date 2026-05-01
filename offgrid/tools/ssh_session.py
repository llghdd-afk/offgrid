"""
SSH Session Manager: paramiko 持久 SSH 连接。
支持多轮命令交互，不需要每次重新连接。

用法：
  session = SSHSession("183.222.230.89", port=22102, username="linux", password="E5#ok")
  session.connect()
  stdout = session.exec("ls /app")
  stdout = session.exec("cd /app && cat config.yml")
  session.close()

集成到 ToolExecutor：
  executor.ssh_connect(host, port, username, password)
  executor.ssh_exec("systemctl status nginx")
  executor.ssh_close()
"""

import logging
import time
from typing import Optional

import paramiko

logger = logging.getLogger(__name__)


class SSHSession:
    """持久 SSH 会话，基于 paramiko。"""

    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str = "root",
        password: Optional[str] = None,
        key_path: Optional[str] = None,
        timeout: float = 10.0,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_path = key_path
        self.timeout = timeout
        self._client: Optional[paramiko.SSHClient] = None
        self._connected = False

    @property
    def connected(self) -> bool:
        """检查连接是否存活。"""
        if not self._client or not self._connected:
            return False
        try:
            transport = self._client.get_transport()
            return transport is not None and transport.is_active()
        except Exception:
            return False

    def connect(self) -> tuple[bool, str]:
        """
        建立 SSH 连接。
        返回 (success, message)。
        """
        try:
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs = {
                "hostname": self.host,
                "port": self.port,
                "username": self.username,
                "timeout": self.timeout,
            }

            if self.key_path:
                connect_kwargs["key_filename"] = self.key_path
            elif self.password:
                connect_kwargs["password"] = self.password

            self._client.connect(**connect_kwargs)
            self._connected = True
            logger.info("[ssh] Connected to %s@%s:%d", self.username, self.host, self.port)
            return True, f"已连接 {self.username}@{self.host}:{self.port}"

        except paramiko.AuthenticationException:
            self._connected = False
            msg = f"认证失败：{self.username}@{self.host}:{self.port}"
            logger.error("[ssh] %s", msg)
            return False, msg
        except paramiko.SSHException as e:
            self._connected = False
            msg = f"SSH错误：{e}"
            logger.error("[ssh] %s", msg)
            return False, msg
        except Exception as e:
            self._connected = False
            msg = f"连接失败：{e}"
            logger.error("[ssh] %s", msg)
            return False, msg

    def exec(self, command: str, timeout: float = 60.0) -> dict:
        """
        在远程执行命令。
        返回 {"stdout": str, "stderr": str, "returncode": int, "elapsed": float}
        """
        if not self.connected:
            return {
                "stdout": "",
                "stderr": "[ERROR] SSH未连接，请先执行 ssh_connect",
                "returncode": -1,
                "elapsed": 0.0,
            }

        t0 = time.time()
        try:
            stdin, stdout, stderr = self._client.exec_command(
                command, timeout=timeout
            )
            # 等待命令完成
            exit_code = stdout.channel.recv_exit_status()
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            elapsed = time.time() - t0

            logger.info("[ssh] exec '%s' → rc=%d (%.1fs)", command[:60], exit_code, elapsed)
            return {
                "stdout": out,
                "stderr": err,
                "returncode": exit_code,
                "elapsed": elapsed,
            }

        except Exception as e:
            elapsed = time.time() - t0
            logger.error("[ssh] exec failed: %s", e)
            return {
                "stdout": "",
                "stderr": f"[ERROR] {e}",
                "returncode": -1,
                "elapsed": elapsed,
            }

    def upload(self, local_path: str, remote_path: str) -> tuple[bool, str]:
        """上传文件到远程。"""
        if not self.connected:
            return False, "SSH未连接"
        try:
            sftp = self._client.open_sftp()
            sftp.put(local_path, remote_path)
            sftp.close()
            logger.info("[ssh] Uploaded %s → %s", local_path, remote_path)
            return True, f"已上传 {local_path} → {remote_path}"
        except Exception as e:
            return False, f"上传失败：{e}"

    def download(self, remote_path: str, local_path: str) -> tuple[bool, str]:
        """从远程下载文件。"""
        if not self.connected:
            return False, "SSH未连接"
        try:
            sftp = self._client.open_sftp()
            sftp.get(remote_path, local_path)
            sftp.close()
            logger.info("[ssh] Downloaded %s → %s", remote_path, local_path)
            return True, f"已下载 {remote_path} → {local_path}"
        except Exception as e:
            return False, f"下载失败：{e}"

    def close(self):
        """关闭连接。"""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._connected = False
            logger.info("[ssh] Connection closed")

    def __del__(self):
        self.close()

    def __repr__(self):
        status = "connected" if self.connected else "disconnected"
        return f"SSHSession({self.username}@{self.host}:{self.port}, {status})"
