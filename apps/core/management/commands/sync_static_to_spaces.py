"""
Management command to sync static files to DigitalOcean Spaces.

This command uploads all static files to Spaces with optimal cache headers
and compression settings for production CDN deployment.
"""

import mimetypes
import os

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Sync static files to DigitalOcean Spaces CDN"

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-collect",
            action="store_true",
            help="Skip collectstatic step",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be uploaded without actually uploading",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force re-upload of all files",
        )

    def handle(self, *args, **options):
        """Handle the sync command."""
        # Setup phase
        spaces_config = self._setup_spaces_connection()
        if not spaces_config:
            return

        if not options["no_collect"]:
            self._run_collectstatic()

        # Validation phase
        client, bucket_name = self._create_s3_client(spaces_config)
        if not client:
            return

        static_root = self._validate_static_root()
        if not static_root:
            return

        # Upload phase
        stats = self._upload_files(client, bucket_name, static_root, options)

        # Reporting phase
        self._display_summary(stats, spaces_config)

    def _setup_spaces_connection(self):
        """Setup and verify Spaces connection."""
        try:
            from apps.core.spaces_config import (
                check_spaces_connection,
                get_spaces_config,
            )
        except ImportError:
            self.stdout.write(self.style.ERROR("Spaces configuration module not found"))
            return None

        is_connected, message = check_spaces_connection()
        if not is_connected:
            self.stdout.write(self.style.ERROR(f"Cannot connect to Spaces: {message}"))
            return None

        self.stdout.write(self.style.SUCCESS(f"Connected to Spaces: {message}"))

        spaces_config = get_spaces_config()
        if not spaces_config:
            self.stdout.write(self.style.ERROR("Spaces configuration not available"))
            return None

        return spaces_config

    def _run_collectstatic(self):
        """Run Django collectstatic command."""
        self.stdout.write("Running collectstatic...")
        call_command("collectstatic", "--noinput", verbosity=0)
        self.stdout.write(self.style.SUCCESS("Static files collected"))

    def _create_s3_client(self, spaces_config):
        """Create and configure S3 client."""
        try:
            import boto3.session
        except ImportError:
            self.stdout.write(self.style.ERROR("boto3 is required for Spaces upload"))
            return None, None

        session = boto3.session.Session()
        client = session.client(
            "s3",
            region_name=spaces_config["AWS_S3_REGION_NAME"],
            endpoint_url=spaces_config["AWS_S3_ENDPOINT_URL"],
            aws_access_key_id=spaces_config["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=spaces_config["AWS_SECRET_ACCESS_KEY"],
        )

        bucket_name = spaces_config["AWS_STORAGE_BUCKET_NAME"]
        return client, bucket_name

    def _validate_static_root(self):
        """Validate static root directory exists."""
        static_root = settings.STATIC_ROOT
        if not os.path.exists(static_root):
            self.stdout.write(
                self.style.ERROR(f"Static root does not exist: {static_root}")
            )
            return None
        return static_root

    def _upload_files(self, client, bucket_name, static_root, options):
        """Upload static files to Spaces."""
        stats = {"uploaded": 0, "skipped": 0, "errors": 0}

        for root, dirs, files in os.walk(static_root):
            for filename in files:
                self._upload_single_file(
                    client, bucket_name, static_root, root, filename, options, stats
                )

        return stats

    def _upload_single_file(
        self, client, bucket_name, static_root, root, filename, options, stats
    ):
        """Upload a single file to Spaces."""
        local_path = os.path.join(root, filename)
        relative_path = os.path.relpath(local_path, static_root)
        s3_key = f"static/{relative_path}".replace("\\", "/")

        # Get file metadata
        content_type = self._get_content_type(filename)
        cache_control = self._get_cache_control(filename)

        # Check if upload needed
        should_upload = self._should_upload_file(
            client, bucket_name, s3_key, local_path, options, stats
        )

        if should_upload:
            self._perform_upload(
                client,
                bucket_name,
                s3_key,
                local_path,
                content_type,
                cache_control,
                options,
                stats,
            )
        else:
            stats["skipped"] += 1
            if options.get("verbosity", 1) > 1:
                self.stdout.write(f"Skipped (unchanged): {s3_key}")

    def _get_content_type(self, filename):
        """Get content type for file."""
        content_type, _ = mimetypes.guess_type(filename)
        return content_type or "application/octet-stream"

    def _get_cache_control(self, filename):
        """Get cache control header for file."""
        from apps.core.spaces_config import get_cache_control_for_file

        return get_cache_control_for_file(filename)

    def _should_upload_file(
        self, client, bucket_name, s3_key, local_path, options, stats
    ):
        """Check if file should be uploaded."""
        from botocore.exceptions import ClientError

        if options["force"]:
            return True

        try:
            response = client.head_object(Bucket=bucket_name, Key=s3_key)
            local_size = os.path.getsize(local_path)
            remote_size = response.get("ContentLength", 0)
            return local_size != remote_size
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return True
            else:
                self.stdout.write(self.style.ERROR(f"Error checking {s3_key}: {e}"))
                stats["errors"] += 1
                return False

    def _perform_upload(
        self,
        client,
        bucket_name,
        s3_key,
        local_path,
        content_type,
        cache_control,
        options,
        stats,
    ):
        """Perform the actual file upload."""
        if options["dry_run"]:
            self.stdout.write(f"Would upload: {s3_key}")
            return

        try:
            with open(local_path, "rb") as f:
                client.put_object(
                    Bucket=bucket_name,
                    Key=s3_key,
                    Body=f,
                    ContentType=content_type,
                    CacheControl=cache_control,
                    ACL="public-read",
                )
            self.stdout.write(self.style.SUCCESS(f"Uploaded: {s3_key}"))
            stats["uploaded"] += 1
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to upload {s3_key}: {e}"))
            stats["errors"] += 1

    def _display_summary(self, stats, spaces_config):
        """Display upload summary."""
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(self.style.SUCCESS("Static files sync complete"))
        self.stdout.write(f"Uploaded: {stats['uploaded']} files")
        self.stdout.write(f"Skipped: {stats['skipped']} files")
        if stats["errors"]:
            self.stdout.write(self.style.ERROR(f"Errors: {stats['errors']} files"))

        cdn_domain = spaces_config.get("AWS_S3_CUSTOM_DOMAIN", "")
        if cdn_domain:
            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS(
                    f"Static files available at: https://{cdn_domain}/static/"
                )
            )
