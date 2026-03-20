from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import AccountViewSet
from .views import MobileMoneyWalletListCreateView

router = DefaultRouter()
router.register(r"", AccountViewSet, basename="account")

app_name = "core"

urlpatterns = [
    path("mobile-money-wallets/", MobileMoneyWalletListCreateView.as_view(), name="mobile-money-wallets"),
    path("", include(router.urls)),
]
