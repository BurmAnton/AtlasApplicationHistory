import pytest
from pytest_django.fixtures import client


def test_url_admin(client):
    response = client.get("/admin/")
    assert response.status_code < 500

def test_url_home(client):
    response = client.get("/")
    assert response.status_code < 500

def test_url_api_guide(client):
    response = client.get("/api-guide/")
    assert response.status_code < 500

def test_url_logout(client):
    response = client.get("/logout/")
    assert response.status_code < 500

def test_url_api(client):
    response = client.get("/api/")
    assert response.status_code < 500



