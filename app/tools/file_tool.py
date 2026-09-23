import os
from pathlib import Path
from typing import List

from app.tools.registry import registry

# For safety, restrict file operations to the current working directory
ALLOWED_BASE_DIR = Path(os.getcwd()).resolve()

def _safe_resolve(relative_path: str) -> Path:
    """Resolves a path safely, preventing traversal outside the allowed base directory."""
    target_path = (ALLOWED_BASE_DIR / relative_path).resolve()
    
    # Check if the resolved path starts with the allowed base directory
    if not str(target_path).startswith(str(ALLOWED_BASE_DIR)):
        raise PermissionError(f"Access denied: Path '{relative_path}' is outside the allowed project directory.")
    
    return target_path

@registry.register()
def list_files(directory: str = ".") -> List[str]:
    """
    Lists files and directories in the specified project directory.
    Uses relative paths from the project root.
    
    Args:
        directory: The relative path to the directory to list. Defaults to the root ".".
    """
    target = _safe_resolve(directory)
    
    if not target.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")
    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {directory}")
        
    items = os.listdir(target)
    return items

@registry.register()
def read_file(filepath: str) -> str:
    """
    Reads the content of a text file from the project directory.
    
    Args:
        filepath: The relative path to the file to read.
    """
    target = _safe_resolve(filepath)
    
    if not target.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    if not target.is_file():
        raise IsADirectoryError(f"Path is a directory, not a file: {filepath}")
        
    try:
        with open(target, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        raise ValueError(f"Cannot read file '{filepath}': File is not valid UTF-8 text.")
