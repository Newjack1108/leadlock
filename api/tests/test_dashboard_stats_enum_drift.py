from sqlalchemy.exc import DataError

from app.routers.dashboard import get_dashboard_stats


class _Result:
    def __init__(self, value):
        self._value = value

    def one(self):
        return self._value

    def all(self):
        return self._value


class _FakeSession:
    def __init__(self):
        self._count_stmt_calls = 0

    def exec(self, stmt):
        stmt_sql = str(stmt)
        if "SELECT count(lead.id) AS count_1" in stmt_sql:
            self._count_stmt_calls += 1
        # The 8th lead-count query in get_dashboard_stats is CLOSED.
        if self._count_stmt_calls == 8:
            raise DataError(
                statement="SELECT count(lead.id) FROM lead WHERE lead.status = 'CLOSED'",
                params={"status_1": "CLOSED"},
                orig=Exception("invalid input value for enum leadstatus: CLOSED"),
            )
        if "GROUP BY lead.lead_source" in stmt_sql:
            return _Result([])
        return _Result(0)


async def test_dashboard_stats_handles_closed_enum_drift():
    stats = await get_dashboard_stats(
        session=_FakeSession(),
        current_user=object(),
        period=None,
    )

    assert stats.closed_count == 0
    assert stats.new_count == 0
