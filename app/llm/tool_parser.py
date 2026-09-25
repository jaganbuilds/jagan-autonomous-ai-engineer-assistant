import inspect
from typing import Callable, Dict, Any

def get_type_name(t: Any) -> str:
    if t == int: return "integer"
    if t == float: return "number"
    if t == bool: return "boolean"
    if t == list or getattr(t, '__origin__', None) == list: return "array"
    if t == dict or getattr(t, '__origin__', None) == dict: return "object"
    return "string"

def callable_to_openai_tool(func: Callable) -> Dict[str, Any]:
    sig = inspect.signature(func)
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    for name, param in sig.parameters.items():
        if name == "session_id":
            continue # session_id is injected internally, not exposed to LLM
            
        param_type = "string"
        if param.annotation != inspect.Parameter.empty:
            param_type = get_type_name(param.annotation)
            
        parameters["properties"][name] = {
            "type": param_type,
            "description": f"Parameter {name}"
        }
        
        if param.default == inspect.Parameter.empty:
            parameters["required"].append(name)
            
    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": inspect.getdoc(func) or f"Execute {func.__name__}",
            "parameters": parameters
        }
    }
