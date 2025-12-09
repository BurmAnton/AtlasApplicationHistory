from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from history.scraper import ExportItem, run_scraper_latest
from history.services import import_from_file
from history.models import ImportHistory


class Command(BaseCommand):
    help = (
        "Создает новую выгрузку на странице Атласа, скачивает только её и сразу импортирует."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--config",
            dest="config",
            default="scraper_config.yaml",
            help="Путь до файла конфигурации скрапера (по умолчанию scraper_config.yaml).",
        )

    def handle(self, *args, **options):
        config_path = options["config"]
        self.stdout.write(self.style.NOTICE(f"Используется конфиг: {config_path}"))

        def should_download(title: str, snapshot_dt):
            exists = ImportHistory.objects.filter(
                snapshot_dt=snapshot_dt, filename=title
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
            item = run_scraper_latest(
                config_path=config_path,
                should_download=should_download,
                on_export=on_export,
            )
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"Ошибка при работе скрапера: {exc}") from exc

        if not item:
            self.stdout.write(self.style.WARNING("Новая выгрузка не была создана/скачана."))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово. Импортирован новый срез от {item.snapshot_dt:%d.%m.%Y %H:%M} ({item.title})."
            )
        )


