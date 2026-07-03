"""
DigitalOcean Spaces configuration module for CDN and static files.

This module provides centralized configuration for:
- Static files storage via Spaces (S3-compatible)
- Media files storage
- CDN distribution
- Cache optimization
"""

from decouple import config


def get_spaces_config():
    """
    Get DigitalOcean Spaces configuration for django-storages.

    Returns:
        dict: Spaces storage configuration or None if not configured
    """
    # Check if Spaces is configured
    access_key = config("SPACES_ACCESS_KEY", default="")
    secret_key = config("SPACES_SECRET_KEY", default="")
    bucket_name = config("SPACES_BUCKET_NAME", default="")
    region = config("SPACES_REGION", default="nyc3")

    if not all([access_key, secret_key, bucket_name]):
        return None

    # Base endpoint URL
    endpoint_url = f"https://{region}.digitaloceanspaces.com"

    # CDN endpoint (if configured)
    cdn_domain = config("SPACES_CDN_DOMAIN", default="")

    return {
        # AWS S3 settings (Spaces is S3-compatible)
        "AWS_ACCESS_KEY_ID": access_key,
        "AWS_SECRET_ACCESS_KEY": secret_key,
        "AWS_STORAGE_BUCKET_NAME": bucket_name,
        "AWS_S3_ENDPOINT_URL": endpoint_url,
        "AWS_S3_REGION_NAME": region,
        # Use CDN domain if available, otherwise use Spaces endpoint
        "AWS_S3_CUSTOM_DOMAIN": (
            cdn_domain
            if cdn_domain
            else f"{bucket_name}.{region}.digitaloceanspaces.com"
        ),
        # File settings
        "AWS_DEFAULT_ACL": "public-read",  # Make files publicly readable
        "AWS_S3_OBJECT_PARAMETERS": {
            "CacheControl": "max-age=86400",  # 1 day browser cache
            "Expires": "Thu, 31 Dec 2099 20:00:00 GMT",  # Far future expiry
        },
        # Performance optimizations
        "AWS_IS_GZIPPED": True,  # Enable gzip compression
        "AWS_S3_FILE_OVERWRITE": True,  # Overwrite files with same name
        "AWS_S3_USE_SSL": True,  # Always use HTTPS
        "AWS_S3_VERIFY": True,  # Verify SSL certificates
        "AWS_QUERYSTRING_AUTH": False,  # Don't add auth to URLs (public files)
        # Connection settings
        "AWS_S3_CONNECTION_TIMEOUT": 20,
        "AWS_S3_MAX_MEMORY_SIZE": 100 * 1024 * 1024,  # 100MB
        # Storage classes
        "STATICFILES_STORAGE": "apps.core.spaces_config.StaticStorage",
        "DEFAULT_FILE_STORAGE": "apps.core.spaces_config.MediaStorage",
    }


def get_static_storage_config():
    """
    Get configuration specifically for static files.

    Returns:
        dict: Static files storage configuration
    """
    base_config = get_spaces_config()
    if not base_config:
        return None

    # Static files specific settings
    static_config = base_config.copy()
    static_config.update(
        {
            "AWS_LOCATION": "static",  # Store static files in 'static/' prefix
            "STATIC_URL": f"https://{base_config['AWS_S3_CUSTOM_DOMAIN']}/static/",
            # Optimize cache for static files
            "AWS_S3_OBJECT_PARAMETERS": {
                "CacheControl": "public, max-age=31536000, immutable",  # 1 year cache
                "Expires": "Thu, 31 Dec 2099 20:00:00 GMT",
            },
        }
    )

    return static_config


def get_media_storage_config():
    """
    Get configuration specifically for media files.

    Returns:
        dict: Media files storage configuration
    """
    base_config = get_spaces_config()
    if not base_config:
        return None

    # Media files specific settings
    media_config = base_config.copy()
    media_config.update(
        {
            "AWS_LOCATION": "media",  # Store media files in 'media/' prefix
            "MEDIA_URL": f"https://{base_config['AWS_S3_CUSTOM_DOMAIN']}/media/",
            # Shorter cache for media files (they might change)
            "AWS_S3_OBJECT_PARAMETERS": {
                "CacheControl": "public, max-age=3600",  # 1 hour cache
            },
            # Media files should be private by default
            "AWS_DEFAULT_ACL": config("MEDIA_FILES_PRIVATE", default=False, cast=bool)
            and "private"
            or "public-read",
        }
    )

    return media_config


