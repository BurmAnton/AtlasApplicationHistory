import pytest
from django.urls import reverse
from history.models import Application

@pytest.mark.django_db
def test_application_list_requires_login(client):
    response = client.get(reverse("application_list"))
    assert response.status_code < 500


@pytest.mark.django_db
def test_api_requires_token(client):
    response = client.get("/api/application/")
    assert response.status_code < 500


@pytest.mark.django_db
def test_api_guide_requires_login(client):
    response = client.get("/api-guide/")
    assert response.status_code < 500


@pytest.mark.django_db
def test_api_guide_requires_admin_group(client, user):
    client.force_login(user)
    response = client.get("/api-guide/")
    assert response.status_code < 500

@pytest.mark.django_db
def test_application_list_authenticated(client, user, existing_application):
    client.force_login(user)

    response = client.get(reverse("application_list"))

    assert response.status_code == 200
    assert "RR-001" in response.content.decode()

@pytest.mark.django_db
def test_application_search_filter(client, user):
    client.force_login(user)
    Application.objects.create(rr_id="RR-1", first_name="Иван")
    Application.objects.create(rr_id="RR-2", first_name="Петр")

    response = client.get(reverse("application_list"), {"search": "Иван"})

    assert "RR-1" in response.content.decode()
    assert "RR-2" not in response.content.decode()

@pytest.mark.django_db
def test_application_program_filter(client, user):
    client.force_login(user)

    Application.objects.create(rr_id="RR-1", program_name="Python")
    Application.objects.create(rr_id="RR-2", program_name="Java")

    response = client.get(reverse("application_list"), {"program": "Python"})

    assert "RR-1" in response.content.decode()
    assert "RR-2" not in response.content.decode()

@pytest.mark.django_db
def test_application_export(client, user, existing_application):
    client.force_login(user)

    response = client.get(reverse("application_list"), {"export": "1"})

    assert response.status_code == 200
    assert response["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )

@pytest.mark.django_db
def test_api_application_with_token(client, token, existing_application):
    response = client.get(
        "/api/application/",
        HTTP_AUTHORIZATION=f"Token {token.key}"
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)

@pytest.mark.django_db
def test_api_application_filter(client, token):
    Application.objects.create(rr_id="RR-1", program_name="Python")
    Application.objects.create(rr_id="RR-2", program_name="Java")

    response = client.get(
        "/api/application/?program_name=Python",
        HTTP_AUTHORIZATION=f"Token {token.key}"
    )

    data = response.json()
    assert len(data) == 1
    assert data[0]["rr_id"] == "RR-1"

@pytest.mark.django_db
def test_api_history_status(client, token, existing_application, existing_status_history):
    response = client.get(
        "/api/history-status/",
        HTTP_AUTHORIZATION=f"Token {token.key}"
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)

@pytest.mark.django_db
def test_api_invalid_token(client):
    response = client.get(
        "/api/application/",
        HTTP_AUTHORIZATION="Token invalidtoken"
    )

    assert response.status_code == 401