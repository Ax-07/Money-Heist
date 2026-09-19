# Batch 20c — Step 2 — Test Hotfix

## Cause

`tests/task_force/test_task_force_execution_runtime.py` used `@pytest.mark.asyncio` and
`async def` test functions. The project does not install `pytest-asyncio`; Pytest therefore
reported `Unknown pytest.mark.asyncio` and refused to execute all 13 async tests.

The existing Money Heist test suite uses `asyncio.run(...)` for asynchronous production
contracts, so this hotfix aligns the Task Force runtime tests with that convention.

## Scope

This overlay changes only the test harness:

- adds `import asyncio`;
- removes every `@pytest.mark.asyncio` marker;
- converts each async test into a normal synchronous Pytest test;
- executes the original async scenario through `asyncio.run(...)`.

No application/runtime code is changed. No dependency is added. In particular,
`app/task_force/execution_runtime.py` is unchanged.

## Validation performed

The hotfixed test file was validated with the asyncio Pytest plugin explicitly disabled:

```text
python -m pytest -q -p no:asyncio tests/task_force/test_task_force_execution_runtime.py
13 passed
```

Cumulative Task Force harness validation with the plugin disabled:

```text
python -m pytest -q -p no:asyncio tests/task_force
91 passed
```

## Local validation

After extracting this overlay at repository root:

```powershell
uv run pytest -q tests/task_force/test_task_force_execution_runtime.py
uv run pytest -q
git status --short
```
