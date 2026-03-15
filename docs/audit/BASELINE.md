# Audit Baseline

## Python Version

Python 3.14.3

## Pytest Output

```
==================================== ERRORS ====================================
____________________ ERROR collecting tests/test_export.py _____________________
ImportError while importing test module '/home/frosty/whoopyy/tests/test_export.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.14/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_export.py:31: in <module>
    from whoopyy.models import (
E   ImportError: cannot import name 'CycleStrain' from 'whoopyy.models' (/home/frosty/whoopyy/src/models.py)
____________________ ERROR collecting tests/test_models.py _____________________
ImportError while importing test module '/home/frosty/whoopyy/tests/test_models.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.14/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_models.py:15: in <module>
    from whoopyy.models import (
E   ImportError: cannot import name 'CycleStrain' from 'whoopyy.models' (/home/frosty/whoopyy/src/models.py)
=========================== short test summary info ============================
ERROR tests/test_export.py
ERROR tests/test_models.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
2 errors in 0.24s
```

## Mypy Source Output (src/)

```
src/export.py:309: error: Need type annotation for "stages"  [var-annotated]
src/export.py:312: error: Item "StageSummary" of "StageSummary | dict[Any, Any]" has no attribute "get"  [union-attr]
src/export.py:313: error: Item "StageSummary" of "StageSummary | dict[Any, Any]" has no attribute "get"  [union-attr]
src/export.py:314: error: Item "StageSummary" of "StageSummary | dict[Any, Any]" has no attribute "get"  [union-attr]
src/export.py:315: error: Item "StageSummary" of "StageSummary | dict[Any, Any]" has no attribute "get"  [union-attr]
src/export.py:410: error: "CycleScore" has no attribute "score"  [attr-defined]
src/export.py:662: error: Argument 1 to "sum" has incompatible type "list[float | None]"; expected "Iterable[bool]"  [arg-type]
src/export.py:663: error: Argument 1 to "sum" has incompatible type "list[float | None]"; expected "Iterable[bool]"  [arg-type]
src/export.py:664: error: Argument 1 to "sum" has incompatible type "list[float | None]"; expected "Iterable[bool]"  [arg-type]
src/export.py:715: error: "CycleScore" has no attribute "score"  [attr-defined]
Found 10 errors in 1 file (checked 11 source files)
```

## Mypy Tests Output (tests/)

```
tests/test_auth.py:533: error: Item "None" of "Any | None" has no attribute "_http_client"  [union-attr]
Found 1 error in 1 file (checked 6 source files)
```

## Summary Table

| Metric                      | Count |
|-----------------------------|-------|
| Tests collected             | 0     |
| Tests passed                | 0     |
| Tests failed                | 0     |
| Collection errors           | 2     |
| Mypy source errors (src/)   | 10    |
| Mypy test errors (tests/)   | 1     |

### Notes

- pytest was interrupted at collection phase due to 2 import errors in `tests/test_export.py` and `tests/test_models.py`. Both fail to import `CycleStrain` from `whoopyy.models`.
- All 10 mypy source errors are in `src/export.py`: missing type annotation, union-attr access, attr-defined on `CycleScore`, and arg-type mismatches for `sum`.
- 1 mypy test error in `tests/test_auth.py:533`: union-attr access on a potentially `None` value.

## Statement

No fixes applied in this phase.
