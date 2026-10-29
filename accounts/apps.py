from django.apps import AppConfig
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import post_migrate


def ensure_dev_admin(sender, **kwargs):
    # Only auto-create this account in local development.
    if not getattr(settings, 'DEBUG', False):
        return

    user_model = get_user_model()
    admin_user, created = user_model.objects.get_or_create(
        username='admin',
        defaults={
            'email': 'admin@example.com',
            'is_staff': True,
            'is_superuser': True,
        },
    )
    admin_user.email = admin_user.email or 'admin@example.com'
    admin_user.is_staff = True
    admin_user.is_superuser = True
    admin_user.set_password('admin')
    admin_user.save()

    profile = getattr(admin_user, 'profile', None)
    if profile:
        profile.role = 'ADMIN'
        profile.approved = True
        profile.save()


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        # Register setup hook without touching the database at startup.
        post_migrate.connect(ensure_dev_admin, sender=self)
