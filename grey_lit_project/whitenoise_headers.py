"""Custom WhiteNoise headers for font and static asset caching."""

# Font file extensions that benefit from immutable Cache-Control
_FONT_EXTENSIONS = frozenset((".woff", ".woff2", ".ttf", ".otf", ".eot"))


def add_headers(headers, path, url):
    """Add Cache-Control: immutable for font files served by WhiteNoise.

    Font files are hashed by CompressedManifestStaticFilesStorage, so they
    can safely be marked immutable to prevent conditional revalidation requests.
    """
    if any(path.endswith(ext) for ext in _FONT_EXTENSIONS):
        headers["Cache-Control"] = "public, max-age=31536000, immutable"