# Custom storage classes
try:  # noqa: C901 - Storage class initialization
    from storages.backends.s3boto3 import S3Boto3Storage

    class StaticStorage(S3Boto3Storage):
        """Custom storage class for static files."""

        location = "static"
        default_acl = "public-read"
        file_overwrite = True

        def __init__(self, *args, **kwargs):
            config = get_static_storage_config()
            if config:
                for key, value in config.items():
                    if hasattr(self, key.lower().replace("aws_", "")):
                        setattr(self, key.lower().replace("aws_", ""), value)
            super().__init__(*args, **kwargs)

    class MediaStorage(S3Boto3Storage):
        """Custom storage class for media files."""

        location = "media"
        file_overwrite = False  # Don't overwrite media files

        def __init__(self, *args, **kwargs):
            config = get_media_storage_config()
            if config:
                for key, value in config.items():
                    if hasattr(self, key.lower().replace("aws_", "")):
                        setattr(self, key.lower().replace("aws_", ""), value)
            super().__init__(*args, **kwargs)

    class PrivateMediaStorage(S3Boto3Storage):
        """Custom storage class for private media files."""

        location = "private"
        default_acl = "private"
        file_overwrite = False
        custom_domain = False  # Don't use CDN for private files
        querystring_auth = True  # Add auth to URLs
        querystring_expire = 300  # URLs expire after 5 minutes

except ImportError:
    # Fallback if django-storages is not installed
    StaticStorage = None  # type: ignore[assignment]
    MediaStorage = None  # type: ignore[assignment]
    PrivateMediaStorage = None  # type: ignore[assignment]


def check_spaces_connection():
    """
    Check if DigitalOcean Spaces is accessible.

    Returns:
        tuple: (bool, str) - (is_connected, message)
    """
    try:
        import boto3.session
        from botocore.exceptions import ClientError, NoCredentialsError
    except ImportError:
        return False, "boto3 library not installed"

    config_dict = get_spaces_config()
    if not config_dict:
        return False, "Spaces not configured (missing credentials)"

    try:
        # Create S3 client
        session = boto3.session.Session()
        client = session.client(
            "s3",
            region_name=config_dict["AWS_S3_REGION_NAME"],
            endpoint_url=config_dict["AWS_S3_ENDPOINT_URL"],
            aws_access_key_id=config_dict["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=config_dict["AWS_SECRET_ACCESS_KEY"],
        )

        # Try to list objects (limited to 1 for speed)
        bucket_name = config_dict["AWS_STORAGE_BUCKET_NAME"]
        response = client.list_objects_v2(Bucket=bucket_name, MaxKeys=1)

        # Get bucket region and size
        bucket_location = client.get_bucket_location(Bucket=bucket_name)
        region = bucket_location.get("LocationConstraint", "unknown")

        # Count total objects (up to 1000 for performance)
        total_objects = response.get("KeyCount", 0)

        return (
            True,
            f"Spaces connected. Bucket: {bucket_name}, Region: {region}, Objects: {total_objects}",
        )

    except NoCredentialsError:
        return False, "Invalid Spaces credentials"
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "NoSuchBucket":
            return False, f"Bucket '{bucket_name}' does not exist"
        elif error_code == "AccessDenied":
            return False, "Access denied to Spaces bucket"
        else:
            return False, f"Spaces error: {error_code}"
    except Exception as e:
        return False, f"Unexpected error checking Spaces: {str(e)}"


# Cache control settings for different file types
CACHE_CONTROL_SETTINGS = {
    # Static assets - cache for 1 year
    "css": "public, max-age=31536000, immutable",
    "js": "public, max-age=31536000, immutable",
    "woff": "public, max-age=31536000, immutable",
    "woff2": "public, max-age=31536000, immutable",
    "ttf": "public, max-age=31536000, immutable",
    "eot": "public, max-age=31536000, immutable",
    # Images - cache for 1 month
    "jpg": "public, max-age=2592000",
    "jpeg": "public, max-age=2592000",
    "png": "public, max-age=2592000",
    "gif": "public, max-age=2592000",
    "webp": "public, max-age=2592000",
    "svg": "public, max-age=2592000",
    "ico": "public, max-age=2592000",
    # Documents - cache for 1 week
    "pdf": "public, max-age=604800",
    "doc": "public, max-age=604800",
    "docx": "public, max-age=604800",
    "xls": "public, max-age=604800",
    "xlsx": "public, max-age=604800",
    # Other - cache for 1 day
    "default": "public, max-age=86400",
}


def get_cache_control_for_file(filename):
    """
    Get optimal cache control header for a file based on its extension.

    Args:
        filename: Name of the file

    Returns:
        str: Cache-Control header value
    """
    import os

    # Get file extension
    _, ext = os.path.splitext(filename)
    ext = ext.lower().lstrip(".")

    # Return appropriate cache control
    return CACHE_CONTROL_SETTINGS.get(ext, CACHE_CONTROL_SETTINGS["default"])
