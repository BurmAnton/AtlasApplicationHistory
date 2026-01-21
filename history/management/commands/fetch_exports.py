from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from history.scraper import ExportItem, run_scraper
from history.services import import_from_file
from history.models import ImportHistory


class Command(BaseCommand):
    help = (
        "Запускает скрапер Атласа: логинится, "
        "скачивает все доступные выгрузки и по очереди импортирует их."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--config",
            dest="config",
            default="scraper_config.yaml",
            help="Путь до файла конфигурации скрапера (по умолчанию scraper_config.yaml).",
        )
        parser.add_argument(
            "--limit",
            dest="limit",
            type=int,
            default=None,
            help="Ограничить количество импортируемых выгрузок за один запуск.",
        )

    def handle(self, *args, **options):
        config_path = options["config"]
        limit = options["limit"]

        self.stdout.write(self.style.NOTICE(f"Используется конфиг: {config_path}"))

        total_created = 0
        total_updated = 0

        def should_download(title: str, snapshot_dt):
            # Пропускаем срезы, которые уже есть в истории импорта.
            # Проверяем только по дате среза, т.к. в истории теперь храним
            # реальное имя файла, а не текст из интерфейса Атласа.
            exists = ImportHistory.objects.filter(
                snapshot_dt=snapshot_dt
            ).exists()
            if exists:
                self.stdout.write(
                    self.style.WARNING(
                        f"Пропуск среза {snapshot_dt:%d.%m.%Y %H:%M} ({title}) — уже импортирован."
                    )
                )
                return False
            return True

        def on_export(item: ExportItem):
            nonlocal total_created, total_updated
            file_path: Path = item.file_path
            self.stdout.write(
                self.style.NOTICE(
                    f"Импорт файла: {file_path.name} (срез {item.snapshot_dt:%d.%m.%Y %H:%M})"
                )
            )
            try:
                created, updated = import_from_file(
                    path=file_path,
                    snapshot_dt=item.snapshot_dt,
                    title=item.title,
                )
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(
                    self.style.ERROR(f"Ошибка импорта {file_path.name}: {exc}")
                )
                return

            total_created += created
            total_updated += updated

            # После успешного импорта удаляем локальный файл выгрузки
            try:
                file_path.unlink(missing_ok=True)
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(
                    self.style.WARNING(
                        f"Не удалось удалить файл {file_path}: {exc}"
                    )
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Импорт завершён: создано {created}, обновлено {updated}"
                )
            )

        try:
            exports = run_scraper(
                config_path=config_path,
                should_download=(
                    (lambda title, dt: should_download(title, dt))
                    if limit is None
                    else None
                ),
                on_export=on_export if limit is None else None,
            )
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"Ошибка при работе скрапера: {exc}") from exc

        # Если указан лимит, обрабатываем только первые N скачанных файлов
        if limit is not None and exports:
            exports = exports[:limit]
            for item in exports:
                if not should_download(item.title, item.snapshot_dt):
                    continue
                on_export(item)

        if not exports:
            self.stdout.write(self.style.WARNING("Скрапер не нашёл ни одной выгрузки."))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово. Всего создано: {total_created}, обновлено: {total_updated}."
            )
        )


