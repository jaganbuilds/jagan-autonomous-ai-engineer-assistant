from typing import Any, Callable, Dict, List
import inspect
import json
import logging

logger = logging.getLogger(__name__)

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._requires_confirmation: Dict[str, bool] = {}
        self._retry_policies: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str | None = None, requires_confirmation: bool = False, retryable: bool = False, max_retries: int = 0) -> Callable:
        """Decorator to register a function as a tool."""
        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            self._tools[tool_name] = self._wrap_tool(func)
            self._requires_confirmation[tool_name] = requires_confirmation
            self._retry_policies[tool_name] = {"retryable": retryable, "max_retries": max_retries}
            return func
        return decorator

    def _wrap_tool(self, func: Callable) -> Callable:
        """Wraps a tool function to handle errors safely and return JSON strings."""
        def wrapper(*args, **kwargs) -> str:
            try:
                result = func(*args, **kwargs)
                return json.dumps({"status": "success", "result": result})
            except Exception as e:
                logger.error(f"Error executing tool {func.__name__}: {e}")
                return json.dumps({"status": "error", "error": str(e)})
        
        # We must preserve the signature and docstring for the LLM to understand it
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        wrapper.__annotations__ = getattr(func, '__annotations__', {})
        wrapper.__signature__ = inspect.signature(func)
        return wrapper

    def get_all_tools(self) -> List[Callable]:
        """Returns all registered tool functions."""
        return list(self._tools.values())
        
    def get_tool(self, name: str) -> Callable | None:
        """Finds a tool by name."""
        return self._tools.get(name)

    def requires_confirmation(self, name: str) -> bool:
        """Returns True if the tool is registered as requiring user confirmation."""
        return self._requires_confirmation.get(name, False)

    def get_retry_policy(self, name: str) -> Dict[str, Any]:
        """Returns the retry policy for a tool."""
        return self._retry_policies.get(name, {"retryable": False, "max_retries": 0})

# Global registry instance
registry = ToolRegistry()
