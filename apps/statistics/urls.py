from django.urls import path

from .views import StatisticsByCategoryView, StatisticsSummaryView, StatisticsTrendsView

app_name = "statistics"

urlpatterns = [
    path("summary/", StatisticsSummaryView.as_view(), name="statistics-summary"),
    path("by-category/", StatisticsByCategoryView.as_view(), name="statistics-by-category"),
    path("trends/", StatisticsTrendsView.as_view(), name="statistics-trends"),
]
