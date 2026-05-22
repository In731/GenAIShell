import os
from pathlib import Path
import fnmatch
from typing import List
from tools.base import tool
from utils.logging import logger

@tool
def create_file(file_path: str, content: str) -> str:
    """Creates a new file or overwrites an existing file with the provided content.
    
    Args:
        file_path: The absolute or relative system path of the target file.
        content: The text content to write into the file.
        
    Returns:
        A confirmation message on successful write, or an error description.
    """
    try:
        path = Path(file_path).resolve()
        # Create directories if they do not exist
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        msg = f"Successfully wrote file to: {path}"
        logger.info(msg)
        return msg
    except Exception as e:
        return f"Error creating file at {file_path}: {e}"

@tool
def search_files(pattern: str, directory: str = ".") -> str:
    """Recursively searches for files matching a filename wildcard pattern (e.g. '*.py' or '*log*').
    
    Args:
        pattern: Wildcard filename glob pattern (e.g. '*.txt').
        directory: Root directory path where the search starts. Defaults to current directory '.'.
        
    Returns:
        Formatted string containing all matching file paths, or a 'no files found' message.
    """
    try:
        search_dir = Path(directory).resolve()
        matches: List[str] = []
        
        for root, _, filenames in os.walk(search_dir):
            for filename in fnmatch.filter(filenames, pattern):
                full_path = Path(root) / filename
                # Express path relative to the search dir for clean display
                try:
                    rel_path = full_path.relative_to(search_dir)
                    matches.append(str(rel_path))
                except ValueError:
                    matches.append(str(full_path))

        if not matches:
            return f"No files matching pattern '{pattern}' found inside directory '{directory}'."
            
        matches.sort()
        # Return truncated list if excessive to prevent context windows blowing up
        if len(matches) > 100:
            truncated = matches[:100]
            return f"Found {len(matches)} files matching (showing first 100):\n" + "\n".join(truncated)
            
        return f"Found {len(matches)} files matching:\n" + "\n".join(matches)
    except Exception as e:
        return f"Error searching files in {directory}: {e}"

@tool
def get_file_summary(file_path: str) -> str:
    """Reads a text file and extracts a preview and metadata summary.
    
    Args:
        file_path: System file path to summarize.
        
    Returns:
        Structured string representation containing line counts, byte sizes, and content preview.
    """
    try:
        path = Path(file_path).resolve()
        if not path.exists():
            return f"Error: File at '{file_path}' does not exist."
            
        if path.is_dir():
            return f"Error: '{file_path}' is a directory, not a file."

        size_bytes = path.stat().st_size
        
        # Read contents safely (handles large files via preview bounds)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            
        line_count = len(lines)
        preview_limit = 20
        preview_text = "".join(lines[:preview_limit])
        
        summary = (
            f"--- File Metadata Summary ---\n"
            f"Path: {path}\n"
            f"Size: {size_bytes} bytes\n"
            f"Lines: {line_count}\n"
            f"--- Content Preview (First {preview_limit} lines) ---\n"
            f"{preview_text}"
        )
        
        if line_count > preview_limit:
            summary += f"\n... [Truncated: {line_count - preview_limit} lines omitted] ..."
            
        return summary
    except Exception as e:
        return f"Error reading file summary for {file_path}: {e}"
