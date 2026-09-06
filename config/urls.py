from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

from schema.schema import graphql_app

urlpatterns = [
    path("admin/", admin.site.urls),
    path("graphql/", graphql_app),
    path("api/auth/", include("apps.auth.urls")),
    path("api/webhooks/", include("apps.wallet.webhook_urls")),
    path("healthcheck/", lambda r: HttpResponse("ok")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
