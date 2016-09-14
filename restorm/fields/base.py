"""restorm resource fields."""


class Field(object):
    # Tracks each time a Field instance is created. Used to retain order.
    creation_counter = 0

    def __init__(self, **kwargs):
        self.default = kwargs.pop('default', None)
        self.required = kwargs.pop('required', True)
        self.editable = kwargs.pop('editable', True)
        self.verbose_name = kwargs.pop('verbose_name', None)

        # Increase the creation counter, and save our local copy.
        self.creation_counter = Field.creation_counter
        Field.creation_counter += 1

    def __get__(self, instance, instance_type=None):
        if instance is None:
            return self

        if not hasattr(instance, '_cache_%s' % self._field):
            try:
                value = instance.data[self._field]
            except KeyError:
                value = self.default

            setattr(instance, '_cache_%s' % self._field, value)

        return getattr(instance, '_cache_%s' % self._field, None)

    def clean(self, value):
        return value

    def __set__(self, instance, value):
        if instance is None:
            raise AttributeError(
                '%s must be accessed via instance' % self._field.name)
        if not self.editable:
            raise AttributeError('%s is not editable!')

        value = self.clean(instance, value)

        setattr(instance, '_cache_%s' % self._field, value)


class BooleanField(Field):
    def clean(self, value):
        return bool(value)


class IntegerField(Field):
    def clean(self, value):
        return int(value)


class CharField(Field):
    def __init__(self, **kwargs):
        self.max_length = kwargs.pop('max_length', None)
        self.choices = kwargs.pop('choices', None)
        super(CharField, self).__init__(**kwargs)

    def clean(self, value):
        return unicode(value)


class URLField(CharField):
    pass
