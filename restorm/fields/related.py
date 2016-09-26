from django import forms
from django.utils.functional import SimpleLazyObject, cached_property
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


class Relation(object):
    def __init__(
            self, field, to, related_name=None, limit_choices_to=None,
            parent_link=False, on_delete=None, related_query_name=None):
        self.field = field
        self.to = to
        self.related_name = related_name
        self.related_query_name = related_query_name
        self.limit_choices_to = {} if limit_choices_to is None else limit_choices_to  # NOQA
        self.multiple = True
        self.parent_link = parent_link
        self.on_delete = on_delete
        self.symmetrical = False


class ManyToOneRel(Relation):
    def __init__(
            self, field, to, field_name, related_name=None,
            limit_choices_to=None, parent_link=False, on_delete=None,
            related_query_name=None):
        super(ManyToOneRel, self).__init__(
            field, to, related_name=related_name,
            limit_choices_to=limit_choices_to, parent_link=parent_link,
            on_delete=on_delete, related_query_name=related_query_name)
        self.field_name = field_name

    def get_related_field(self):
        field = self.to._meta.get_field(self.field_name)
        if not field.concrete:
            raise FieldDoesNotExist(
                "No related field named '%s'" % self.field_name)
        return field


class RelatedResource(Field):
    relation_class = Relation

    def __init__(self, field, resource, get_itm_params=None, **kwargs):
        super(RelatedResource, self).__init__(**kwargs)
        self.is_relation = True
        if isinstance(resource, basestring):
            def lazy_resource(resource_str):
                def import_resource():
                    return import_string(resource_str)
                return SimpleLazyObject(import_resource)
            resource = lazy_resource(resource)
        self._resource = resource
        if get_itm_params is None:
            get_itm_params = _default_get_itm_params
        self._get_itm_params = get_itm_params

    @cached_property
    def rel(self):
        return self.relation_class(self, self._resource)

    @cached_property
    def _client(self):
        return self.rel.to._meta.client

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
                instance.data[self.attname], self.rel.to)

            if bool([True for v in itm_params.values() if v]) or (not self.blank and not self.null):
                itm = self.ret.to._default_manager.get(**itm_params)
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
    relation_class = ManyToOneRel

    @cached_property
    def rel(self):
        return self.relation_class(
            self, self._resource, self._resource._meta.pk.attname)

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

            itm_params_list = [
                self._get_itm_params(x, self.rel.to) for x in raw_data]
            related_list = [
                lazy_wrap(self.rel.to, itm_params)
                for itm_params in itm_params_list
            ]
            setattr(
                instance,
                '_cache_%s' % self.attname,
                related_list
            )

        return getattr(instance, '_cache_%s' % self.attname, None)

    def formfield(self, **kwargs):
        defaults = {
            'form_class': forms.TypedMultipleChoiceField,
            'choices': [[obj.pk, obj.__unicode__()] for obj in self.rel.to._default_manager.get_queryset()],  # NOQA
        }
        defaults.update(kwargs)
        return super(ToManyField, self).formfield(**defaults)
