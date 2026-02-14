import pytest
from history.models import Application
from history.services import _import_dataframe, import_from_file, import_data, export_to_excel

@pytest.mark.django_db
def test_import_dataframe(invalid_dataframe, snapshot_dt):
    with pytest.raises(ValueError):
        _import_dataframe(invalid_dataframe, snapshot_dt, "test.xlsx")

@pytest.mark.django_db
def test_import_creates_application(valid_import_dataframe, snapshot_dt):
    created, updated = _import_dataframe(valid_import_dataframe, snapshot_dt, "test.xlsx")

    assert created == 1
    assert updated == 0
    assert Application.objects.count() == 1

@pytest.mark.django_db
def test_import_updates_application(existing_application, valid_import_dataframe, snapshot_dt):
    created, updated = _import_dataframe(valid_import_dataframe, snapshot_dt, "test.xlsx")

    existing_application.refresh_from_db()

    assert created == 0
    assert updated == 1
    assert existing_application.current_atlas_status == "new"
    assert existing_application.current_rr_status == "created"

@pytest.mark.django_db
def test_import_file_duplicate_snapshot(existing_import_history, snapshot_dt):
    with pytest.raises(ValueError):
        import_from_file("file.xlsx", snapshot_dt)

@pytest.mark.django_db
def test_import_data_duplicate_snapshot(existing_import_history, snapshot_dt):
    with pytest.raises(ValueError):
        import_data("file.xlsx", snapshot_dt)

@pytest.mark.django_db
def test_export_to_excel_response(application):
    response = export_to_excel(Application.objects.all())

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/vnd.openxmlformats-officedocument")