"""get_active_products must page past PostgREST's 1000-row response cap."""
import db


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self._range = (0, len(rows) - 1)

    def select(self, *_):  return self
    def eq(self, *_):      return self
    def order(self, *_):   return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        start, end = self._range
        cap = min(end, start + 999)  # server-side max-rows
        self.data = self._rows[start:cap + 1]
        return self


class _FakeClient:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _):
        return _FakeQuery(self._rows)


def test_get_active_products_pages_past_1000(monkeypatch):
    rows = [{"id": i} for i in range(2345)]
    monkeypatch.setattr(db, "get_client", lambda: _FakeClient(rows))
    assert db.get_active_products() == rows


def test_get_active_products_exact_page_boundary(monkeypatch):
    rows = [{"id": i} for i in range(1000)]
    monkeypatch.setattr(db, "get_client", lambda: _FakeClient(rows))
    assert db.get_active_products() == rows
