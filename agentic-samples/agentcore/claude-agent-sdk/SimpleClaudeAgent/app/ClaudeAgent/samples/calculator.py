# Simple calculator module — used as a sample file for Claude Agent SDK demo prompts.
# Try: {"prompt": "Read /app/samples/calculator.py and explain what it does"}
# Try: {"prompt": "Search for any TODO comments in /app/samples/"}


# TODO: add input validation (reject non-numeric types)
def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return a + b


def subtract(a: int, b: int) -> int:
    """Return the difference of two integers."""
    return a - b


def multiply(a: int, b: int) -> int:
    """Return the product of two integers."""
    return a * b


def divide(a: float, b: float) -> float:
    """Return the quotient of two numbers."""
    return a / b  # TODO: handle b == 0 to avoid ZeroDivisionError
