import subprocess
from tools.base import tool
from utils.logging import logger

@tool
def git_status() -> str:
    """Queries the current status of the Git repository tracking modifications, untracked files, and active branch details.
    
    Returns:
        Structured text containing standard output from 'git status', or error logs.
    """
    try:
        # Run git status in the current working directory
        result = subprocess.run(
            ["git", "status"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8"
        )
        if result.returncode != 0:
            if "not a git repository" in result.stderr.lower():
                return "Not a git repository. Initialize git first using 'git init'."
            return f"Error executing git status: {result.stderr}"
        return result.stdout
    except FileNotFoundError:
        return "Git is not installed or not found in the environment PATH."
    except Exception as e:
        return f"Unexpected error checking git status: {e}"

@tool
def git_commit(message: str) -> str:
    """Stages all local modifications (executes 'git add .') and commits them with an automated message.
    
    Args:
        message: The commit message description.
        
    Returns:
        A status string detailing the staged modifications and commit confirmation.
    """
    try:
        # 1. Run git add .
        add_result = subprocess.run(
            ["git", "add", "."],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8"
        )
        if add_result.returncode != 0:
            return f"Failed to stage files (git add .): {add_result.stderr}"
            
        # 2. Run git commit
        commit_result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8"
        )
        if commit_result.returncode != 0:
            if "nothing to commit" in commit_result.stdout.lower() or "nothing added to commit" in commit_result.stderr.lower():
                return "Commit aborted: No modifications detected to stage/commit."
            return f"Failed to complete commit: {commit_result.stderr}\nStdout: {commit_result.stdout}"
            
        logger.info(f"Successfully completed Git Commit: '{message}'")
        return f"Commit Successful!\n\nStdout:\n{commit_result.stdout}"
        
    except FileNotFoundError:
        return "Git is not installed or not found in the environment PATH."
    except Exception as e:
        return f"Unexpected error during git commit: {e}"
