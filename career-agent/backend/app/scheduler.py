"""Optional background scheduler for Step 8's job discovery -- disabled
by default (DISCOVERY_SCHEDULER_ENABLED=false). When enabled, runs
discovery on a fixed interval in addition to whatever the user triggers
manually via POST /discovery/run. A separate opt-in from discovery
itself: discovery always works on-demand regardless of this setting."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.db.database import SessionLocal
from app.models.enums import DiscoveryTrigger

logger = logging.getLogger("app.scheduler")

_scheduler: BackgroundScheduler | None = None


def _scheduled_discovery_job() -> None:
    from app.services.discovery_service import run_discovery

    db = SessionLocal()
    try:
        run = run_discovery(db, trigger=DiscoveryTrigger.SCHEDULED)
        logger.info("scheduled discovery run id=%s jobs_found=%s jobs_created=%s", run.id, run.jobs_found, run.jobs_created)
    except Exception:
        logger.exception("scheduled discovery run failed")
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    settings = get_settings()
    if not settings.discovery_scheduler_enabled or _scheduler is not None:
        return

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _scheduled_discovery_job,
        "interval",
        hours=settings.discovery_scheduler_interval_hours,
        id="discovery_scheduled_run",
        # No explicit next_run_time -- APScheduler's interval trigger
        # defaults to firing one interval from now, not immediately on
        # every server restart.
    )
    _scheduler.start()
    logger.info("discovery scheduler started interval_hours=%s", settings.discovery_scheduler_interval_hours)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
