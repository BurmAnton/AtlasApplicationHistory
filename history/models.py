from django.db import models
from django.utils import timezone


class Application(models.Model):
    rr_id = models.CharField(max_length=255, unique=True, verbose_name="ID заявки из РР")
    
    last_name = models.CharField(max_length=255, verbose_name="Фамилия", blank=True, null=True)
    first_name = models.CharField(max_length=255, verbose_name="Имя", blank=True, null=True)
    middle_name = models.CharField(max_length=255, verbose_name="Отчество", blank=True, null=True)
    
    email = models.EmailField(verbose_name="Email", blank=True, null=True)
    
    start_date = models.DateField(verbose_name="Начало периода обучения", blank=True, null=True)
    end_date = models.DateField(verbose_name="Окончание периода обучения", blank=True, null=True)
    
    program_name = models.TextField(verbose_name="Программа обучения", blank=True, null=True)
    region = models.CharField(max_length=255, verbose_name="Регион", blank=True, null=True)
    category = models.TextField(verbose_name="Категория гражданина", blank=True, null=True)
    snils = models.CharField(max_length=50, verbose_name="СНИЛС", blank=True, null=True)
    
    request_date = models.DateField(verbose_name="Дата подачи заявки на РР", blank=True, null=True)
    program_id = models.CharField(max_length=255, verbose_name="ID программы в заявке", blank=True, null=True)
    
    # Denormalized fields for performance
    current_atlas_status = models.CharField(max_length=255, verbose_name="Текущий статус Атлас", blank=True, null=True)
    current_rr_status = models.CharField(max_length=255, verbose_name="Текущий статус РР", blank=True, null=True)
    
    prev_atlas_status = models.CharField(max_length=255, verbose_name="Предыдущий статус Атлас", blank=True, null=True)
    prev_rr_status = models.CharField(max_length=255, verbose_name="Предыдущий статус РР", blank=True, null=True)

    def __str__(self):
        return f"{self.last_name} {self.first_name} ({self.rr_id})"

    class Meta:
        verbose_name = "Заявка"
        verbose_name_plural = "Заявки"


class StatusHistory(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='history', verbose_name="Заявка")
    
    atlas_status = models.CharField(max_length=255, verbose_name="Статус Атлас", blank=True, null=True)
    rr_status = models.CharField(max_length=255, verbose_name="Статус РР", blank=True, null=True)
    
    snapshot_dt = models.DateTimeField(verbose_name="Дата/время среза")

    class Meta:
        verbose_name = "История статуса"
        verbose_name_plural = "История статусов"
        ordering = ['-snapshot_dt']

class ImportHistory(models.Model):
    filename = models.CharField(max_length=255, verbose_name="Имя файла")
    snapshot_dt = models.DateTimeField(verbose_name="Дата/время среза (из формы)")
    upload_dt = models.DateTimeField(auto_now_add=True, verbose_name="Время загрузки")
    created_count = models.IntegerField(default=0, verbose_name="Создано заявок")
    updated_count = models.IntegerField(default=0, verbose_name="Обновлено заявок")

    class Meta:
        verbose_name = "История импорта"
        verbose_name_plural = "История импортов"
        ordering = ['-upload_dt']

    def __str__(self):
        return f"{self.filename} ({self.snapshot_dt})"


class ExportSchedule(models.Model):
    """
    Настройка периодического запуска команды fetch_latest_export.
    """

    name = models.CharField("Название", max_length=255)
    enabled = models.BooleanField("Включено", default=True)

    # Конфиг скрапера (путь до YAML)
    config_path = models.CharField(
        "Путь к scraper_config.yaml", max_length=500, default="scraper_config.yaml"
    )

    # Периодичность запуска в минутах
    interval_minutes = models.PositiveIntegerField("Период (минуты)", default=30)

    # Временное окно в пределах суток
    start_time = models.TimeField("Начало интервала (время дня)")
    end_time = models.TimeField("Окончание интервала (время дня)")

    # Дата, после которой расписание перестаёт работать
    end_date = models.DateField("Дата окончания действия", null=True, blank=True)

    # Когда задача была выполнена в последний раз / когда можно запускать снова
    last_run_at = models.DateTimeField("Последний запуск", null=True, blank=True)

    class Meta:
        verbose_name = "Расписание автоимпорта"
        verbose_name_plural = "Расписания автоимпорта"

    def __str__(self):
        return self.name

    def is_active_now(self) -> bool:
        """
        Возвращает True, если сейчас попадём в окно [start_time, end_time)
        и дата не позднее end_date (если задана).
        """
        now = timezone.localtime()
        if self.end_date and now.date() > self.end_date:
            return False
        if self.start_time <= self.end_time:
            return self.start_time <= now.time() < self.end_time
        # Перекрытие через полночь (например, 22:00–06:00)
        return now.time() >= self.start_time or now.time() < self.end_time

    def should_run_now(self) -> bool:
        """
        Проверяет, пора ли запускать задачу с учётом интервала и окна.
        """
        if not self.enabled:
            return False
        if not self.is_active_now():
            return False
        now = timezone.now()
        if self.last_run_at is None:
            return True
        delta = now - self.last_run_at
        return delta.total_seconds() >= self.interval_minutes * 60

    def mark_executed(self):
        self.last_run_at = timezone.now()
        self.save(update_fields=["last_run_at"])
