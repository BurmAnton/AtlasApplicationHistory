from django.contrib import admin

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
