
from django.contrib import admin
from django.urls import path, include

# Ensure app admin modules (including our hub.admin stub) are imported
# so they can replace the default admin.site (e.g. with MaterialAdminSite).
try:
    import hub.admin  # side-effect: may swap admin.site if material is available
except Exception:
    pass

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('hub.urls')),
]
