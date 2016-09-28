# -*- coding: utf-8 -*-
from restorm.exceptions import RestServerException, RestValidationException
from restorm.patterns import ResourcePattern
from restorm.query import RestQuerySet


class ResourceManagerDescriptor(object):
    """
    This class ensures managers aren't accessible via model instances. For
    example, Book.objects works, but book_obj.objects raises AttributeError.
    """
    def __init__(self, manager):
        self.manager = manager

    def __get__(self, instance, type=None):
        if instance is not None:
            raise AttributeError(
                'Manager is not accessible via %s instances' % type.__name__)
        return self.manager


class ResourceManager(object):

    def __init__(self, queryset_class=None):
        if queryset_class is None:
            queryset_class = RestQuerySet
        self.queryset_class = queryset_class
        self.object_class = None

    @property
    def options(self):
        try:
            return getattr(self, '_options')
        except AttributeError:
            self._options = self.object_class._meta
            return self._options

    def get_queryset(self):
        queryset = self.queryset_class(
            model=self.object_class, client=self.options.client)
        return queryset

    def filter(self, **kwargs):
        queryset = self.get_queryset().filter(**kwargs)
        return queryset

    def all(self):
        queryset = self.get_queryset()
        return queryset

    def get(self, **kwargs):
        obj = self.get_queryset().get(**kwargs)
        return obj

    def using(self, client):
        return self.get_queryset().using(client)

    def order_by(self, *args):
        return self.get_queryset().order_by(*args)

    def create(self, **kwargs):
        """Send POST request to resource and return Resource instance."""
        rp = ResourcePattern.parse(self.options.list)
        absolute_url = rp.get_absolute_url(root=self.options.root)

        response = self.object_class.Meta.client.post(absolute_url, kwargs)

        # Although 201 is the best HTTP status code for a valid POST response.
        if response.status_code in [200, 201, 204]:
            if response.content:
                return self.object_class(
                    data=response.content, absolute_url=absolute_url,
                    client=self.object_class.Meta.client)
            else:
                return None
        elif response.status_code in [400]:
            raise RestValidationException('Cannot create "%s" (%d): %s' % (
                response.request.uri, response.status_code, response.content),
                response)
        else:
            raise RestServerException('Cannot create "%s" (%d): %s' % (
                response.request.uri, response.status_code, response.content))
