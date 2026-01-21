from celery import shared_task


@shared_task
def ping_history():
    """
    Простейшая тестовая задача для проверки работы Celery.
    Можно вызвать из Django shell:
        from history.tasks import ping_history
        ping_history.delay()
    """
    return "ok"


@shared_task
def run_export_schedule(schedule_id: int):
    """
    Celery‑задача, которая обслуживает одно конкретное ExportSchedule.

    Логика:
    - по ID находит ExportSchedule;
    - если расписание отключено/устарело — ничего не делает;
    - если по should_run_now() пора запускать скрапинг — вызывает fetch_latest_export
      и помечает расписание как выполненное;
    - в конце всегда планирует себя ещё раз:
        * если только что отработало — через interval_minutes;
        * если пока ещё рано — через 60 секунд для следующей проверки.
    """
    from django.utils import timezone

    from history.management.commands.fetch_latest_export import (
        Command as FetchLatestCommand,
    )
    from history.models import ExportSchedule

    try:
        sched = ExportSchedule.objects.get(pk=schedule_id)
    except ExportSchedule.DoesNotExist:
        # Расписание удалили — останавливаем цепочку задач
        return

    # Если расписание выключено или вышло по дате — не продолжаем
    if not sched.enabled:
        return
    if sched.end_date and timezone.localdate() > sched.end_date:
        return

    # По умолчанию проверяем расписание раз в минуту.
    countdown = 60

    # Проверяем, пора ли запускать. Даже если внутри скрапера произойдёт ошибка,
    # мы НЕ падаем, а просто логируем её и продолжаем планировать следующие проверки.
    if sched.should_run_now():
        try:
            cmd = FetchLatestCommand()
            cmd.handle(config=sched.config_path)
            sched.mark_executed()
            # Следующую проверку делаем через полный интервал только после успешного запуска.
            countdown = sched.interval_minutes * 60
        except Exception as exc:  # noqa: BLE001
            # Логируем в stdout, чтобы было видно в логах Celery,
            # но не обрываем цепочку задач.
            print(
                f"[run_export_schedule] Ошибка при выполнении fetch_latest_export "
                f"для расписания id={sched.pk} ({sched.name!r}): {exc}"
            )

    # Планируем следующий запуск этой же задачи
    run_export_schedule.apply_async(args=(schedule_id,), countdown=countdown)



