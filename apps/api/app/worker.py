from celery import Celery
from .config import settings

celery = Celery('zota', broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(task_serializer='json', accept_content=['json'], result_serializer='json', task_track_started=True, broker_connection_retry_on_startup=True)

@celery.task
def health():
    return {'status': 'ok', 'note': 'Phase 1 worker infrastructure; discovery and delivery tasks are not enabled.'}
