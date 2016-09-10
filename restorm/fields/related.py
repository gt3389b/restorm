from restorm.exceptions import RestServerException
from .base import Field


def _default_get_itm_params(instance, field, resource):
    value = instance.__dict__['data'][field][resource._meta.pk.attname]
    return {
        resource._meta.pk.attname: value
    }


class RelatedResource(Field):
    def __init__(self, field, resource, get_itm_params=None, **kwargs):
        super(RelatedResource, self).__init__(**kwargs)
        self._field = field
        self._resource = resource
        self._client = resource._meta.client
        if get_itm_params is None:
            get_itm_params = _default_get_itm_params
        self._get_itm_params = get_itm_params

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

        if not hasattr(instance, '_cache_%s' % self._field):
            itm_params = self._get_itm_params(
                instance, self._field, self._resource)
            itm = self._resource.objects.get(**itm_params)
            setattr(
                instance,
                '_cache_%s' % self._field,
                itm
            )

        return getattr(instance, '_cache_%s' % self._field, None)

    def __set__(self, instance, value):
        if instance is None:
            raise AttributeError(
                '%s must be accessed via instance' % self._field.name)

        if isinstance(value, dict):
            absolute_url = instance[self._field]
            response = self._client.put(absolute_url, value)
            if response.status_code not in [200, 201, 304]:
                raise RestServerException('Cannot put "%s" (%d): %s' % (
                    absolute_url, response.status_code, response.content))

            resource_class = self._create_new_class(self._field)
            setattr(instance, '_cache_%s' % self._field, resource_class(
                value, client=self._client, absolute_url=absolute_url))
        else:
            setattr(instance, '_cache_%s' % self._field, value)
