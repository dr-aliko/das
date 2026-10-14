from whitenoise.storage import CompressedManifestStaticFilesStorage


class ManifestStorage(CompressedManifestStaticFilesStorage):
    # Prevents 500s when a template (e.g. third-party admin override or a
    # missing icon reference) asks for a file that was not collected.
    # The unhashed URL is returned instead of raising ValueError.
    manifest_strict = False
