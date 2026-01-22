from django.urls import path
from . import views

urlpatterns = [
    path('', views.application_list, name='application_list'),
    path('logout/', views.logout_view, name='logout'),
]
