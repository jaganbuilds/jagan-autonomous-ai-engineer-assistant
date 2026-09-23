import os
from pathlib import Path
from typing import Dict, Any

from app.tools.registry import registry
from app.tools.file_tool import ALLOWED_BASE_DIR

@registry.register()
def get_project_info() -> Dict[str, Any]:
    """
    Identifies the current project and returns high-level project structure information.
    Detects important files like README.md, requirements.txt, and source directories.
    """
    base_dir = ALLOWED_BASE_DIR
    
    important_files = ['README.md', 'requirements.txt', 'setup.py', 'pyproject.toml', 'package.json', '.gitignore']
    detected_files = [f for f in important_files if (base_dir / f).is_file()]
    
    # Simple top-level directory scan to find source directories
    directories = [d.name for d in base_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
    
    # Check specifically for python package structures
    source_directories = [d for d in directories if (base_dir / d / '__init__.py').exists() or d in ['app', 'src', 'tests']]
    
    return {
        "project_root_name": base_dir.name,
        "important_files_found": detected_files,
        "source_directories": source_directories,
        "all_top_level_directories": directories
    }
