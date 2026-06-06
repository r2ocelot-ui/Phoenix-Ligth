from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services import ranks


def _user(**overrides):
    base = dict(
        rank="novato",
        extra_permissions=[],
        denied_permissions=[],
        activity_points=0,
        created_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_novato_is_read_only():
    u = _user()
    assert ranks.has_permission(u, ranks.P_CABINET_READ)
    assert not ranks.has_permission(u, ranks.P_CABINET_CONTROL)


def test_owner_holds_wildcard():
    u = _user(rank="owner")
    assert ranks.effective_permissions(u) == {ranks.WILDCARD}
    assert ranks.has_permission(u, ranks.P_USER_MANAGE)


def test_extra_permission_grants_beyond_rank():
    u = _user(extra_permissions=[ranks.P_CABINET_CONTROL])
    assert ranks.has_permission(u, ranks.P_CABINET_CONTROL)


def test_denied_permission_revokes_rank_default():
    u = _user(rank="operador", denied_permissions=[ranks.P_CABINET_CONTROL])
    assert not ranks.has_permission(u, ranks.P_CABINET_CONTROL)
    assert ranks.has_permission(u, ranks.P_CABINET_READ)


def test_progression_eligible_with_points_and_tenure():
    u = _user(
        activity_points=10,
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    info = ranks.promotion_eligibility(u)
    assert info["next_rank"] == "operador"
    assert info["eligible"] is True


def test_progression_blocked_without_points():
    assert ranks.promotion_eligibility(_user(activity_points=0))["eligible"] is False


def test_auto_promote_respects_ceiling():
    u = _user(
        activity_points=999,
        created_at=datetime.now(timezone.utc) - timedelta(days=365),
    )
    # Ceiling at novato -> next step (operador) is above the cap, no promotion.
    assert ranks.maybe_auto_promote(u, enabled=True, max_rank="novato") is False
    assert u.rank == "novato"
    # Ceiling at tecnico -> one step up to operador.
    assert ranks.maybe_auto_promote(u, enabled=True, max_rank="tecnico") is True
    assert u.rank == "operador"


def test_auto_promote_disabled_does_nothing():
    u = _user(activity_points=999)
    assert ranks.maybe_auto_promote(u, enabled=False, max_rank="owner") is False
    assert u.rank == "novato"
