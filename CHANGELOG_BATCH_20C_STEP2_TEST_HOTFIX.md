# Changelog — Batch 20c Step 2 Test Hotfix

- Fixed Task Force execution runtime tests for the repository's existing async test convention.
- Removed reliance on the absent `pytest-asyncio` plugin.
- Replaced `@pytest.mark.asyncio` execution with `asyncio.run(...)`.
- No production code changed.
- No dependency changed.
- No Risk, broker, registry, LIVE, or execution authority changed.
