from rest_framework.routers import DefaultRouter

from .views import SearchSessionViewSet

app_name = "review_manager_api"

router = DefaultRouter()
router.register(r"sessions", SearchSessionViewSet, basename="session")

urlpatterns = router.urls
