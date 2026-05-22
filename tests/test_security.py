import pytest
from security.guardrails import CommandGuard, SecurityLevel
from config.settings import settings

def test_sanitize_input():
    """Verifies that null bytes and line returns are successfully stripped."""
    dirty_cmd = "echo 'hello'\x00\r"
    cleaned = CommandGuard.sanitize_input(dirty_cmd)
    assert cleaned == "echo 'hello'"

def test_blocked_commands():
    """Verifies that critical system-destruction commands are blocked."""
    blocked_commands = [
        "rm -rf /",
        "del /s /q c:\\*",
        ":(){ :|:& };:",
        "mkfs.ext4 /dev/sda",
        "dd if=/dev/zero of=/dev/sda",
        "shutdown -h now"
    ]
    for cmd in blocked_commands:
        sec_level, explanation = CommandGuard.analyze_command(cmd)
        assert sec_level == SecurityLevel.BLOCKED
        assert "blocked" in explanation.lower()

def test_system_root_directory_guard():
    """Verifies that deletion targeting system root folders is blocked."""
    dangerous_target_cmd = "rm -f /etc/hosts"
    sec_level, explanation = CommandGuard.analyze_command(dangerous_target_cmd)
    assert sec_level == SecurityLevel.BLOCKED
    assert "dangerous system target directory" in explanation.lower()

def test_risky_commands():
    """Verifies that commands like deletes, user creation, or port kills are classified as RISKY."""
    # Ensure safe mode is false for this specific check, otherwise everything is upgraded to risky
    settings.safe_mode_enabled = False
    
    risky_commands = [
        "rm file.txt",
        "taskkill /F /PID 1234",
        "sudo apt update",
        "echo 'data' > config.json",
        "reg delete HKLM\\Software"
    ]
    for cmd in risky_commands:
        sec_level, explanation = CommandGuard.analyze_command(cmd)
        assert sec_level == SecurityLevel.RISKY
        assert "risky" in explanation.lower()

def test_safe_mode_escalation():
    """Verifies that when settings.safe_mode_enabled is True, standard commands are upgraded to RISKY."""
    settings.safe_mode_enabled = True
    
    # Normally a safe read-only command
    cmd = "echo 'Hello World'"
    sec_level, explanation = CommandGuard.analyze_command(cmd)
    assert sec_level == SecurityLevel.RISKY
    assert "global safe mode is enabled" in explanation.lower()
