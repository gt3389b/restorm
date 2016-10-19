from collections import OrderedDict
import sys

from django.apps import apps
from django.apps.config import MODELS_MODULE_NAME
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
# from django.utils.text import camel_case_to_spaces
# from django.utils import six

from restorm.conf import settings
from restorm.exceptions import RestServerException, RestValidationException
# from restorm.rest import restify
from restorm.fields import Field, ToOneField, ToManyField
from restorm.managers import ResourceManager, ResourceManagerDescriptor
from restorm.patterns import ResourcePattern


class ResourceOptions(object):
    DEFAULT_NAMES = (
        'list', 'item', 'root', 'app_label', 'resource_name', 'verbose_name',
        'client', 'app_config', 'page_size', 'page_size_param')

    def __init__(self, meta, app_label=None):
        # Represents this Resource's list URI pattern. For example: A list of
        # objects can be found at http://localhost/api/book/.
        self.list = ''

        # Represents this Resource's item URI pattern. For example: A single
        # object of this resource can be found at http://localhost/api/book/1.
        self.item = ''

        # Indicates the root of the resource. In some cases, a resource is
        # found on a different domain or service. For example: If the regular
        # resource can be found on http://localhost/api/ the search engine
        # might be found on http://search.localhost/api/. If so, set root to
        # this different URL.
        self.root = ''

        self.page_size = None
        self.page_size_param = None

        # Lets make Django think this is an actual Model
        self._get_fields_cache = {}
        self.proxied_children = []
        self.local_fields = []
        self.local_many_to_many = []
        self.virtual_fields = []
        self.many_to_many = []
        self._verbose_name = None
        self._verbose_name_plural = None
        # self.db_table = ''
        self.ordering = []
        self.default_permissions = ('add', 'change', 'delete')
        self.permissions = []
        self.app_label = app_label
        self.get_latest_by = None
        self.order_with_respect_to = None
        # self.db_tablespace = settings.DEFAULT_TABLESPACE
        self.meta = meta

        self.has_auto_field = False
        self.auto_field = None
        self.abstract = False
        self.managed = True
        self.proxy = False
        self.proxy_for_model = None
        self.concrete_model = None
        self.swappable = False
        self.swapped = False
        self.parents = OrderedDict()
        self.auto_created = False

        self.managers = []

        self.related_fkey_lookups = []

        self.apps = apps

        self.default_related_name = None

        self.client = None

        # Next, apply any overridden values from 'class Meta'.
        # TODO: This might be a good place to store ResourcePatterns.
        if meta:
            meta_attrs = meta.__dict__.copy()
            for name in meta.__dict__:
                # Ignore any private attributes that Django doesn't care about.
                # NOTE: We can't modify a dictionary's contents while looping
                # over it, so we loop over the *original* dictionary instead.
                if name.startswith('_'):
                    del meta_attrs[name]
            for attr_name in self.DEFAULT_NAMES:
                if attr_name in meta_attrs:
                    value = meta_attrs.pop(attr_name)
                    try:
                        setattr(self, attr_name, value)
                    except AttributeError:
                        setattr(self, "_{}".format(attr_name), value)
                elif hasattr(meta, attr_name):
                    setattr(self, attr_name, getattr(meta, attr_name))
        if self.client is None:
            self.client = settings.DEFAULT_CLIENT

    @property
    def model_name(self):
        return getattr(self, 'resource_name', None)

    @property
    def object_name(self):
        return self.model_name

    @property
    def verbose_name(self):
        if not self._verbose_name:
            self._verbose_name = self.model_name
        return self._verbose_name

    @property
    def verbose_name_plural(self):
        return "{}s".format(self.verbose_name)

    def get_field(self, field):
        try:
            field = self._fields[field]
        except KeyError:
            raise FieldDoesNotExist
        return field

    @property
    def fields(self):
        return self._fields.values()

    def get_fields(self, include_hidden=False):
        fields = self._fields.copy()
        return fields

    def get_parent_list(self):
        return []

    @property
    def pk(self):
        return self._fields[self._pk_attr]


