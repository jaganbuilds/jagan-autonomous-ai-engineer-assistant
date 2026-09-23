import ast
import operator
from typing import Union

from app.tools.registry import registry

# Map AST node types to actual operator functions
ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.BitXor: operator.xor,
    ast.USub: operator.neg
}

def _evaluate_expr(node):
    """Safely recursively evaluates a mathematical AST node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)): # <number>
        return node.value
    elif isinstance(node, ast.BinOp): # <left> <operator> <right>
        op = type(node.op)
        if op not in ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported operator: {op.__name__}")
        left = _evaluate_expr(node.left)
        right = _evaluate_expr(node.right)
        return ALLOWED_OPERATORS[op](left, right)
    elif isinstance(node, ast.UnaryOp): # <operator> <operand> e.g., -1
        op = type(node.op)
        if op not in ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported operator: {op.__name__}")
        operand = _evaluate_expr(node.operand)
        return ALLOWED_OPERATORS[op](operand)
    else:
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

@registry.register()
def calculate(expression: str) -> Union[int, float]:
    """
    Safely evaluates a basic mathematical expression (addition, subtraction, multiplication, division, power).
    
    Args:
        expression: A string representing a mathematical expression (e.g., '2 + 2 * 3' or '10 / 2')
    """
    try:
        # Parse the expression into an AST
        # mode='eval' ensures it's just a single expression
        tree = ast.parse(expression, mode='eval')
        
        # Walk the AST safely
        return _evaluate_expr(tree.body)
        
    except SyntaxError:
        raise ValueError("Invalid syntax in mathematical expression.")
    except ZeroDivisionError:
        raise ValueError("Division by zero error.")
    except Exception as e:
        raise ValueError(f"Failed to calculate expression: {str(e)}")
