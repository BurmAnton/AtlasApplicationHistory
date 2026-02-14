import pandas as pd
import pytest
from unittest.mock import patch
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from history.models import Application, ImportHistory, ExportSchedule, StatusHistory
from datetime import time, date, datetime


@pytest.fixture
def application():
    return Application.objects.create(rr_id="RR-001", first_name="Иван", last_name="Иванов")

@pytest.fixture
def import_history():
    return ImportHistory.objects.create(filename="test.xlsx", snapshot_dt=date(2024, 1, 1))

@pytest.fixture
def export_schedule():
    with patch("history.tasks.run_export_schedule"):
        return ExportSchedule.objects.create(name="Test Schedule", start_time=time(9, 0), end_time=time(22, 0))

@pytest.fixture
def application_data():
    return {
        "rr_id": "RR-001",
        "last_name": "Иванов",
        "first_name": "Иван",
        "email": "ivan@test.ru",
        "program_name": "Python",
        "current_atlas_status": "new",
        "current_rr_status": "created",
        "start_date": date.today()
    }

@pytest.fixture
def snapshot_dt():
    return date(2024, 1, 1)

@pytest.fixture
def invalid_dataframe():
    return pd.DataFrame({
        "Имя": ["Иван"]
    })

@pytest.fixture
def valid_import_dataframe():
    return pd.DataFrame([{
        "Фамилия": "Иванов",
        "Имя": "Иван",
        "Отчество": "Иванович",
        "Статус заявки в Атлас": "new",
        "Статус заявки в РР": "created",
        "Email": "ivan@test.ru",
        "Начало периода обучения": "01.01.2024",
        "Окончание периода обучения": "31.12.2024",
        "Программа обучения": "Python",
        "Регион": "Москва",
        "Категория гражданина": "A",
        "СНИЛС": "123",
        "Дата подачи заявки на РР": "01.01.2024",
        "ID программы в заявке": "PR-1",
        "ID заявки из РР": "RR-001",
    }])

@pytest.fixture
def existing_application():
    return Application.objects.create(
        rr_id="RR-001",
        first_name="Иван",
        last_name="Иванов",
        current_atlas_status="old",
        current_rr_status="old",
        start_date = date.today()
    )

@pytest.fixture
def existing_import_history(snapshot_dt):
    return ImportHistory.objects.create(
        filename="test.xlsx",
        snapshot_dt=snapshot_dt,
        created_count=1,
        updated_count=0
    )

@pytest.fixture
def dataframe_with_space():
    return pd.DataFrame(columns=
        [" Имя ",
        " Фамилия ",
        " Статус заявки в Атлас "]
    )

@pytest.fixture
def user():
    return User.objects.create_user(username="testuser", password="12345")

@pytest.fixture
def token(user):
    return Token.objects.create(user=user)

@pytest.fixture
def existing_status_history(existing_application):
    return StatusHistory.objects.create(
        application=existing_application,
        atlas_status="new",
        rr_status="created",
        snapshot_dt=datetime.now()
    )