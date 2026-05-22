import sys
import subprocess
import re
from typing import Optional
from tools.base import tool
from utils.logging import logger

@tool
def list_active_processes(limit: int = 15) -> str:
    """Lists currently active operating system processes.
    
    Args:
        limit: Max number of process rows to print. Defaults to 15.
        
    Returns:
        Structured table string listing processes running on the machine.
    """
    try:
        if sys.platform == "win32":
            # Run tasklist on Windows
            cmd = ["tasklist"]
        else:
            # POSIX hosts use standard ps
            cmd = ["ps", "-ef"]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace"
        )
        
        if result.returncode != 0:
            return f"Failed to retrieve processes: {result.stderr}"

        lines = result.stdout.strip().split("\n")
        
        if len(lines) <= limit + 2:
            return "\n".join(lines)
            
        # Preview header + limited entries
        header = lines[:3]
        entries = lines[3:3 + limit]
        
        return (
            "\n".join(header) + "\n" +
            "\n".join(entries) + "\n" +
            f"... [Truncated: {len(lines) - 3 - limit} processes remaining] ..."
        )
    except Exception as e:
        return f"Error listing active processes: {e}"

@tool
def kill_process_by_port(port: int) -> str:
    """Identifies and terminates any active OS process bound to a specific network port (e.g. 3000, 8080).
    
    Args:
        port: The network port integer.
        
    Returns:
        Confirmation status detailing the identified PID and kill confirmation, or search errors.
    """
    try:
        pid: Optional[int] = None
        
        if sys.platform == "win32":
            # 1. Run netstat to locate PID bound to port
            netstat_cmd = f"netstat -ano"
            netstat_run = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8"
            )
            
            # Look for lines containing ":port " and extract the trailing PID digit
            pattern = re.compile(rf":{port}\s+.*?\s+LISTENING\s+(\d+)", re.IGNORECASE)
            for line in netstat_run.stdout.split("\n"):
                match = pattern.search(line)
                if match:
                    pid = int(match.group(1))
                    break
                    
            if not pid:
                return f"No process identified bound to port {port}."

            # 2. Terminate the discovered PID
            kill_run = subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8"
            )
            if kill_run.returncode != 0:
                return f"Failed to terminate PID {pid} bound to port {port}: {kill_run.stderr}"
                
            return f"Successfully terminated PID {pid} listening on port {port}.\nOutput:\n{kill_run.stdout.strip()}"

        else:
            # Linux / macOS
            # 1. Locate process using lsof
            lsof_run = subprocess.run(
                ["lsof", "-t", f"-i:{port}"],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8"
            )
            
            pids_str = lsof_run.stdout.strip()
            if not pids_str:
                return f"No process identified bound to port {port}."
                
            # Extract first PID
            pid = int(pids_str.split("\n")[0])
            
            # 2. Terminate PID
            kill_run = subprocess.run(
                ["kill", "-9", str(pid)],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8"
            )
            if kill_run.returncode != 0:
                return f"Failed to terminate PID {pid} bound to port {port}: {kill_run.stderr}"
                
            return f"Successfully terminated PID {pid} listening on port {port}."

    except Exception as e:
        return f"Error executing kill process by port {port}: {e}"
