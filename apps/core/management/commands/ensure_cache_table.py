"""
Management command to ensure cache table exists and fix stuck sessions.
This runs automatically on deployment if called from startup script.
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from apps.core.cache_utils import get_safe_cache

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Ensure cache table exists and fix stuck sessions"

    def handle(self, *args, **options):  # noqa: C901 - Cache setup and validation
        self.stdout.write("Ensuring cache infrastructure...")

        # Step 1: Create cache table if needed
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cache_table (
                        cache_key varchar(255) NOT NULL PRIMARY KEY,
                        value text NOT NULL,
                        expires timestamp with time zone NOT NULL
                    );
                """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS cache_table_expires
                    ON cache_table (expires);
                """
                )
            self.stdout.write(self.style.SUCCESS("✅ Cache table ensured"))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️ Cache table creation: {e}"))

        # Step 2: Test cache
        try:
            cache_backend = get_safe_cache()
            if cache_backend:
                cache_backend.set("startup_test", "ok", 10)
                value = cache_backend.get("startup_test")
                if value == "ok":
                    self.stdout.write(self.style.SUCCESS("✅ Cache test passed"))
                else:
                    self.stdout.write(
                        self.style.WARNING("⚠️ Cache test returned unexpected value")
                    )
            else:
                self.stdout.write(
                    self.style.WARNING("⚠️ No valid cache backend available")
                )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Cache test failed: {e}"))

        # Step 3: Fix stuck sessions
        try:
            from apps.results_manager.models import ProcessedResult
            from apps.review_manager.models import SearchSession

            stuck = SearchSession.objects.filter(
                status="executing",
                updated_at__lt=timezone.now() - timedelta(minutes=10),
            )

            stuck_count = stuck.count()
            if stuck_count > 0:
                self.stdout.write(f"Found {stuck_count} stuck sessions")

                for session in stuck:
                    results = ProcessedResult.objects.filter(session=session).count()
                    if results > 0:
                        session.status = "ready_for_review"
                        session.save()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✅ Fixed {session.id}: moved to ready_for_review ({results} results)"
                            )
                        )
                    else:
                        age = timezone.now() - session.updated_at
                        if age > timedelta(hours=1):
                            session.status = "archived"
                            session.save()
                            self.stdout.write(
                                self.style.WARNING(
                                    f"❌ Archived {session.id}: no results after {age.total_seconds() / 3600:.1f} hours"
                                )
                            )
            else:
                self.stdout.write(self.style.SUCCESS("✅ No stuck sessions found"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error fixing stuck sessions: {e}"))

        self.stdout.write(self.style.SUCCESS("Cache infrastructure check complete!"))
