# Patterns
Recurring patterns promoted from project memory.


## Django manager methods must be mocked with patch.object, not string-based patch()

**Type:** pattern | **Importance:** 4/5 | **Date:** 2026-03-17 10:35:23
**Tags:** django,testing,mock,pattern
**Issue:** #136

String-based `patch("app.models.MyModel.objects.method")` does NOT work for Django manager methods because `objects` is a `ManagerDescriptor` that returns a fresh manager instance on each attribute access — `patch()` can't traverse it.

**Correct:** `patch.object(MyModel.objects, "get_or_create", side_effect=...)` — this patches the method on the actual manager instance.

**Wrong:** `patch("apps.review_manager.models.ReviewInvitation.objects.get_or_create", ...)` — the mock never intercepts because the descriptor returns a new manager each time.

This applies to all manager methods: `get_or_create`, `create`, `filter`, `count`, `bulk_create`, etc.

---

## When removing a view class, always check views/__init__.py and urls.py for side-file imports

**Type:** pattern | **Importance:** 4/5 | **Date:** 2026-04-04
**Issue:** #149+#150

When a Junior task removes a class or function from a views module (e.g. `SessionSetupView`), the task's "all done" result can be misleading. The removed class may still be imported in `views/__init__.py` (which re-exports for backward compatibility) or registered in `urls.py`. Both cause `ImportError` at startup, crashing the Docker container.

**Always do after removing a class:**
1. `grep -rn 'RemovedClassName' apps/` — catches imports in `views/__init__.py`, `tests/`, `urls.py`, submodules
2. Check `urls.py` for `views.RemovedClassName.as_view()` entries
3. Check `views/__init__.py` for both the import and `__all__` entry
4. Check `CLAUDE.md` for doc references

**Example crash:** `SessionSetupView` removed from `views_main.py` but `views/__init__.py` still had `from apps.review_manager.views_main import SessionSetupView`. Deploy succeeded but containers restarted with `ImportError: cannot import name 'SessionSetupView'`.

---
