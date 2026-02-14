import pytest
from django.db import connection
from history.models import Application

@pytest.mark.django_db
def test_migrations():
    tables = connection.introspection.table_names()
    assert "django_migrations" in tables

@pytest.mark.django_db
def test_model(application):
    assert Application.objects.count() == 1
    assert application.rr_id == "RR-001"