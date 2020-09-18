import django
from django.apps import apps, AppConfig
from django.contrib.auth.management import _get_all_permissions
from django.core import exceptions
from django.db import DEFAULT_DB_ALIAS, router
from django.db.models.signals import post_migrate
from django.utils import six


def update_ctypes_permissions(app_config, verbosity=2, interactive=True,
                              using=DEFAULT_DB_ALIAS, **kwargs):
    """
    Creates resources content types and default permissions.

    Most bits taken from contenttypes.management.update_contenttypes
    and auth.management.create_permissions.

    This will not make any attempt to clear content types no longer
    associated to resources.

    Note:
    -----
    Because content types will not remain associated with real models,
    Django will ask to remove them after every migration.
    Although this function will recreate them, model instances with
    non-weak relations to them will be also deleted by the cascade,
    so for the time being is better to say "no" asked to remove stale
    content types.

    TODO: This *may* be addressed/mitigated defining a database
    router with a defined allow_migrate() method that checks the app
    against ContentType; e.g.:

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if <this app_label comes from a restorm app>:
            # don't allow the migration
            # (although maybe it's worth checking mode_name)
            return False
        # no opinion (let other routers decide)
        return None

    see
    docs.djangoproject.com/en/1.8/topics/db/multi-db/#allow_migrate

    """
    if not isinstance(app_config, RestormAppConfig):
        # Any model will end up here, we are only interested in
        # restorm resources.
        return

    if not app_config.models_module:
        # This is left here for compatibility with Django.
        # Works because restorm resources are defined in the models.py.
        return

    try:
        ContentType = apps.get_model('contenttypes', 'ContentType')
        Permission = apps.get_model('auth', 'Permission')
    except LookupError:
        return

    if not router.allow_migrate_model(using, ContentType) \
            or not router.allow_migrate_model(using, Permission):
        return

    ContentType.objects.clear_cache()

    app_label = app_config.label
    app_resources = {resource._meta.resource_name: resource
                     for resource in app_config.get_resources()}

    if not app_resources:
        return

    # Get all the content types for this app
    content_types = {
        ct.model: ct
        for ct in ContentType.objects.using(using).filter(app_label=app_label)
    }

    # Create in memory any missing content type
    cts = [ContentType(app_label=app_label, model=resources_name)
           for (resources_name, resource) in six.iteritems(app_resources)
           if resources_name not in content_types]

    # Bulk-create the new instances
    ContentType.objects.using(using).bulk_create(cts)
    if verbosity >= 2:
        msg = "Adding content type '{0.app_label} | {0.model}' (restorm)".format
        for ct in cts:
            print(msg(ct))

    # This will hold the permissions we're looking for as
    # (content_type, (codename, name))
    searched_perms = list()
    # The codenames and ctypes that should exist.
    ctypes = set()

    for klass in app_resources.values():
        # Force looking up the content types in the current database
        # before creating foreign keys to them.
        ctype = ContentType.objects.db_manager(using).get_for_model(klass)
        ctypes.add(ctype)
        for perm in _get_all_permissions(klass._meta, ctype):
            searched_perms.append((ctype, perm))

    # Find all the Permissions that have a content_type for a resource we're
    # looking for.  We don't need to check for codenames since we already have
    # a list of the ones we're going to create.
    all_perms = set(Permission.objects.using(using).filter(
        content_type__in=ctypes,
    ).values_list(
        "content_type", "codename"
    ))

    perms = [
        Permission(codename=codename, name=name, content_type=ct)
        for ct, (codename, name) in searched_perms
        if (ct.pk, codename) not in all_perms
    ]
    # Validate the permissions before bulk_creation to avoid cryptic
    # database error when the verbose_name is longer than 50 characters.
    permission_name_max_length = Permission._meta.get_field('name').max_length
    verbose_name_max_length = permission_name_max_length - 11  # len('Can change ') prefix
    for perm in perms:
        if len(perm.name) > permission_name_max_length:
            raise exceptions.ValidationError(
                "The verbose_name of %s.%s is longer than %s characters" % (
                    perm.content_type.app_label,
                    perm.content_type.model,
                    verbose_name_max_length,
                )
            )
    Permission.objects.using(using).bulk_create(perms)
    if verbosity >= 2:
        for perm in perms:
            print("Adding permission '%s' (restorm)" % perm)


class RestormAppConfig(AppConfig):
    """
    A custom AppConfig for Restorm resources.

    """
    # Automatically recreate missing content types and permissions
    # for resources in this app after each migration.
    auto_create_permissions = True

    def get_resources(self):
        """
        Returns an iterable of this app's restorm resources.
        """
        # Probably not required, but checking Django models for consistency.
        self.check_models_ready()
        from .registry import registry

        for resource in registry.all_resources[self.label].values():
            yield resource

    def ready(self):
        """
        Sets the signal handler for creating content types.
        Needs to be called by overriding subclasses.
        """
        if self.auto_create_permissions:
            post_migrate.connect(update_ctypes_permissions)

class RestormAppSetup():
    django.setup()
