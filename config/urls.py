from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path

from apps.core import views as core_views
from apps.storefront import views as storefront_views

handler404 = "apps.core.views.error_404"
handler500 = "apps.core.views.error_500"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("salud/", core_views.health, name="salud"),
    path("robots.txt", storefront_views.robots_txt, name="robots"),
    path("cuenta/", include("apps.accounts.urls")),
    path("panel/", include("apps.panel.urls")),
    path("pagos/", include("apps.payments.urls")),
    path("", include("apps.shipping.urls")),
    path("", include("apps.orders.urls")),
    path("", include("apps.cart.urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.storefront.urls")),
    re_path(r"^media/(?P<path>.+)$", core_views.public_media, name="media"),
]

admin.site.site_header = "GlobalTecnology · respaldo técnico"
admin.site.site_title = "GlobalTecnology"
