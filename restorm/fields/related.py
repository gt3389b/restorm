from django import forms
from django.utils.functional import SimpleLazyObject, cached_property
from django.utils.module_loading import import_string
from django.db.models import FieldDoesNotExist

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
        self.multiple = False
        self.parent_link = parent_link
        self.on_delete = on_delete
        self.symmetrical = False

    def get_accessor_name(self, model=None):
        opts = model._meta if model else self.to._meta
        model = model or self.to
        if self.multiple:
            if self.symmetrical and model == self.to:
                return None
        if self.related_name:
            return self.related_name
        if opts.default_related_name:
            return opts.default_related_name % {
                'model_name': opts.model_name.lower(),
                'app_label': opts.app_label.lower(),
            }
        return opts.model_name + ('_set' if self.multiple else '')


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


class ManyToManyRel(Relation):
    def __init__(
            self, field, to, field_name, through=None, related_name=None,
            limit_choices_to=None, parent_link=False, on_delete=None,
            related_query_name=None):
        super(ManyToManyRel, self).__init__(
            field, to, related_name=related_name,
            limit_choices_to=limit_choices_to, parent_link=parent_link,
            on_delete=on_delete, related_query_name=related_query_name)
        self.multiple = True
        self.field_name = field_name
        self.through = through

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

    # def __get__(self, instance, instance_type=None):
    #     if instance is None:
    #         return self
    #
    #     if not hasattr(instance, '_cache_%s' % self.attname):
    #         itm_params = self._get_itm_params(
    #             instance.data[self.attname], self.rel.to)
    #
    #         if bool([True for v in itm_params.values() if v]) or (not self.blank and not self.null):
    #             itm = self.ret.to._default_manager.get(**itm_params)
    #         else:
    #             itm = None
    #         setattr(
    #             instance,
    #             '_cache_%s' % self.attname,
    #             itm
    #         )
    #
    #     return getattr(instance, '_cache_%s' % self.attname, None)

    def __set__(self, instance, value):
        if instance is None:
            raise AttributeError(
                '%s must be accessed via instance' % self.attname.name)

        itm_params = self._get_itm_params(value, self.rel.to)
        if bool([True for v in itm_params.values() if v]):
            def lazy_wrap(resource, itm_params):
                def get_obj():
                    return resource._default_manager.get(**itm_params)
                return SimpleLazyObject(get_obj)

            itm = lazy_wrap(self.rel.to, itm_params)
        else:
            itm = value

        instance.data[self.attname] = itm


class ToOneField(RelatedResource):
    relation_class = ManyToOneRel

    @cached_property
    def rel(self):
        return self.relation_class(
            self, self._resource, self._resource._meta.pk.attname)

    def formfield(self, **kwargs):
        defaults = {
            'form_class': forms.TypedChoiceField,
            'choices': SimpleLazyObject(lambda: [[obj.pk, obj.__unicode__()] for obj in self.rel.to._default_manager.get_queryset()]),
        }
        defaults.update(kwargs)
        return super(ToOneField, self).formfield(**defaults)

    # def __get__(self, instance, instance_type=None):
    #     obj = super(ToOneField, self).__get__(instance=instance, instance_type=instance_type)
    #     if obj:
    #         return getattr(obj, obj._meta.pk.attname, obj)
    #     return None
    def save_form_data(self, instance, data):
        # Important: None means "no change", other false value means "clear"
        # This subtle distinction (rather than a more explicit marker) is
        # needed because we need to consume values that are also sane for a
        # regular (non Model-) Form to find in its cleaned_data dictionary.
        # assert False, data
        if data is not None:
            # This value will be converted to unicode and stored in the
            # database, so leaving False as-is is not acceptable.
            if not data:
                data = ''
            setattr(instance, self.name, data)


class ToManyField(RelatedResource):
    relation_class = ManyToManyRel

    def __init__(self, *args, **kwargs):
        through = kwargs.pop('through', None)
        if through and isinstance(through, basestring):
            def lazy_resource(resource_str):
                def import_resource():
                    return import_string(resource_str)
                return SimpleLazyObject(import_resource)
            through = lazy_resource(through)
        self._through = through
        return super(ToManyField, self).__init__(*args, **kwargs)

    @cached_property
    def rel(self):
        return self.relation_class(
            self,
            self._resource,
            self._resource._meta.pk.attname,
            through=self._through)

    def __set__(self, instance, value):
        if instance is None:
            raise AttributeError(
                '%s must be accessed via instance' % self.attname.name)

        itm_params_list = [
            self._get_itm_params(x, self.rel.to) for x in value]

        if value and itm_params_list:
            def lazy_wrap(resource, itm_params):
                def get_obj():
                    return resource._default_manager.get(**itm_params)
                return SimpleLazyObject(get_obj)

            related_list = [
                lazy_wrap(self.rel.to, itm_params)
                for itm_params in itm_params_list
            ]
        else:
            related_list = []

        instance.data[self.attname] = related_list

    def formfield(self, **kwargs):
        defaults = {
            'form_class': forms.TypedMultipleChoiceField,
            'choices': SimpleLazyObject(lambda: [[obj.pk, obj.__unicode__()] for obj in self.rel.to._default_manager.get_queryset()]),  # NOQA
        }
        defaults.update(kwargs)
        if defaults.get('initial') is not None:
            initial = defaults['initial']
            if callable(initial):
                initial = initial()
            defaults['initial'] = [i._get_pk_val() for i in initial]
        return super(ToManyField, self).formfield(**defaults)
