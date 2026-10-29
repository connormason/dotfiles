---
globs: tests/**
---

# Testing Rules

> Universal pytest conventions. Project-specific runners, markers, and matrices belong in a project-level
> `.claude/rules/testing.md`.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Test Structure](#test-structure)
- [Test Docstrings](#test-docstrings)
- [Test Patterns](#test-patterns)
  - [Parametrized Testing](#parametrized-testing)
  - [Fixtures](#fixtures)
  - [Exception Testing](#exception-testing)
  - [Platform / Availability Gating](#platform--availability-gating)
- [Linting Compliance](#linting-compliance)

<!-- mdformat-toc end -->

## Test Structure<a name="test-structure"></a>

- Test classes: `TestFunctionName` or `TestClassName`
- Test methods: `test_specific_behavior_description() -> None`
- **All test methods MUST have a `-> None` return type annotation**
- Use `@pytest.mark.parametrize` for multiple scenarios
- Gate environment-dependent tests with `@pytest.mark.skipif(...)`

## Test Docstrings<a name="test-docstrings"></a>

**CRITICAL**: All test docstrings MUST use multi-line format, even for short descriptions:

```python
# CORRECT
class TestFunctionName:
    """
    Tests for function_name
    """
    def test_basic_behavior(self) -> None:
        """
        Test basic functionality description
        """
        assert result == expected

# WRONG — single-line format
def test_basic_behavior(self) -> None:
    """Test basic functionality description"""
```

**Format rules:**

- Opening `"""` on the same line as `def`/`class`
- Description on the next line
- Closing `"""` on its own line
- Capitalize the first word, no period at the end

## Test Patterns<a name="test-patterns"></a>

### Parametrized Testing<a name="parametrized-testing"></a>

```python
@pytest.mark.parametrize(
    ('input_data', 'expected'),
    [
        (['a', 'b', 'c'], 3),
        ([],              0),
        (['single'],      1),
    ],
)
def test_list_length(self, input_data: list[str], expected: int) -> None:
    """
    Test list length calculation with various inputs
    """
    assert len(input_data) == expected
```

### Fixtures<a name="fixtures"></a>

```python
@pytest.fixture(scope='session')
def temp_config_dir() -> Iterator[Path]:
    """
    Create a temporary config directory for the whole session
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture(autouse=True)
def reset_global_state() -> Iterator[None]:
    """
    Reset global state around each test
    """
    original = get_global_state()
    yield
    set_global_state(original)
```

### Exception Testing<a name="exception-testing"></a>

```python
def test_error_handling(self) -> None:
    """
    Test that the function raises for invalid input
    """
    with pytest.raises(CommandError) as exc_info:
        run_failing_command()

    error = exc_info.value
    assert error.returncode != 0
    assert 'expected error message' in str(error)
```

### Platform / Availability Gating<a name="platform--availability-gating"></a>

```python
@pytest.mark.skipif(os.name != 'posix', reason='Unix-specific test')
def test_unix_command(self) -> None: ...

@pytest.mark.skipif(not shutil.which('git'), reason='Git not available')
def test_git_operations(self) -> None: ...
```

## Linting Compliance<a name="linting-compliance"></a>

All tests MUST pass `ruff check` without errors. Common issues:

1. **TC001**: move application imports used only in type hints into `TYPE_CHECKING` blocks
2. **RUF059**: prefix unused unpacked variables with an underscore (`_name, value = pair`)
3. Always run `ruff check tests/` before considering tests complete
