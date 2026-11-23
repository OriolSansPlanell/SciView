"""Fuzzing the two places that read text from other people: math expressions and project files.

Whatever they are given, they must either work or raise a clear error (ExpressionError / ValueError), never
crash with another exception, hang, or run code. Seeds are fixed, so a failure can be reproduced.
"""
import copy
import json
import random
import signal
from pathlib import Path

import numpy as np
import pytest

import sciview as sv
from sciview.engine.mathexpr import ExpressionError, evaluate

GOLDEN = sorted((Path(__file__).parent / "golden" / "0.4").glob("*.sciview.json"))
TOKENS = ["x", "t", "y", "1", "2.5", "1e3", "-", "+", "*", "/", "**", "(", ")", ",", "sin", "cos", "exp", "log",
          "sqrt", "abs", "pi", "e", "where", "clip", "min", "max", "<", ">", "==", "and", "or", "not", "if", "else",
          "[", "]", "{", "}", "'", '"', "__import__", "os", "lambda", ".", "__class__", "__subclasses__", "open",
          ":", ";", "=", "@", "%", "//", "~", "^", "&", "|", "  ", "\n", "nan", "inf", "1" * 400, "(" * 50]


class Timeout(Exception):
    pass


def _alarm(seconds):
    if hasattr(signal, "SIGALRM"):
        def handler(*_):
            raise Timeout()
        signal.signal(signal.SIGALRM, handler)
        signal.alarm(seconds)


def _clear():
    if hasattr(signal, "SIGALRM"):
        signal.alarm(0)


def test_expressions_never_crash_or_run_code():
    rng = random.Random(1234)
    x = np.linspace(-3, 3, 7)
    compiled = 0
    for _ in range(3000):
        src = "".join(rng.choice(TOKENS) + rng.choice(["", " "]) for _ in range(rng.randint(1, 12)))
        _alarm(5)
        try:
            evaluate(src, x=x, t=0.5)
            compiled += 1
        except ExpressionError:
            pass
        except Timeout:
            pytest.fail(f"expression took too long: {src!r}")
        except Exception as exc:  # anything else is a bug
            pytest.fail(f"{type(exc).__name__} for {src!r}: {exc}")
        finally:
            _clear()
    assert compiled > 20                              # the generator does produce valid expressions too


def test_expressions_reject_attempts_to_escape():
    for src in ("__import__('os').system('echo hi')", "().__class__.__subclasses__()", "open('x')",
                "(lambda: 1)()", "x.__class__", "[c for c in ()]", "exec('1')", "eval('1')", "globals()"):
        with pytest.raises(ExpressionError):
            evaluate(src, x=np.zeros(2), t=0)


def _mutate(rng, value, depth=0):
    """A random change somewhere in a JSON value: wrong types, missing keys, odd numbers, deep nesting."""
    odd = [None, True, -1, 0, 1e308, -1e308, float("nan"), "", "x" * 5000, [], {}, [1, 2], {"a": 1}, "#zzz",
           "../../etc/passwd", "assets/*.csv", [[1]], 3.5, "1, 2, 3"]
    if isinstance(value, dict) and value and depth < 6:
        k = rng.choice(list(value))
        roll = rng.random()
        if roll < 0.15:
            del value[k]
        elif roll < 0.3:
            value[k] = rng.choice(odd)
        else:
            value[k] = _mutate(rng, value[k], depth + 1)
        return value
    if isinstance(value, list) and value and depth < 6:
        i = rng.randrange(len(value))
        roll = rng.random()
        if roll < 0.1:
            value.pop(i)
        elif roll < 0.2:
            value.insert(i, copy.deepcopy(rng.choice(value)))
        elif roll < 0.3:
            value[i] = rng.choice(odd)
        else:
            value[i] = _mutate(rng, value[i], depth + 1)
        return value
    return rng.choice(odd)


@pytest.mark.parametrize("path", GOLDEN, ids=lambda p: p.name.split(".")[0])
def test_damaged_project_files_load_or_say_why(path, tmp_path):
    base = json.loads(path.read_text(encoding="utf-8"))
    rng = random.Random(path.name)
    for i in range(60):
        data = copy.deepcopy(base)
        for _ in range(rng.randint(1, 6)):
            data = _mutate(rng, data)
        try:
            film = sv.Project.from_json(data, tmp_path / "f.sciview.json")
        except ValueError:
            continue                                       # a clear refusal is fine
        except Exception as exc:
            pytest.fail(f"case {i}: loading crashed with {type(exc).__name__}: {exc}")
        try:
            film.validate()
            again = sv.Project.from_json(json.loads(json.dumps(film.to_json(), allow_nan=True)))
            with np.errstate(all="ignore"):                  # absurd numbers may overflow: fine, if no crash
                again.frame(film.duration * rng.random(), 0.05)
        except Exception as exc:
            pytest.fail(f"case {i}: a film that loaded then failed ({type(exc).__name__}: {exc})")
