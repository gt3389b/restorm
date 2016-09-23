from django import forms
from django.utils.functional import SimpleLazyObject
from django.utils.module_loading import import_string

from restorm.exceptions import RestServerException

from .base import Field


def _default_get_itm_params(data, resource):
    if type(data) == dict:
        value = data[resource._meta.pk.attname]
    else:
        value = data
    return {
        resource._meta.pk.attname: value
    }


class RelatedResource(Field):
    def __init__(self, field, resource, get_itm_params=None, **kwargs):
        super(RelatedResource, self).__init__(**kwargs)
        self.is_relation = True
        self.attname = field
        self.name = field
        if isinstance(resource, basestring):
            def lazy_resource(resource_str):
                def import_resource():
                    return import_string(resource_str)
                return SimpleLazyObject(import_resource)
            self._resource = lazy_resource(resource)
        else:
            self._resource = resource
        if get_itm_params is None:
            get_itm_params = _default_get_itm_params
        self._get_itm_params = get_itm_params

    @property
    def _client(self):
        return self._resource._meta.client

    def _create_new_class(self, name):
        # FIXME: This will be a RestResource!
        from restorm.resources import Resource
        class_name = name.title().replace('_', '')
        return type(
            str('%sResource' % class_name),
            (Resource,),
            {'__module__': '%s.auto' % Resource.__module__}
        )

    def __get__(self, instance, instance_type=None):
        if instance is None:
            return self

        if not hasattr(instance, '_cache_%s' % self.attname):
            itm_params = self._get_itm_params(
                instance.data[self.attname], self._resource)

            if bool([True for v in itm_params.values() if v]) or (not self.blank and not self.null):
                itm = self._resource.objects.get(**itm_params)
            else:
                itm = None
            setattr(
                instance,
                '_cache_%s' % self.attname,
                itm
            )

        return getattr(instance, '_cache_%s' % self.attname, None)

    def __set__(self, instance, value):
        # FIXME : this doesn't work anymore
        if instance is None:
            raise AttributeError(
                '%s must be accessed via instance' % self.attname.name)

        if isinstance(value, dict):
            absolute_url = instance[self.attname]
            response = self._client.put(absolute_url, value)
            if response.status_code not in [200, 201, 304]:
                raise RestServerException('Cannot put "%s" (%d): %s' % (
                    absolute_url, response.status_code, response.content))

            resource_class = self._create_new_class(self.attname)
            setattr(instance, '_cache_%s' % self.attname, resource_class(
                value, client=self._client, absolute_url=absolute_url))
        else:
            setattr(instance, '_cache_%s' % self.attname, value)


class ToOneField(RelatedResource):
    def formfield(self, **kwargs):
        defaults = {
            'form_class': forms.TypedChoiceField,
            'choices': [[obj.pk, obj.__unicode__()] for obj in self._resource._default_manager.get_queryset()],
        }
        defaults.update(kwargs)
        return super(ToOneField, self).formfield(**defaults)

    def __get__(self, instance, instance_type=None):
        obj = super(ToOneField, self).__get__(instance=instance, instance_type=instance_type)
        if obj:
            return getattr(obj, obj._meta.pk.attname, obj)
        return None


class ToManyField(RelatedResource):
    def __get__(self, instance, instance_type=None):
        if instance is None:
            return self

        if not hasattr(instance, '_cache_%s' % self.attname):
            raw_data = instance.data[self.attname]

            def lazy_wrap(resource, itm_params):
                def get_obj():
                    return resource.objects.get(**itm_params)
                return SimpleLazyObject(get_obj)

            itm_params_list = [self._get_itm_params(x, self._resource) for x in raw_data]
            related_list = [
                lazy_wrap(self._resource, itm_params)
                for itm_params in itm_params_list
            ]
            setattr(
                instance,
                '_cache_%s' % self.attname,
                related_list
            )

        return getattr(instance, '_cache_%s' % self.attname, None)
