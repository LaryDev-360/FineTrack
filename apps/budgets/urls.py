from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BudgetViewSet

router = DefaultRouter()
router.register(r"", BudgetViewSet, basename="budget")

app_name = "budgets"

urlpatterns = [
    path("", include(router.urls)),
]
