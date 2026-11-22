from api.catalog.worker import celery
from api.rfq.db import connection

from .runner import run_agent


@celery.task(name="procurement.research")
def research(run_id):
    return run_agent(run_id)


@celery.task(name="procurement.dispatch")
def dispatch():
    with connection() as conn:
        rows = conn.execute(
            "select id from procurement.procurement_agent_runs where state='queued' or (state in ('planning','executing_tools','verifying') and updated_at<now()-interval '75 seconds') order by created_at limit 5"
        ).fetchall()
    for row in rows:
        research.apply_async(args=[str(row["id"])])
    return len(rows)


celery.conf.beat_schedule["recover-procurement-outbox"] = {
    "task": "procurement.dispatch",
    "schedule": 15.0,
}
