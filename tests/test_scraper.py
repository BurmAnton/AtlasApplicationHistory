import openpyxl
import pytest
import responses
import requests
from datetime import datetime
from history.scraper import _parse_snapshot_dt
from history.scraper import _wait_for_new_file
from unittest.mock import MagicMock, patch
from history.scraper import collect_and_download_exports
from io import BytesIO
from django.urls import reverse

@responses.activate
def test_parse_snapshot_dt_valid_from_html(html_body):
    responses.add(responses.GET, url="http://127.0.0.1:8000/api/", body=html_body, status=200)
    requests.get("http://127.0.0.1:8000/api/")

    result = _parse_snapshot_dt(html_body)

    assert result == datetime (2025, 12, 9, 14, 28)

def test__parse_snapshot_dt_invalid():
    with pytest.raises(ValueError):
        _parse_snapshot_dt("негативная строка")

@responses.activate
def test_parse_applications_from_json(json_body):
    responses.add(responses.GET, url="http://127.0.0.1:8000/logout/", json=json_body, status=200)
    response = requests.get("http://127.0.0.1:8000/logout/")

    data = response.json()

    assert len(data["applications"]) == 1
    assert data["applications"][0]["rr_id"] == "RR-001"

def test_wait_for_new_file(tmp_path):
    before = set(tmp_path.glob("*.xlsx"))

    file = tmp_path / "test.xlsx"
    file.write_text("Hello World")

    result = _wait_for_new_file(tmp_path, before, timeout=1)

    assert result.name == "test.xlsx"

def test_collect_exports_parses_items(tmp_path, scraper_config):
    driver = MagicMock()

    item = MagicMock()
    text_el = MagicMock()
    text_el.text = "09.12.2025, 14:28"

    item.find_element.return_value = text_el

    download_btn = MagicMock()
    item.find_element.side_effect = [text_el, download_btn]

    driver.find_elements.return_value = [item]

    fake_file = tmp_path / "file.xlsx"

    with patch("history.scraper._wait_for_new_file", return_value=fake_file):
        result = collect_and_download_exports(driver, scraper_config, tmp_path, should_download=lambda title, dt: True, on_export=None)

        assert len(result) == 1
        assert result[0].snapshot_dt == datetime (2025, 12, 9, 14, 28)

@pytest.mark.django_db
def test_xlsx_export(client, user, existing_application):
    client.force_login(user)

    response = client.get(
        reverse("application_list"), {"export": "1"})

    open_xlsx = openpyxl.load_workbook(BytesIO(response.content))
    first_sheet = open_xlsx.active

    headers_cap = [cell.value for cell in first_sheet[1]]
    headers_value = [cell.value for cell in first_sheet[2]]

    assert "ID заявки из РР" in headers_cap
    assert "Фамилия" in headers_cap
    assert "Имя" in headers_cap
    assert "RR-001" in headers_value
    assert "Иванов" in headers_value
    assert "Иван" in headers_value