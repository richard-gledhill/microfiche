from fuzzywuzzy import fuzz

def foo(bar: str = "Hello World!") -> str:
    """Summary line.

    Extended description of function.

    Args:
        bar: Description of input argument.

    Returns:
        Description of return value
    """

    return bar


if __name__ == "__main__":  # pragma: no cover
    print(foo())
    pass
