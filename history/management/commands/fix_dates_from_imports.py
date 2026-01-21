from datetime import datetime

from django.core.management.base import BaseCommand

from history.models import Application


class Command(BaseCommand):
    help = (
        "Поправить даты (start_date, end_date, request_date), которые были некорректно "
        "распознаны из формата dd.mm.yyyy при старой логике импорта.\n"
        "Логика: если и день, и месяц <= 12 (двусмысленный случай), считаем, что "
        "они были перепутаны местами (mm<->dd), и восстанавливаем исходную дату."
    )

    def handle(self, *args, **options):
        fields = ["start_date", "end_date", "request_date"]
        total = Application.objects.count()
        fixed = 0

        self.stdout.write(
            self.style.NOTICE(
                f"Найдено заявок: {total}. Проверяю и исправляю двусмысленные даты..."
            )
        )

        for app in Application.objects.iterator():
            updates = {}

            for field in fields:
                value = getattr(app, field)
                if not value:
                    continue

                # Интересуют только двусмысленные случаи, когда и день, и месяц в диапазоне 1–12.
                day = value.day
                month = value.month
                if not (1 <= day <= 12 and 1 <= month <= 12):
                    continue

                # Предполагаем, что исходная строка была dd.mm.YYYY, но распарсилась как mm.dd.YYYY.
                # Чтобы восстановить её, форматируем как mm.dd.YYYY и заново парсим как dd.mm.YYYY.
                s = value.strftime("%m.%d.%Y")  # то, что было бы исходной строкой dd.mm.YYYY
                try:
                    corrected = datetime.strptime(s, "%d.%m.%Y").date()
                except ValueError:
                    # Если такая дата невозможна, оставляем как есть.
                    continue

                if corrected != value:
                    updates[field] = corrected

            if updates:
                for f, v in updates.items():
                    setattr(app, f, v)
                app.save(update_fields=list(updates.keys()))
                fixed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Исправление дат завершено. Обновлено заявок: {fixed} из {total}."
            )
        )


