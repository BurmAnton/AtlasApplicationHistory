from django.contrib import admin, messages
from django.core.management import call_command

from .models import Application, StatusHistory, ImportHistory, ExportSchedule


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("rr_id", "last_name", "first_name", "program_name", "current_atlas_status", "current_rr_status")
    search_fields = ("rr_id", "last_name", "first_name", "email", "snils")
    list_filter = ("current_atlas_status", "current_rr_status", "program_name", "region")


@admin.register(StatusHistory)
class StatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("application", "atlas_status", "rr_status", "snapshot_dt")
    list_filter = ("atlas_status", "rr_status")
    search_fields = ("application__rr_id", "application__last_name", "application__first_name")


@admin.register(ImportHistory)
class ImportHistoryAdmin(admin.ModelAdmin):
    list_display = ("filename", "snapshot_dt", "upload_dt", "created_count", "updated_count")
    list_filter = ("upload_dt",)
    search_fields = ("filename",)


@admin.register(ExportSchedule)
class ExportScheduleAdmin(admin.ModelAdmin):
    list_display = ("name", "enabled", "interval_minutes", "start_time", "end_time", "end_date", "last_run_at")
    list_filter = ("enabled",)
    search_fields = ("name", "config_path")

    actions = ("run_scheduler_now", "force_fetch_latest_for_selected")

    @admin.action(description="Выполнить автоимпорт по активным расписаниям (run_export_scheduler)")
    def run_scheduler_now(self, request, queryset):
        """
        Запускает management-команду run_export_scheduler,
        которая сама пройдётся по всем активным ExportSchedule.
        """
        try:
            call_command("run_export_scheduler")
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f"Ошибка при запуске автоимпорта: {exc}")
        else:
            messages.success(
                request,
                "Автоимпорт по активным расписаниям запущен. "
                "Подробности см. в логах сервера / Celery.",
            )

    @admin.action(description="Принудительно запустить скрапинг для выбранных расписаний")
    def force_fetch_latest_for_selected(self, request, queryset):
        """
        Для выбранных ExportSchedule принудительно запускает fetch_latest_export
        с их config_path и обновляет last_run_at.
        """
        from history.management.commands.fetch_latest_export import Command as FetchLatestCommand

        cmd = FetchLatestCommand()
        success_count = 0
        errors = 0

        for sched in queryset:
            try:
                cmd.handle(config=sched.config_path)
                sched.mark_executed()
                success_count += 1
            except Exception as exc:  # noqa: BLE001
                errors += 1
                messages.error(
                    request,
                    f"Ошибка при запуске скрапинга для '{sched.name}' "
                    f"(config={sched.config_path}): {exc}",
                )

        if success_count:
            messages.success(
                request,
                f"Успешно запущен скрапинг для {success_count} расписаний.",
            )
        if not success_count and not errors:
            messages.info(request, "Не выбрано ни одного расписания.")
