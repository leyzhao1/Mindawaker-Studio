from __future__ import annotations

import ast
import math
from typing import Callable

import numpy as np


_ALLOWED_FUNC_NAMES = {
    "sin": np.sin,
    "cos": np.cos,
    "tan": np.tan,
    "exp": np.exp,
    "log": np.log,
    "sqrt": np.sqrt,
    "abs": np.abs,
}

_ALLOWED_BINOPS = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
)

_ALLOWED_UNARYOPS = (
    ast.UAdd,
    ast.USub,
)

_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Call,
    ast.Attribute,
)


_PRESET_FUNCTIONS: dict[str, Callable[[float], float | tuple[float, float]]] = {
    "logistic_basic": lambda x: 1.0 / (1.0 + math.exp(-x)),
    "exp2": lambda x: 2.0**x,
    "linear": lambda x: x,
    "unit_circle": lambda t: (math.cos(t), math.sin(t)),
}


class PlotExpressionError(ValueError):
    pass


def _validate_ast(node: ast.AST) -> None:
    for child in ast.walk(node):
        if not isinstance(child, _ALLOWED_NODES):
            raise PlotExpressionError(f"Disallowed syntax: {type(child).__name__}")
        if isinstance(child, ast.BinOp) and not isinstance(child.op, _ALLOWED_BINOPS):
            raise PlotExpressionError(f"Disallowed operator: {type(child.op).__name__}")
        if isinstance(child, ast.UnaryOp) and not isinstance(child.op, _ALLOWED_UNARYOPS):
            raise PlotExpressionError(f"Disallowed unary operator: {type(child.op).__name__}")
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                if child.func.id not in _ALLOWED_FUNC_NAMES:
                    raise PlotExpressionError(f"Function not allowed: {child.func.id}")
            elif isinstance(child.func, ast.Attribute):
                base = child.func.value
                if not isinstance(base, ast.Name) or base.id not in {"np", "math"}:
                    raise PlotExpressionError("Only np.* or math.* calls are allowed")
            else:
                raise PlotExpressionError("Invalid call target")
        if isinstance(child, ast.Name) and child.id not in {"x", "np", "math"} and child.id not in _ALLOWED_FUNC_NAMES:
            raise PlotExpressionError(f"Name not allowed: {child.id}")


def compile_plot_function(plot_kind: str, expression: str | None = None, preset: str | None = None) -> Callable[[float], float | tuple[float, float]]:
    if plot_kind == "preset":
        if not preset:
            raise PlotExpressionError("preset is required when plot_kind='preset'")
        fn = _PRESET_FUNCTIONS.get(preset)
        if fn is None:
            raise PlotExpressionError(f"Unknown preset: {preset}")
        return fn

    if plot_kind != "expression":
        raise PlotExpressionError("plot_kind must be 'expression' or 'preset'")
    if not expression or not expression.strip():
        raise PlotExpressionError("expression is required when plot_kind='expression'")

    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise PlotExpressionError(f"Invalid expression syntax: {exc.msg}") from exc

    _validate_ast(parsed)
    compiled = compile(parsed, "<plot_expression>", "eval")

    safe_globals = {
        "__builtins__": {},
        "np": np,
        "math": math,
        **_ALLOWED_FUNC_NAMES,
    }

    def _plot_fn(x: float) -> float:
        value = eval(compiled, safe_globals, {"x": x})
        if isinstance(value, (int, float, np.floating, np.integer)):
            return float(value)
        raise PlotExpressionError("Compiled expression must return a numeric scalar")

    return _plot_fn
