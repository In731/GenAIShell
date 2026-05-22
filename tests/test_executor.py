import pytest
import asyncio
import sys
from core.executor import CommandExecutor

pytestmark = pytest.mark.asyncio

async def test_execute_success():
    """Validates that a safe standard shell read command executes correctly and captures stdout."""
    executor = CommandExecutor()
    
    if sys.platform == "win32":
        cmd = "Write-Output 'Antigravity'"
    else:
        cmd = "echo 'Antigravity'"
        
    res = await executor.execute(cmd)
    
    assert res.exit_code == 0
    assert "Antigravity" in res.stdout
    assert not res.timeout_reached
    assert not res.stderr

async def test_execute_timeout():
    """Validates that a long-running runaway shell command is terminated when it reaches maximum timeout."""
    # Set timeout bounds extremely short for testing
    executor = CommandExecutor(timeout=1)
    
    if sys.platform == "win32":
        # Start-Sleep on PowerShell
        cmd = "Start-Sleep -Seconds 10"
    else:
        # standard sleep on POSIX
        cmd = "sleep 10"
        
    res = await executor.execute(cmd)
    
    assert res.exit_code == -1
    assert res.timeout_reached
    assert "terminated" in res.stderr.lower()
    assert not res.stdout
