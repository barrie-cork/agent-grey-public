"""
Tests for Phase 0 browser-extension prototype: BrowsingVisit feeds PRISMA
other-methods flow; database flow is unchanged; metadata persists on results.

Deliberately failing until S7 (auto_populate_other_methods wiring) and S3
(add_manual_result metadata) are implemented.
"""

from django.test import TestCase

from apps.core.tests.utils import create_test_user
from apps.reporting.services.prisma_reporting_service import PrismaReportingService
from apps.review_manager.models import SearchSession
from apps.review_results.models import BrowsingVisit
from apps.review_results.services.manual_result_service import ManualResultService


class BrowsingVisitsPrismaFlowTest(TestCase):
    """BrowsingVisit rows populate other_methods_flow; database_flow is unchanged."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Browsing Visits PRISMA Test",
            owner=self.user,
            status="under_review",
        )
        self.service = PrismaReportingService()

    def _prisma(self):
        return self.service.generate_full_prisma_flow_data(str(self.session.id))

    def _create_visits(self, count=1, *, access_successful=True, domain_base="example"):
        for i in range(count):
            BrowsingVisit.objects.create(
                session=self.session,
                user=self.user,
                url=f"https://{domain_base}{i}.com/report",
                title=f"Report {i}",
                access_successful=access_successful,
                visit_source="auto",
            )

    def test_visits_appear_in_other_methods_retrieval(self):
        """N visits -> reports_sought = N in other_methods_flow."""
        self._create_visits(5)
        result = self._prisma()
        self.assertEqual(result["other_methods_flow"]["retrieval"]["reports_sought"], 5)

    def test_failed_visits_counted_as_not_retrieved(self):
        """Visits with access_successful=False count as reports_not_retrieved."""
        self._create_visits(3, access_successful=True)
        self._create_visits(2, access_successful=False)
        om = self._prisma()["other_methods_flow"]
        self.assertEqual(om["retrieval"]["reports_sought"], 5)
        self.assertEqual(om["retrieval"]["reports_not_retrieved"], 2)

    def test_database_flow_unchanged_by_browsing_visits(self):
        """Adding BrowsingVisit rows must not alter the database (left) column."""
        baseline = self._prisma()["database_flow"]
        self._create_visits(10)
        self.assertEqual(self._prisma()["database_flow"], baseline)

    def test_no_visits_gives_zero_reports_sought(self):
        """When no BrowsingVisit rows exist, other_methods reports_sought is 0."""
        om = self._prisma()["other_methods_flow"]
        self.assertEqual(om["retrieval"]["reports_sought"], 0)


class AddManualResultMetadataTest(TestCase):
    """add_manual_result should accept and persist metadata fields on ProcessedResult."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Metadata Persistence Test",
            owner=self.user,
            status="under_review",
        )

    def test_metadata_fields_persisted(self):
        """author, published_date, publisher, document_type survive the round-trip."""
        result = ManualResultService.add_manual_result(
            session=self.session,
            user=self.user,
            url="https://nice.org.uk/guidance/ng123",
            title="NICE Guidelines NG123",
            justification="Found during grey-lit browsing",
            metadata={
                "author": "NICE Editorial Board",
                "published_date": "2024-03-15",
                "publisher": "National Institute for Health and Care Excellence",
                "document_type": "report",
            },
        )
        result.refresh_from_db()
        self.assertIn("NICE Editorial Board", result.authors)
        self.assertEqual(str(result.publication_date), "2024-03-15")
        self.assertEqual(
            result.source_organization,
            "National Institute for Health and Care Excellence",
        )
        self.assertEqual(result.document_type, "report")

    def test_existing_callers_without_metadata_unaffected(self):
        """add_manual_result without metadata= still works (all new args optional)."""
        result = ManualResultService.add_manual_result(
            session=self.session,
            user=self.user,
            url="https://example.com/page",
            title="Example Page",
            justification="Found while browsing",
        )
        self.assertIsNotNone(result.pk)
        self.assertEqual(result.authors, [])
