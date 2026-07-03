# KNOWN ISSUES

Promoted memories for agent-grey.

---

## Django signal disconnect fails silently when dispatch_uid was used on connect

**Type:** bug | **Importance:** 4/5 | **Date:** 2026-03-13 15:51:32
**Tags:** django,signals,testing,dispatch_uid

Root cause: Django's post_save.disconnect(func, sender=Model) uses _make_id(func) as the lookup key, but when the signal was connected with dispatch_uid, the key is (dispatch_uid, _make_id(sender)). These keys don't match, so disconnect silently does nothing.

Fix: Use dispatch_uid parameter in both disconnect and reconnect calls:
```python
# Disconnect
post_save.disconnect(sender=User, dispatch_uid="accounts.create_personal_organisation")

# Reconnect (needs both function AND dispatch_uid)
post_save.connect(create_personal_organisation, sender=User, dispatch_uid="accounts.create_personal_organisation")
```

Impact: DisablePersonalOrgSignalMixin was not actually disabling the personal org signal, causing test users to get unexpected personal organisations. This broke 5 tests in test_dual_screening_api where views use `.first()` on OrganisationMembership queries and got the personal org instead of the test org.

---
