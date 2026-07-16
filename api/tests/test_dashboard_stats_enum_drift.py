import pytest

from app.routers.dashboard import get_dashboard_stats


class _Result:
    def __init__(self, value):
        self._value = value

    def one(self):
        return self._value

    def all(self):
        return self._value


class _FakeSession:
    def exec(self, stmt):
        stmt_sql = str(stmt)
        if "GROUP BY lead.lead_source" in stmt_sql:
            return _Result([])
        return _Result(0)


@pytest.mark.anyio
async def test_dashboard_stats_returns_zero_counts_on_empty_session():
    """Closed is quote-based now; no lead CLOSED enum query required."""
    stats = await get_dashboard_stats(
        session=_FakeSession(),
        current_user=object(),
        period=None,
        start_date=None,
        end_date=None,
    )

    assert stats.closed_count == 0
    assert stats.won_count == 0
    assert stats.lost_count == 0
    assert stats.new_count == 0


class _FakeSessionWithDuplicateSources:
    def exec(self, stmt):
        stmt_sql = str(stmt)
        if "GROUP BY lead.lead_source" in stmt_sql:
            return _Result([("WEBSITE", 10, 3)])
        return _Result(0)


@pytest.mark.anyio
async def test_dashboard_stats_includes_duplicate_rate_by_source():
    stats = await get_dashboard_stats(
        session=_FakeSessionWithDuplicateSources(),
        current_user=object(),
        period=None,
        start_date=None,
        end_date=None,
    )

    assert len(stats.leads_by_source) == 1
    source_row = stats.leads_by_source[0]
    assert source_row.source == "WEBSITE"
    assert source_row.count == 10
    assert source_row.duplicate_count == 3
    assert source_row.duplicate_rate == 30.0
