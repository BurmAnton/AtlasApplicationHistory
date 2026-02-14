import pytest
from django.core.exceptions import ValidationError
from history.models import Application
from tests.conftest import application

@pytest.mark.django_db
def test_model(application):
    assert application.id is not None

@pytest.mark.django_db
def test_app_employment_default(application):
    assert application.employment is False

@pytest.mark.django_db
def test_import_history_defaults(import_history):
    assert import_history.created_count == 0
    assert import_history.updated_count == 0
    assert import_history.upload_dt is not None

@pytest.mark.django_db
def test_import_schedule_defaults(export_schedule):
    assert isinstance(export_schedule.is_active_now(), bool)

@pytest.mark.django_db
def test_application_create(application_data):
    assert Application.objects.create(**application_data).pk is not None

@pytest.mark.django_db
def test_application_rr_id_required(application_data):
    application_data["rr_id"] = None
    app = Application(**application_data)

    with pytest.raises(ValidationError):
        app.full_clean()
        app.save()

@pytest.mark.django_db
def test_application_atlas_status(application_data):
    application_data["current_atlas_status"] = "WRONG_STATUS"
    app = Application(**application_data)

    app.full_clean()
    app.save()

    assert app.current_atlas_status == "WRONG_STATUS"

@pytest.mark.django_db
def test_application_email_max_length(application_data):
    application_data["email"] = "a" * 300 + "@test.ru"
    app = Application(**application_data)

    with pytest.raises(ValidationError):
        app.full_clean()
        app.save()