"""Safe evaluation of small math expressions such as ``exp(-x/2) * sin(4*x - t)``.

Project files can come from other people, so expressions are parsed with
:mod:`ast` and only arithmetic, comparisons, numbers, the variables ``x`` and
``t`` and a whitelist of NumPy functions are allowed. Nothing else can run.
"""
from __future__ import annotations

import ast
import warnings
from collections.abc import Callable
from functools import lru_cache

import numpy as np

FUNCTIONS: dict[str, Callable] = {
    name: getattr(np, name) for name in (
        "sin", "cos", "tan", "arcsin", "arccos", "arctan", "arctan2", "sinh", "cosh", "tanh",
        "exp", "log", "log10", "log2", "sqrt", "abs", "sign", "floor", "ceil", "round",
        "minimum", "maximum", "clip", "where", "hypot", "sinc", "heaviside", "mod",
    )
}
FUNCTIONS.update({
    "gauss": lambda x, mu=0.0, sigma=1.0: np.exp(-0.5 * ((x - mu) / sigma) ** 2),
    "step": lambda x: np.where(np.asarray(x) >= 0, 1.0, 0.0),
    "ln": np.log,
    "asin": np.arcsin, "acos": np.arccos, "atan": np.arctan,
})
CONSTANTS = {"pi": np.pi, "e": np.e, "inf": np.inf}

_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load, ast.Call,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv, ast.USub, ast.UAdd,
    ast.Compare, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq, ast.IfExp,
    ast.BoolOp, ast.And, ast.Or, ast.keyword,
)


class ExpressionError(ValueError):
    pass


@lru_cache(maxsize=512)
def compile_expression(src: str, variables: tuple[str, ...] = ("x", "t")):
    """Validate and compile ``src``; return a code object for :func:`evaluate`."""
    text = (src or "").strip().replace("^", "**")
    if not text:
        raise ExpressionError("empty expression")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)     # "is not callable; perhaps you missed a comma?"
            tree = ast.parse(text, mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        raise ExpressionError(f"cannot read expression {src!r}: {getattr(exc, 'msg', exc)}") from None
    allowed = set(variables) | set(FUNCTIONS) | set(CONSTANTS)
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ExpressionError(f"not allowed in expressions: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in allowed:
            names = ", ".join(v for v in ("x", "y", "z", "t") if v in variables)
            raise ExpressionError(f"unknown name {node.id!r} (use {names}, pi, e and functions like sin, exp)")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS):
            raise ExpressionError("only functions such as sin, exp, sqrt, gauss can be called")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ExpressionError("only numbers are allowed as constants")
    return compile(tree, "<expression>", "eval")


def evaluate(src: str, **variables) -> np.ndarray:
    """Evaluate an expression with NumPy broadcasting, e.g. ``evaluate("sin(x)", x=xs)``."""
    code = compile_expression(src, tuple(sorted(set(variables) | {"x", "t"})))
    ns = dict(FUNCTIONS)
    ns.update(CONSTANTS)
    ns.update({k: np.asarray(v, np.float64) if not np.isscalar(v) else float(v) for k, v in variables.items()})
    try:
        with np.errstate(all="ignore"):
            out = eval(code, {"__builtins__": {}}, ns)  # noqa: S307 - AST validated above
    except ExpressionError:
        raise
    except (ArithmeticError, TypeError, ValueError, IndexError, MemoryError, RecursionError) as exc:
        raise ExpressionError(f"cannot evaluate {src!r}: {exc}") from None
    if callable(out):
        raise ExpressionError(f"{src.strip()!r} is a function: call it, e.g. {src.strip()}(x)")
    try:
        if not isinstance(out, (int, float, bool, np.ndarray, np.number, np.bool_)):
            out = np.asarray(out, np.float64)
    except (TypeError, ValueError):
        raise ExpressionError(f"{src!r} does not give numbers") from None
    return out


def uses_time(src: str) -> bool:
    """True if an expression mentions the film time ``t`` (so its curve moves)."""
    try:
        tree = ast.parse((src or "").replace("^", "**"), mode="eval")
    except SyntaxError:
        return False
    return any(isinstance(n, ast.Name) and n.id == "t" for n in ast.walk(tree))
