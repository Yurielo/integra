"""Structured lifecycle events on stderr; no accumulating log in either store."""
import json
import sys
from datetime import datetime, timezone


def emit(event, **fields):
    print(json.dumps({'artifact_type': 'integra.lifecycle_event', 'event': event,
                      'at': datetime.now(timezone.utc).isoformat(), **fields},
                     sort_keys=True), file=sys.stderr, flush=True)
