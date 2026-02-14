import django

def test_mode():
    django.setup()
    assert True