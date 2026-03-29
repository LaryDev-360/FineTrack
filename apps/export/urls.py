from django.urls import path

from .views import ExportBackupJSONView, ExportTransactionsCSVView

app_name = "export"

urlpatterns = [
    path("csv/", ExportTransactionsCSVView.as_view(), name="export-csv"),
    path("json/", ExportBackupJSONView.as_view(), name="export-json"),
]
