from __future__ import annotations

import logging
import time

from .event_bus import read_ingestion_events, set_ingestion_cursor
from .ingestion import ingest_log

LOGGER = logging.getLogger("ollive.pipeline")


def drain_ingestion_events(limit: int = 100) -> int:
    events = read_ingestion_events(limit=limit)
    processed = 0
    for stream_id, payload in events:
        ingest_log(payload)
        set_ingestion_cursor(stream_id)
        processed += 1
    return processed


def run_forever(poll_interval_seconds: float = 1.0) -> None:
    LOGGER.info("stage=worker level=start status=pass service=ingestion")
    while True:
        try:
            processed = drain_ingestion_events()
            if processed == 0:
                time.sleep(poll_interval_seconds)
        except KeyboardInterrupt:
            LOGGER.info("stage=worker level=stop status=pass service=ingestion")
            return
        except Exception:
            LOGGER.exception("stage=worker level=loop status=fail service=ingestion")
            time.sleep(poll_interval_seconds)


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()