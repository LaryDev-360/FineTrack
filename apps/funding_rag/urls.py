from django.urls import path

from .views import FundingAskView, FundingIngestView, FundingReindexView, FundingSourcesView

app_name = "funding_rag"

urlpatterns = [
    path("ask/", FundingAskView.as_view(), name="funding-ask"),
    path("ingest/", FundingIngestView.as_view(), name="funding-ingest"),
    path("sources/", FundingSourcesView.as_view(), name="funding-sources"),
    path("reindex/", FundingReindexView.as_view(), name="funding-reindex"),
]