class ResourceBase(type):
    """
    Meta class for Resource. This class ensures that Resource classes (not
    instances) are magically prepared.
    """

    def __new__(cls, name, bases, attrs):
        super_new = super(ResourceBase, cls).__new__
        parents = [b for b in bases if isinstance(b, ResourceBase)]
        if not parents:
            # If this isn't a subclass of RestObject, don't do anything
            # special.
            return super_new(cls, name, bases, attrs)

        attrs['__ordered__'] = [
            key for key in attrs.keys() if key not in (
                '__module__', '__qualname__')]

        current_fields = []
        for key, value in list(attrs.items()):
            if isinstance(value, Field):
                if getattr(value, 'attname', None) is None:
                    # setattr(value, '_field', key)
                    setattr(value, 'attname', key)
                    setattr(value, 'name', key)
                current_fields.append((key, value))
                attrs.pop(key)
        current_fields.sort(key=lambda x: x[1].creation_counter)
        attrs['declared_fields'] = OrderedDict(current_fields)

        new_class = super_new(cls, name, bases, attrs)

        # Create the meta class.
        attr_meta = attrs.pop('Meta', None)
        if not attr_meta:
            meta = getattr(new_class, 'Meta', None)
        else:
            meta = attr_meta
        # base_meta = getattr(new_class, '_meta', None)

        module = attrs.pop('__module__')
        app_config = apps.get_containing_app_config(module)
        setattr(meta, 'app_config', app_config)

        if getattr(meta, 'app_label', None) is None:

            if app_config is None:

                model_module = sys.modules[new_class.__module__]
                package_components = model_module.__name__.split('.')
                # find the last occurrence of 'models'
                package_components.reverse()
                try:
                    app_label_index = package_components.index(
                        MODELS_MODULE_NAME) + 1
                except ValueError:
                    app_label_index = 1
                try:
                    kwargs = {"app_label": package_components[app_label_index]}
                except IndexError:
                    raise ImproperlyConfigured(
                        'Unable to detect the app label for model "%s." '
                        'Ensure that its module, "%s", is located inside an '
                        'installed app.' % (
                            new_class.__name__, model_module.__name__)
                    )
            else:
                kwargs = {"app_label": app_config.label}

        else:
            kwargs = {}

        setattr(new_class, '_meta', ResourceOptions(meta, **kwargs))

        # Assign manager.
        manager = attrs.pop('objects', None)
        if manager is None:
            manager = ResourceManager()
        manager.object_class = new_class

        # Wrap default or custom managers such that it can only be used on
        # classes and not on instances.
        new_class.objects = ResourceManagerDescriptor(manager)

        # Walk through the MRO.
        declared_fields = OrderedDict()
        for base in reversed(new_class.__mro__):
            # Collect fields from base class.
            if hasattr(base, 'declared_fields'):
                declared_fields.update(base.declared_fields)

            # Field shadowing.
            for attr, value in base.__dict__.items():
                if value is None and attr in declared_fields:
                    declared_fields.pop(attr)
        primary_key = None
        for attr, value in declared_fields.items():
            setattr(new_class, attr, value)
            if value.primary_key:
                if primary_key is not None:
                    raise ImproperlyConfigured('Multiple primary keys.')
                else:
                    primary_key = value
                    setattr(new_class._meta, '_pk_attr', attr)
        new_class.base_fields = declared_fields
        new_class.declared_fields = declared_fields

        setattr(new_class._meta, '_fields', declared_fields)
        setattr(new_class._meta, 'concrete_fields', declared_fields)
        setattr(new_class._meta, 'concrete_model', new_class)
        setattr(new_class, 'DoesNotExist', RestServerException)

        class State:
            db = new_class._meta.client
            adding = False

        setattr(new_class, '_state', State())

        return new_class

    @property
    def _default_manager(self):
        return self.objects


class ResourceList(list):
    """
    A list of ``Resource`` instances which are most likely incomplete compared
    to when they are retrieved as an individual.
    """
    def __init__(self, data, **kwargs):
        self.client = kwargs.pop('client', None)
        self.absolute_url = kwargs.pop('absolute_url', None)

        super(ResourceList, self).__init__(
            [Resource(item, self.client) for item in data])


