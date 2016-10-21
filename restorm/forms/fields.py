from django.forms.fields import TypedChoiceField


class ResourceChoiceField(TypedChoiceField):
    def __init__(self, queryset, **kwargs):
        kwargs['choices'] = self.curry_queryset_choices(queryset)
        super(ResourceChoiceField, self).__init__(**kwargs)

    def curry_queryset_choices(self, queryset):
        def get_queryset_choices():
            return [(obj.pk, unicode(obj)) for obj in queryset]
        return get_queryset_choices
