import re
from enum import Enum
from typing import Tuple, List
from utils.logging import logger
from config.settings import settings

class SecurityLevel(Enum):
    SAFE = "safe"
    RISKY = "risky"
    BLOCKED = "blocked"

class CommandGuard:
    """Security engine validating, classifying, and sanitizing shell commands before run."""
    
    # 1. BLOCKED commands (never executed)
    BLOCKED_PATTERNS: List[re.Pattern] = [
        re.compile(r"\brm\s+-rf?\s+(?:/|\*|\.\*)\b", re.IGNORECASE),          # rm -rf / or rm -rf *
        re.compile(r"\bdel\s+(?:/s|/f|/q|\s)+\s*(?:c:\\?\*|c:\\windows|\*)\b", re.IGNORECASE), # del C:\* or C:\Windows
        re.compile(r"(?::\(\)\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:)", re.IGNORECASE),               # Fork bomb: :(){ :|:& };:
        re.compile(r"\bmkfs(?:\.[a-z0-9]+)?\b", re.IGNORECASE),              # Format file systems
        re.compile(r"\bdd\s+if=\b", re.IGNORECASE),                          # Raw copy sectors dd if=
        re.compile(r"\bFormat-Volume\b", re.IGNORECASE),                     # PowerShell format
        re.compile(r"\bchown\s+.*root\b", re.IGNORECASE),                    # Privilege theft
        re.compile(r"\bchmod\s+(?:-R\s+)?777\s+/\b", re.IGNORECASE),         # Open root permissions
        re.compile(r"\b(?:shutdown|reboot|init\s+0|poweroff)\b", re.IGNORECASE) # Forced shutdowns
    ]

    # 2. RISKY commands (requires confirmation)
    RISKY_PATTERNS: List[re.Pattern] = [
        re.compile(r"\b(?:rm|del|rmdir|rd|Remove-Item)\b", re.IGNORECASE),     # Deletion
        re.compile(r"\b(?:kill|taskkill|killall|Stop-Process)\b", re.IGNORECASE), # Terminating tasks
        re.compile(r"\b(?:sudo|runas|su|net\s+user|net\s+localgroup)\b", re.IGNORECASE), # Escalation / User Management
        re.compile(r"\b(?:curl|wget|Invoke-WebRequest|iwr)\b.*\|\s*(?:bash|sh|iex|powershell)\b", re.IGNORECASE), # Run remote scripts directly
        re.compile(r"\b(?:reg\s+(?:add|delete|import|export)|Set-ItemProperty)\b", re.IGNORECASE), # OS Registry manipulation
        re.compile(r"[>|>>]\s*[\w\.\-/\\_]+", re.IGNORECASE)                   # Redirect output (file overrides)
    ]

    @classmethod
    def sanitize_input(cls, command: str) -> str:
        """Sanitizes the command string, stripping null bytes and carriage returns."""
        if not command:
            return ""
        # Remove null bytes, Carriage returns, and strip leading/trailing spaces
        sanitized = command.replace("\x00", "").replace("\r", "").strip()
        return sanitized

    @classmethod
    def analyze_command(cls, command: str) -> Tuple[SecurityLevel, str]:
        """Inspects shell commands, matching against safety blocklists and risky groups.
        
        Returns:
            Tuple[SecurityLevel, explanation_string]
        """
        sanitized = cls.sanitize_input(command)
        
        if not sanitized:
            return SecurityLevel.SAFE, "Command is empty."

        # Rule 1: Check blocked patterns
        for pattern in cls.BLOCKED_PATTERNS:
            if pattern.search(sanitized):
                explanation = f"Command matches blocked destructive pattern: {pattern.pattern}"
                logger.warning(f"Blocked Command Intercepted: '{sanitized}' - Reason: {explanation}")
                return SecurityLevel.BLOCKED, explanation

        # Rule 2: Check recursive protection on root directories
        # Matches deletion or modifications targeting system roots / C: root / etc / system32
        root_targets = [
            r"/\b", r"c:\\\b", r"c:\\windows\b", r"/etc\b", r"/usr\b", r"/bin\b", r"/var\b"
        ]
        destructive_keywords = ["rm", "del", "remove-item", "rd", "rmdir"]
        has_dest_keyword = any(kw in sanitized.lower() for kw in destructive_keywords)
        
        if has_dest_keyword:
            for root_pat in root_targets:
                if re.search(root_pat, sanitized, re.IGNORECASE):
                    explanation = f"Dangerous system target directory detected: {root_pat}"
                    logger.warning(f"Blocked Command Intercepted (System Root Guard): '{sanitized}' - Reason: {explanation}")
                    return SecurityLevel.BLOCKED, explanation

        # Rule 3: Check risky patterns
        for pattern in cls.RISKY_PATTERNS:
            if pattern.search(sanitized):
                explanation = f"Command matches risky pattern: {pattern.pattern}"
                logger.debug(f"Risky Command Flagged: '{sanitized}' - Reason: {explanation}")
                return SecurityLevel.RISKY, explanation

        # If safe mode is globally enabled, upgrade SAFE commands to RISKY to ensure absolute user control
        if settings.safe_mode_enabled:
            return SecurityLevel.RISKY, "Global safe mode is enabled. All execution actions require validation."

        return SecurityLevel.SAFE, "Command is safe to execute."
