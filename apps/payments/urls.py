from django.urls import path

from .views import (
    MerchantMeView,
    PaymentConfirmView,
    PaymentIntentCreateView,
    PaymentIntentDetailView,
    MerchantRecordSaleView,
)

app_name = "payments"

urlpatterns = [
    path("merchant/me/", MerchantMeView.as_view(), name="merchant-me"),
    path("payments/intents/", PaymentIntentCreateView.as_view(), name="payment-intent-create"),
    path("payments/intents/<uuid:intent_id>/", PaymentIntentDetailView.as_view(), name="payment-intent-detail"),
    path("payments/confirm/", PaymentConfirmView.as_view(), name="payment-confirm"),
    path("payments/merchant/record-sale/", MerchantRecordSaleView.as_view(), name="merchant-record-sale"),
]
