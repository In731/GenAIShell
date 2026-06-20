import asyncio
import sys
import os
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from config.settings import settings
from utils.logging import logger
from security.guardrails import CommandGuard, SecurityLevel

class ExecutionResult(BaseModel):
    """Encapsulates outcome details of an executed terminal subprocess command."""
    stdout: str = Field(default="")
    stderr: str = Field(default="")
    exit_code: Optional[int] = Field(default=None)
    timeout_reached: bool = Field(default=False)
    command_run: str = Field(default="")

class CommandExecutor:
    """Asynchronous secure execution engine for running system terminal operations."""

    def __init__(self, timeout: Optional[int] = None):
        self.timeout = timeout or settings.max_shell_timeout

    def _determine_shell(self) -> Dict[str, Any]:
        """Detects hosting operating system and prepares subprocess shell setup.
        
        Returns:
            Dict containing execution options like executable configuration.
        """
        options: Dict[str, Any] = {}
        if sys.platform == "win32":
            # Prefer PowerShell on Windows for high scalability and structured scripting
            # Bypass execution policy in case script execution is blocked on user machine
            options["executable"] = "powershell.exe"
            logger.debug("Windows host detected. Routing command through powershell.exe")
        else:
            # POSIX hosts use standard bash or shell
            options["executable"] = "/bin/bash" if os.path.exists("/bin/bash") else "/bin/sh"
            logger.debug(f"POSIX host detected. Routing command through {options['executable']}")
        return options

    async def execute(self, command: str) -> ExecutionResult:
        """Asynchronously executes a shell command, monitoring execution timeouts and outputs.
        
        Args:
            command: The command string to run in the terminal shell.
            
        Returns:
            ExecutionResult instance containing exit code, stdout, stderr, and metadata.
        """
        sanitized_command = CommandGuard.sanitize_input(command)
        
        # Double safety check (insurance policy in the execution engine)
        security_level, explanation = CommandGuard.analyze_command(sanitized_command)
        if security_level == SecurityLevel.BLOCKED:
            logger.error(f"Executor blocked malicious command run attempt: '{sanitized_command}'")
            return ExecutionResult(
                stdout="",
                stderr=f"Security Error: Command blocked by system guardrails. {explanation}",
                exit_code=-1,
                timeout_reached=False,
                command_run=sanitized_command
            )

        logger.info(f"Executing command: '{sanitized_command}' with timeout={self.timeout}s")
        if sys.platform == "win32":
            # On Windows, use create_subprocess_exec to safely launch PowerShell
            process = await asyncio.create_subprocess_exec(
                "powershell.exe",
                "-Command",
                sanitized_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        else:
            # On POSIX, use create_subprocess_shell with explicit bash/sh
            executable = "/bin/bash" if os.path.exists("/bin/bash") else "/bin/sh"
            process = await asyncio.create_subprocess_shell(
                sanitized_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                executable=executable
            )

        try:
            # Run within wait_for to prevent runaway background processes
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout
            )
            
            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = process.returncode
            
            logger.debug(f"Command execution completed. Exit Code: {exit_code}")
            
            return ExecutionResult(
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=exit_code,
                timeout_reached=False,
                command_run=sanitized_command
            )

        except asyncio.TimeoutError:
            logger.warning(f"Command timed out after {self.timeout} seconds. Initiating process termination.")
            
            # Clean process termination
            try:
                if sys.platform == "win32":
                    # On Windows, kill process tree via taskkill if possible
                    kill_cmd = f"taskkill /F /T /PID {process.pid}"
                    kill_proc = await asyncio.create_subprocess_shell(
                        kill_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await kill_proc.communicate()
                else:
                    process.terminate()
                    await process.wait()
            except Exception as kill_err:
                logger.error(f"Failed to cleanly terminate timed-out process {process.pid}: {kill_err}")
                try:
                    process.kill()
                except Exception:
                    pass

            return ExecutionResult(
                stdout="",
                stderr=f"Execution Error: Subprocess reached max execution timeout ({self.timeout}s) and was terminated.",
                exit_code=-1,
                timeout_reached=True,
                command_run=sanitized_command
            )
        except Exception as err:
            logger.error(f"Unexpected error running subprocess: {err}")
            return ExecutionResult(
                stdout="",
                stderr=f"Execution Error: Unexpected exception occurred: {err}",
                exit_code=-1,
                timeout_reached=False,
                command_run=sanitized_command
            )
