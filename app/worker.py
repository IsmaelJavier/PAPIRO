from celery import Celery
from app.config import settings

celery_app = Celery("osint_mvp", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)
celery_app.autodiscover_tasks(["app"])
