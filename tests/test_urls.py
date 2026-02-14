import pytest
from pytest_django.fixtures import client


@pytest.mark.django_db
def test_url_admin(client):
    response = client.get("/admin/")
    assert response.status_code < 500

@pytest.mark.django_db
def test_url_home(client):
    response = client.get("/")
    assert response.status_code < 500



