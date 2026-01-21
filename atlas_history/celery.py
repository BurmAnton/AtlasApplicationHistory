import os

from celery import Celery

# Указываем настройки Django по умолчанию для celery
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "atlas_history.settings")

app = Celery("atlas_history")

# Читает настройки CELERY_* из django settings
app.config_from_object("django.conf:settings", namespace="CELERY")

# Автоматически находит tasks.py во всех установленных приложениях
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")


