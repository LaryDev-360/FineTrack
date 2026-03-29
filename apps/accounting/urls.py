from django.urls import path

from .views import (
    AccountingBilanExportCSVView,
    AccountingBilansView,
    AccountingKPIsView,
    AccountingPeriodView,
)

app_name = "accounting"

urlpatterns = [
    path("period/", AccountingPeriodView.as_view(), name="accounting-period"),
    path("bilans/", AccountingBilansView.as_view(), name="accounting-bilans"),
    path("kpis/", AccountingKPIsView.as_view(), name="accounting-kpis"),
    path("export/csv/", AccountingBilanExportCSVView.as_view(), name="accounting-export-csv"),
]
