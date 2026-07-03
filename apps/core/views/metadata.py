"""
Metadata API views for Agent Grey.

Provides REST endpoints for accessing codebase metadata.
"""

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import cache_page
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

if TYPE_CHECKING:
    pass

# Add scripts directory to path for metadata imports
scripts_path = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
sys.path.insert(0, str(scripts_path))

try:
    from metadata.query_metadata import MetadataQuery
except ImportError:
    MetadataQuery = None


class MetadataAPIView(APIView):
    """API endpoint for codebase metadata."""

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    def get(self, request):
        """Get metadata statistics and information."""
        if not MetadataQuery:
            return Response(
                {"error": "Metadata system not available"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            query = MetadataQuery()

            if not query.metadata:
                return Response(
                    {"error": "No metadata found. Run metadata extraction first."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Get requested data type and delegate to handler
            data_type = request.GET.get("type", "stats")

            handler = self._get_handler_for_type(data_type)
            if not handler:
                return Response(
                    {
                        "error": f"Unknown data type: {data_type}. Valid types: stats, models, search, app, model"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return handler(request, query)

        except Exception as e:
            return Response(
                {"error": f"Error accessing metadata: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _get_handler_for_type(self, data_type: str):
        """Get handler method for data type."""
        handlers = {
            "stats": self._handle_stats_request,
            "models": self._handle_models_request,
            "search": self._handle_search_request,
            "app": self._handle_app_request,
            "model": self._handle_model_request,
        }
        return handlers.get(data_type)

    def _handle_stats_request(self, request, query):
        """Handle stats data type request."""
        return Response(
            {
                "stats": query.get_stats(),
                "last_updated": str(query.metadata.get("updated_at", "unknown")),
            }
        )

    def _handle_models_request(self, request, query):
        """Handle models data type request."""
        models = query.list_models()
        return Response({"models": models, "count": len(models)})

    def _handle_search_request(self, request, query):
        """Handle search data type request."""
        search_term = request.GET.get("q", "")
        if not search_term:
            return Response(
                {"error": "Search query 'q' parameter required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = query.search_metadata(search_term)
        return Response(
            {
                "query": search_term,
                "results": results,
                "total_matches": sum(len(items) for items in results.values()),
            }
        )

    def _handle_app_request(self, request, query):
        """Handle app data type request."""
        app_name = request.GET.get("name", "")
        if not app_name:
            return Response(
                {"error": "App 'name' parameter required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        app_info = query.get_app_info(app_name)
        if not app_info:
            return Response(
                {"error": f"App '{app_name}' not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(app_info)

    def _handle_model_request(self, request, query):
        """Handle model data type request."""
        model_path = request.GET.get("path", "")
        if not model_path:
            return Response(
                {"error": "Model 'path' parameter required (e.g., 'accounts.User')"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        model_info = query.get_model_info(model_path)
        if not model_info:
            return Response(
                {"error": f"Model '{model_path}' not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({"model": model_path, "info": model_info})


class MetadataHealthCheckView(View):
    """Simple health check for metadata system."""

    def get(self, request) -> JsonResponse:
        """Check if metadata system is healthy."""
        from apps.core.types.api_responses import MetadataHealthResponse

        try:
            if MetadataQuery:
                query = MetadataQuery()
                if query.metadata:
                    health: MetadataHealthResponse = {
                        "status": "healthy",
                        "metadata_available": True,
                        "last_updated": str(
                            query.metadata.get("updated_at", "unknown")
                        ),
                        "records_count": 0,
                        "error": None,
                    }

                    stats = query.get_stats()
                    health["records_count"] = stats.get("total_models", 0)
                else:
                    health = {
                        "status": "no_data",
                        "metadata_available": False,
                        "last_updated": None,
                        "records_count": 0,
                        "error": None,
                    }
            else:
                health = {
                    "status": "unavailable",
                    "metadata_available": False,
                    "last_updated": None,
                    "records_count": 0,
                    "error": None,
                }

        except Exception as e:
            health = {
                "status": "error",
                "metadata_available": False,
                "last_updated": None,
                "records_count": 0,
                "error": str(e),
            }

        status_code = 200 if health["status"] == "healthy" else 503
        return JsonResponse(health, status=status_code)
