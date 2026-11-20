"""Regression tests: non-polynomial equations must classify as "nonlinear".

Found by the adversarial eval (a06): "sin(x) = 0.5" was read as "(x) = 0.5"
because the word "sin" ended the equation run, so it classified as linear.
"""

import pytest

from offline_tutor.equations import classify


@pytest.mark.parametrize(
    "text",
    [
        "sin(x) = 0.5",
        "cos(x) = 1",
        "tan(x) = 1",
        "exp(x) = 2",
        "log(x) = 1",
        "sqrt(x) = 3",
        "abs(x) = 2",
        "1/x = 2",
    ],
)
def test_non_polynomial_is_nonlinear(text: str) -> None:
    assert classify(text) == "nonlinear"


# Results recorded before the fix; the fix must not change them.
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2*x + 3 = 7", "linear_one_var"),
        ("x/2 + 1 = 3", "linear_one_var"),
        ("0.5*x = 2", "linear_one_var"),
        ("sqrt(2)*x = 4", "linear_one_var"),
        ("x**2 = 4", "nonlinear"),
        ("x + y = 3", "linear_other"),
    ],
)
def test_unchanged(text: str, expected: str) -> None:
    assert classify(text) == expected
