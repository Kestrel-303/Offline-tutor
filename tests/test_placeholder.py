import sympy

import offline_tutor


def test_imports() -> None:
    assert offline_tutor.__doc__
    assert sympy.Rational(8, 2) == 4
