from django.core.management.base import BaseCommand

from history.models import ExportSchedule
from history.management.commands.fetch_latest_export import Command as FetchLatestCommand


class Command(BaseCommand):
    help = (
        "Проверяет активные расписания ExportSchedule и, при необходимости, "
        "запускает fetch_latest_export для каждого."
        "\nОбычно вызывается каждые 1–5 минут планировщиком ОС."
    )

    def handle(self, *args, **options):
        schedules = ExportSchedule.objects.all()
        if not schedules:
            self.stdout.write(self.style.WARNING("Нет настроенных расписаний ExportSchedule."))
            return

        fetch_cmd = FetchLatestCommand()

        for sched in schedules:
            if not sched.should_run_now():
                continue

            self.stdout.write(
                self.style.NOTICE(
                    f"Запуск расписания '{sched.name}' (config={sched.config_path})"
                )
            )

            fetch_cmd.handle(config=sched.config_path)
            sched.mark_executed()