class Resource(object):
    """
    Class that holds information about a resource.

    It has a manager to retrieve and/or manipulate the state of a resource.
    """
    __metaclass__ = ResourceBase

    objects = None

    def __init__(self, data={}, client=None, absolute_url=None):
        self.client = client or self._meta.client
        self.absolute_url = absolute_url
        assert type(data) == dict, (type(data), data)
        self.data = data.copy()
        if self.absolute_url is None and self._meta.pk.attname not in self.data:
            self._state.adding = True
        self._item_pattern = ResourcePattern.parse(self._meta.item)
        self._list_pattern = ResourcePattern.parse(self._meta.list)

    def __unicode__(self):
        return unicode(self.absolute_url)

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self.__unicode__())

    def _get_pk_val(self):
        try:
            return self.data[self._meta.pk.attname]
        except:
            return getattr(self.data, self._meta.pk.attname)

    def _get_unique_checks(self, exclude=None):
        return [], []

    @property
    def pk(self):
        if getattr(self._meta, '_pk_attr', 'id'):
            return getattr(self, self._meta._pk_attr, None)

    def serializable_value(self, name):
        return getattr(self, name, None)

    def full_clean(self, *args, **kwargs):
        pass

    def validate_unique(self, *args, **kwargs):
        pass

    def _clean_request_data(self):
        obj_data = self.data.copy()
        for key, value in self.data.items():
            try:
                field = self._meta.get_field(key)
            except FieldDoesNotExist:
                del obj_data[key]
                continue
            if value and isinstance(field, ToOneField):
                value = value.pk
            if value and isinstance(field, ToManyField):
                if field.rel.through is None:
                    value = [o.pk for o in value]
                else:
                    del obj_data[key]
                    continue
            obj_data[key] = value
        return obj_data

    def save(self, commit=True):
        """
        Performs a PUT request to update the object.

        No guarantees are given to what this method actually returns due to the
        freedom of API implementations. If there is a body in the response, the
        contents of this body is returned, otherwise ``None``.
        """
        obj_data = self._clean_request_data()
        if not commit:
            return
        if not self.absolute_url:
            created = True
            absolute_url = self._list_pattern.get_absolute_url(
                root=self._meta.root)
            response = self.client.post(absolute_url, obj_data)
        else:
            created = False
            absolute_url = self.absolute_url
            response = self.client.put(self.absolute_url, obj_data)

        # Although 204 is the best HTTP status code for a valid PUT response.
        if response.status_code in [200, 201, 204]:
            if response.content and isinstance(response.content, dict):
                self.data = response.content
                pk_attr = self._meta.pk.attname
                if not self.absolute_url:
                    self.absolute_url = self._item_pattern.get_absolute_url(
                        root=self._meta.root, **{pk_attr: self.data[pk_attr]})
            return created
        elif response.status_code in [400]:
            raise RestValidationException('Cannot save "%s" (%d): %s' % (
                response.request.uri, response.status_code, response.content),
                response)
        else:
            raise RestServerException('Cannot save "%s" (%d): %s' % (
                response.request.uri, response.status_code, response.content))

    def delete(self):
        """
        Performs a DELETE request to delete the object.

        No guarantees are given to what this method actually returns due to the
        freedom of API implementations. If there is a body in the response, the
        contents of this body is returned, otherwise ``None``.
        """

        response = self.client.delete(self.absolute_url)

        # Although 204 is the best HTTP status code for a valid PUT response.
        if response.status_code in [200, 201, 204]:
            if response.content:
                return response.content
            else:
                return None
        elif response.status_code in [400]:
            raise RestValidationException('Cannot delete "%s" (%d): %s' % (
                response.request.uri, response.status_code, response.content),
                response)
        else:
            raise RestServerException('Cannot delete "%s" (%d): %s' % (
                response.request.uri, response.status_code, response.content))


class SimpleResource(object):
    """
    Class that holds information about a resource.

    It has a manager to retrieve and/or manipulate the state of a resource.
    """
    __metaclass__ = ResourceBase

    objects = None

    def __init__(self, data=None, client=None, absolute_url=None):
        self.client = client
        self.absolute_url = absolute_url

        self.data = data

    def __unicode__(self):
        return self.absolute_url

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self.__unicode__())

    def save(self):
        self.client.put(self.absolute_url, self.data)
