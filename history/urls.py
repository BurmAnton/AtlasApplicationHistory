from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter
from .views import ApplicationViewSet

router = DefaultRouter()
router.register(r'user-progress', ApplicationViewSet, basename='user-progress')

urlpatterns = [
    path('', views.application_list, name='application_list'),
    path('logout/', views.logout_view, name='logout'),
    path('api-guide/', views.api_guide, name="api-guide"),
    path('api/', include(router.urls)),
]
