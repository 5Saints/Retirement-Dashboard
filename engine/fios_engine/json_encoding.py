"""Shared exact JSON encoding (Section 27: no float rounding anywhere this engine
produces JSON). `report_export.export_json` and the API layer (`api/fios_api`, which
wraps this engine per `docs/architecture.md`) both need to turn Decimal/date-heavy
dataclass graphs into JSON without introducing the float-rounding regression FastAPI's
own default encoder would (it converts `Decimal` to `int`/`float` depending on whether
there's a fractional part). One encoder, one convention, used everywhere.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime
from decimal import Decimal


class FiosJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return dataclasses.asdict(obj)
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


def to_jsonable(value: object) -> object:
    """Round-trip `value` through `FiosJSONEncoder` to get a plain JSON-safe structure
    (nested dicts/lists/strs/...) -- useful when a caller needs a plain object rather
    than a JSON string, e.g. to hand to a test assertion."""
    return json.loads(json.dumps(value, cls=FiosJSONEncoder))
