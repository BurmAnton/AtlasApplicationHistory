import pytest
from history.models import Application
from history.services import _import_dataframe

@pytest.mark.django_db
def test_date_string_conversion(valid_import_dataframe, snapshot_dt):
    _import_dataframe(valid_import_dataframe, snapshot_dt, "test.xlsx")
    app = Application.objects.get(rr_id="RR-001")

    assert app.start_date.year == 2024
    assert app.start_date.month == 1
    assert app.start_date.day == 1

def test_dataframe_columns(dataframe_with_space):
    dataframe_with_space.columns = dataframe_with_space.columns.str.strip()

    assert "Имя" in dataframe_with_space.columns
    assert "Фамилия" in dataframe_with_space.columns
    assert "Статус заявки в Атлас" in dataframe_with_space.columns

