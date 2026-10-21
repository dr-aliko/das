from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateFileSystemStorage(FileSystemStorage):
    """Stores files outside MEDIA_ROOT so nginx/whitenoise never serves them."""

    def __init__(self, **kwargs):
        kwargs.setdefault('location', str(settings.PRIVATE_MEDIA_ROOT))
        kwargs.setdefault('base_url', None)
        super().__init__(**kwargs)

    def url(self, name):
        raise ValueError('Private files must be served through a protected Django view.')
