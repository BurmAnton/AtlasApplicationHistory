from django.core.management.base import BaseCommand

from history.models import Application, StatusHistory


class Command(BaseCommand):
    help = (
        "Пересчитывает поля prev_atlas_status и prev_rr_status у всех Application "
        "на основе истории StatusHistory.\n"
        "Нужно выполнить один раз после обновления логики предыдущих статусов."
    )

    def handle(self, *args, **options):
        total = Application.objects.count()
        updated = 0

        self.stdout.write(self.style.NOTICE(f"Найдено заявок: {total}. Начинаю пересчёт..."))

        for app in Application.objects.iterator():
            current_atlas = app.current_atlas_status
            current_rr = app.current_rr_status

            # Ищем последний статус Атлас, отличный от текущего
            prev_atlas = (
                StatusHistory.objects.filter(
                    application=app,
                    atlas_status__isnull=False,
                )
                .exclude(atlas_status=current_atlas)
                .order_by("-snapshot_dt")
                .values_list("atlas_status", flat=True)
                .first()
            )

            # Ищем последний статус РР, отличный от текущего
            prev_rr = (
                StatusHistory.objects.filter(
                    application=app,
                    rr_status__isnull=False,
                )
                .exclude(rr_status=current_rr)
                .order_by("-snapshot_dt")
                .values_list("rr_status", flat=True)
                .first()
            )

            if app.prev_atlas_status != prev_atlas or app.prev_rr_status != prev_rr:
                app.prev_atlas_status = prev_atlas
                app.prev_rr_status = prev_rr
                app.save(update_fields=["prev_atlas_status", "prev_rr_status"])
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Пересчёт завершён. Обновлено заявок: {updated} из {total}."
            )
        )


