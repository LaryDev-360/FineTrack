"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from apps.core.sync_views import InitialSyncView


def api_root(request):
    return JsonResponse({"message": "FineTrack API", "version": "0.1.0"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api_root),
    # OpenAPI / Swagger
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # API
    path("api/auth/", include("apps.accounts.urls")),
    path("api/sync/initial/", InitialSyncView.as_view(), name="sync-initial"),
    path("api/accounts/", include("apps.core.urls")),
    path("api/categories/", include("apps.categories.urls")),
    path("api/transactions/", include("apps.transactions.urls")),
    path("api/budgets/", include("apps.budgets.urls")),
    path("api/statistics/", include("apps.statistics.urls")),
    path("api/accounting/", include("apps.accounting.urls")),
    path("api/export/", include("apps.export.urls")),
    path("api/funding/", include("apps.funding_rag.urls")),
    path("api/", include("apps.payments.urls")),
]
