import pytest
import os
import json
from pathlib import Path

from app.tools.registry import registry
from app.tools.file_tool import list_files, read_file, ALLOWED_BASE_DIR
from app.tools.project_tool import get_project_info
from app.tools.calculator_tool import calculate

def test_tool_registration():
    tools = registry.get_all_tools()
    tool_names = [t.__name__ for t in tools]
    
    assert "list_files" in tool_names
    assert "read_file" in tool_names
    assert "get_project_info" in tool_names
    assert "calculate" in tool_names

def test_tool_discovery():
    tool = registry.get_tool("calculate")
    assert tool is not None
    assert tool.__name__ == "calculate"

def test_calculator_valid():
    tool = registry.get_tool("calculate")
    # The registry wraps the function to return a JSON string
    result_str = tool("2 + 3 * 4")
    result = json.loads(result_str)
    assert result["status"] == "success"
    assert result["result"] == 14

def test_calculator_invalid_input():
    tool = registry.get_tool("calculate")
    result_str = tool("2 + abc")
    result = json.loads(result_str)
    assert result["status"] == "error"

def test_calculator_errors():
    tool = registry.get_tool("calculate")
    # Division by zero
    result_str = tool("10 / 0")
    result = json.loads(result_str)
    assert result["status"] == "error"
    assert "Division by zero" in result["error"]
    
    # Unsafe operation
    result_str = tool("__import__('os').system('echo hello')")
    result = json.loads(result_str)
    assert result["status"] == "error"

def test_file_tool_valid():
    tool = registry.get_tool("list_files")
    result_str = tool(".")
    result = json.loads(result_str)
    assert result["status"] == "success"
    assert isinstance(result["result"], list)

def test_file_tool_missing_file():
    tool = registry.get_tool("read_file")
    result_str = tool("does_not_exist.txt")
    result = json.loads(result_str)
    assert result["status"] == "error"
    assert "File not found" in result["error"]

def test_file_tool_path_traversal():
    tool = registry.get_tool("read_file")
    # Attempt path traversal
    result_str = tool("../../../windows/win.ini")
    result = json.loads(result_str)
    assert result["status"] == "error"
    assert "Access denied" in result["error"]

def test_project_tool():
    tool = registry.get_tool("get_project_info")
    result_str = tool()
    result = json.loads(result_str)
    assert result["status"] == "success"
    assert "project_root_name" in result["result"]
    assert "important_files_found" in result["result"]

def test_registry_confirmation_metadata():
    # Existing tools should default to False
    assert registry.requires_confirmation("calculate") is False
    assert registry.requires_confirmation("list_files") is False
    
    # Register a mock sensitive tool
    @registry.register(name="delete_database", requires_confirmation=True)
    def mock_delete_db() -> str:
        return "Deleted"
        
    # Check that metadata is correctly exposed
    assert registry.requires_confirmation("delete_database") is True
    
    # Ensure it's in the tool list
    tool_names = [t.__name__ for t in registry.get_all_tools()]
    assert "mock_delete_db" in tool_names
    
    # Ensure tool still executes if called directly
    tool = registry.get_tool("delete_database")
    res = json.loads(tool())
    assert res["status"] == "success"
    assert res["result"] == "Deleted"
