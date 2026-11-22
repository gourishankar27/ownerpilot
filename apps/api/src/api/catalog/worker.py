from api.rfq.worker import celery
from api.rfq.db import connection
from .service import build


@celery.task(name="catalog.build")
def index_catalog(version):
    return build(version)


@celery.task(name="catalog.dispatch")
def dispatch():
    with connection() as conn:
        rows = conn.execute(
            "select id from procurement.catalog_versions where state='queued' or (state='building' and started_at<now()-interval '60 seconds') order by created_at limit 20"
        ).fetchall()
    for row in rows:
        index_catalog.apply_async(args=[str(row["id"])])
    return len(rows)


celery.conf.beat_schedule["recover-catalog-outbox"] = {
    "task": "catalog.dispatch",
    "schedule": 15.0,
}
