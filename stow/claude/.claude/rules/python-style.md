---
globs: '**/*.py'
---

# Python Code Style

> **Project-level `.claude/rules/python-style.md` takes precedence** over this file when present. This provides baseline
> coverage for projects that lack their own Python style rules.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Critical Imports](#critical-imports)
- [Naming Conventions](#naming-conventions)
- [Module API](#module-api)
- [File Organization](#file-organization)
- [Docstring Style](#docstring-style)
- [Line Width](#line-width)
- [Type Annotations (Python 3.9+)](#type-annotations-python-39)
- [Optional Dependencies Pattern](#optional-dependencies-pattern)
- [Code Organization](#code-organization)
  - [Dataclass with Custom Init](#dataclass-with-custom-init)
  - [Custom Exception Hierarchies](#custom-exception-hierarchies)
  - [Error Logging Pattern](#error-logging-pattern)
- [Class Body Whitespace](#class-body-whitespace)
- [Testing](#testing)

<!-- mdformat-toc end -->

## Critical Imports<a name="critical-imports"></a>

`from __future__ import annotations` — always first import. Ordering: Standard library → Third-party → Local →
`if TYPE_CHECKING:` block. Move type-only imports into `TYPE_CHECKING` blocks (TC001). Prefix unused unpacked vars with
`_` (RUF059).

```python
from __future__ import annotations

# Standard library (grouped by module family)
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

# Third-party
from typing_extensions import Self, TypeAlias

# Local
from mypkg.module import SomeClass

# Type-only / circular-import isolation
if TYPE_CHECKING:
    from collections.abc import Iterator
```

## Naming Conventions<a name="naming-conventions"></a>

- **Files:** snake_case for modules, matching feature names
- **Classes:** PascalCase (`HTTPClient`, `RetryConfig`)
- **Functions/methods:** snake_case (`run_command`, `get_instance`)
- **Constants:** UPPER_SNAKE_CASE (`DEFAULT_TIMEOUT`, `PYTHON_VERSIONS`)
- **Type aliases:** PascalCase with TypeAlias annotation (`PathLike: TypeAlias = Union[Path, str]`)
- **Type variables:** Single uppercase or short PascalCase (`T`, `F`, `ArgsT`)
- **Feature flags:** UPPER_SNAKE with `_SUPPORT` suffix (`RICH_SUPPORT`, `CLICK_SUPPORT`)

## Module API<a name="module-api"></a>

All public **modules** MUST define `__all__` immediately after imports. Scripts/hooks (executed directly) should NOT
define `__all__`.

```python
__all__ = [
    'SomeClass',
    'main_function',
]
```

## File Organization<a name="file-organization"></a>

Every Python file follows this structure:

1. Module docstring
2. `from __future__ import annotations`
3. Standard library imports (grouped by module family)
4. Third-party imports
5. Local imports
6. `if TYPE_CHECKING:` block for type-only imports
7. `__all__` definition (modules only — omit for scripts/hooks)
8. Section headers using boxed comment blocks
9. Implementation

## Docstring Style<a name="docstring-style"></a>

Sphinx-style (`:param`, `:return`, `:raises`). Check project ruff config for the `convention` setting — **numpy**
convention enforces dashed section underlines (D406/D407) and summary-line periods (D400); **sphinx** convention uses
colon-terminated section headers (`Examples:`) and no enforced period.

- Multi-line format strongly preferred, even for short descriptions
- Summary lines end with a period when D400 is enabled (numpy convention)
- Lowercase first word after `:directive:` tags unless proper noun/type name
- Directive ordering: `:param:` → `:raises:` → `:return:`
- Use full 120-char line width for docstring content

```python
def example_function(param1: str, param2: int = 5) -> list[str]:
    """
    Brief description (period iff D400 is on).

    Examples
    --------
        >>> example_function("hello", 3)
        ['hello', 'hello', 'hello']

    :param param1: description with lowercase first letter
    :param param2: optional parameter description
    :raises ValueError: if param1 is empty
    :return: description with lowercase first letter
    """
```

> Numpy convention uses dashed `Examples\n--------` section underlines (shown above); sphinx convention uses `Examples:`
> instead. Match whatever the project's ruff `convention` setting enforces.

## Line Width<a name="line-width"></a>

**120 characters** for Python code, docstrings, and Markdown (except code blocks, tables, URLs, mermaid diagrams).

## Type Annotations (Python 3.9+)<a name="type-annotations-python-39"></a>

- `list[str]` not `List[str]`, `dict[str, Any]` not `Dict[str, Any]`
- `str | None` not `Optional[str]`
- `TypeAlias` for complex types, `Protocol` with `@runtime_checkable` for duck typing
- No bare `Any` without justification; exception chaining required: `raise NewError(...) from e`

```python
# TypeAlias for complex types
PathLike: TypeAlias = Union[Path, str]

# Generic TypeVar
T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])

# Function overloads
@overload
@classmethod
def from_dict(cls, data: dict[str, Any]) -> Self: ...

# Protocol with @runtime_checkable
@runtime_checkable
class HasName(Protocol):
    @abstractmethod
    def name(self) -> str: ...

# TypedDict with Required/NotRequired
class ConfigAttributes(TypedDict):
    filepath: NotRequired[Path]
    project:  NotRequired[str]

# ClassVar for class constants
class APIClient:
    DEFAULT_TIMEOUT: ClassVar[int] = 30
```

## Optional Dependencies Pattern<a name="optional-dependencies-pattern"></a>

```python
try:
    import rich
except (ImportError, ModuleNotFoundError):
    RICH_SUPPORT = False
else:
    RICH_SUPPORT = True
```

## Code Organization<a name="code-organization"></a>

- Use boxed comment headers (`# ====`) to separate logical sections
- ABC pattern: `metaclass=abc.ABCMeta` with `@abstractmethod`
- Explicit `else:` clauses when they improve readability
- Multi-line method chains with parentheses for fluent interfaces

```python
# ==============================================================================
# Exception classes
# ==============================================================================

class CustomError(Exception): ...

# Fluent interface — parenthesized chain
result = (
    Selector(data)
    .filter_none()
    .filter(lambda x: x > 2)
    .to_list()
)
```

### Dataclass with Custom Init<a name="dataclass-with-custom-init"></a>

```python
@dataclass(init=False)
class RetryConfig:
    DEFAULT_MAX_RETRIES: ClassVar[int] = 3
    max_retries: int

    def __init__(self, *, max_retries: int = DEFAULT_MAX_RETRIES) -> None:
        self.max_retries = max_retries
```

### Custom Exception Hierarchies<a name="custom-exception-hierarchies"></a>

Inherit from the most appropriate standard exception:

```python
class CommandError(subprocess.CalledProcessError, Generic[AnyStr]):
    def __init__(self, cmd, returncode, message=None, stdout=None, stderr=None) -> None: ...
```

### Error Logging Pattern<a name="error-logging-pattern"></a>

```python
logger.error(f'Operation failed: {e!s}')
logger.debug(traceback.format_exc())
```

## Class Body Whitespace<a name="class-body-whitespace"></a>

**No blank line between a class docstring and the first member.** This applies to all classes — regular, dataclass, ABC,
test classes. The closing `"""` of the class docstring is followed immediately by the first method/attribute.

```python
# CORRECT
class MyThing:
    """
    Brief description
    """
    def __init__(self) -> None: ...

# WRONG — blank line between docstring and first member
class MyThing:
    """
    Brief description
    """

    def __init__(self) -> None: ...
```

## Testing<a name="testing"></a>

See `testing.md` for the full pytest conventions. The essentials:

- Test classes: `TestFunctionName` or `TestClassName`
- All test methods MUST have `-> None` return annotations
- Multi-line test docstrings only (never single-line `"""..."""` format)
- Capitalize first word of test docstring, no period at end
- `@pytest.mark.parametrize` with tuple format for multiple scenarios
- Always run `ruff check` before considering code complete
