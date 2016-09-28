"""restorm resource fields."""
from decimal import Decimal
import json
try:
    from django.utils import six
except ImportError:
    import six

from django import forms
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.utils.encoding import smart_text
from django.utils.text import capfirst
from jsonfield.encoder import JSONEncoder
from jsonfield.fields import JSONFormField

BLANK_CHOICE_DASH = [("", "---------")]


class NOT_PROVIDED:
    pass


class Field(object):
    # Tracks each time a Field instance is created. Used to retain order.
    creation_counter = 0
    empty_strings_allowed = True

    def __init__(self, **kwargs):
        self.primary_key = kwargs.pop('primary_key', False)
        self.default = kwargs.pop('default', None)
        self.null = kwargs.pop('null', False)
        self.blank = kwargs.pop('blank', False)
        self.editable = kwargs.pop('editable', True)
        self._verbose_name = kwargs.pop('verbose_name', None)
        self.help_text = kwargs.pop('help_text', '')
        self.is_relation = False
        self.auto_created = False
        self.choices = kwargs.pop('choices', None)
        self.concrete = True
        self.unique = False

        # Increase the creation counter, and save our local copy.
        self.creation_counter = Field.creation_counter
        Field.creation_counter += 1

    @property
    def rel(self):
        return None

    @property
    def flatchoices(self):
        return getattr(self, 'choices', None)

    def get_choices(
            self, include_blank=True, blank_choice=BLANK_CHOICE_DASH,
            limit_choices_to=None):
        """Returns choices with a default blank choices included, for use
        as SelectField choices for this field."""
        blank_defined = False
        choices = list(self.choices) if self.choices else []
        named_groups = choices and isinstance(choices[0][1], (list, tuple))
        if not named_groups:
            for choice, __ in choices:
                if choice in ('', None):
                    blank_defined = True
                    break

        first_choice = (blank_choice if include_blank and
                        not blank_defined else [])
        if self.choices:
            return first_choice + choices
        rel_model = self.rel.to
        limit_choices_to = limit_choices_to or self.get_limit_choices_to()
        if hasattr(self.rel, 'get_related_field'):
            lst = [(getattr(x, self.rel.get_related_field().attname),
                   smart_text(x))
                   for x in rel_model._default_manager.complex_filter(
                       limit_choices_to)]
        else:
            lst = [(x._get_pk_val(), smart_text(x))
                   for x in rel_model._default_manager.complex_filter(
                       limit_choices_to)]
        return first_choice + lst

    @property
    def verbose_name(self):
        verbose_name = self._verbose_name
        if verbose_name is None:
            verbose_name = self.attname.replace('_', ' ')
        return verbose_name

    def __get__(self, instance, instance_type=None):
        if instance is None or not hasattr(instance, 'client'):
            return self
        return instance.data.get(self.attname, self.default)

    def clean(self, instance, value):
        return value

    def __set__(self, instance, value):
        if instance is None:
            raise AttributeError(
                '%s must be accessed via instance' % self.attname.name)
        if not self.editable:
            return

        value = self.clean(instance, value)
        instance.data[self.attname] = value

    def value_from_object(self, instance):
        return self.__get__(instance)

    def get_attname(self):
        return self.attname

    def save_form_data(self, instance, data):
        # Important: None means "no change", other false value means "clear"
        # This subtle distinction (rather than a more explicit marker) is
        # needed because we need to consume values that are also sane for a
        # regular (non Model-) Form to find in its cleaned_data dictionary.
        if data is not None:
            # This value will be converted to unicode and stored in the
            # database, so leaving False as-is is not acceptable.
            if not data:
                data = ''
            setattr(instance, self.name, data)

    def has_default(self):
        """
        Returns a boolean of whether this field has a default value.
        """
        return self.default is not NOT_PROVIDED

    def get_default(self):
        """
        Returns the default value for this field.
        """
        if self.has_default():
            if callable(self.default):
                return self.default()
            return self.default
        if (not self.empty_strings_allowed or self.null):
            return None
        return ""

    def to_python(self, value):
        """
        Converts the input value into the expected Python data type, raising
        django.core.exceptions.ValidationError if the data can't be converted.
        Returns the converted value. Subclasses should override this.
        """
        return value

    def formfield(self, form_class=None, choices_form_class=None, **kwargs):
        """
        Returns a django.forms.Field instance for this database Field.
        """
        defaults = {'required': not self.blank,
                    'label': capfirst(self.verbose_name),
                    'help_text': self.help_text}
        if self.has_default():
            if callable(self.default):
                defaults['initial'] = self.default
                defaults['show_hidden_initial'] = True
            else:
                defaults['initial'] = self.get_default()
        if self.choices:
            # Fields with choices get special treatment.
            include_blank = (self.blank or
                             not (self.has_default() or 'initial' in kwargs))
            defaults['choices'] = self.get_choices(include_blank=include_blank)
            defaults['coerce'] = self.to_python
            if self.null:
                defaults['empty_value'] = None
            if choices_form_class is not None:
                form_class = choices_form_class
            else:
                form_class = forms.TypedChoiceField
            # Many of the subclass-specific formfield arguments (min_value,
            # max_value) don't apply for choice fields, so be sure to only pass
            # the values that TypedChoiceField will understand.
            for k in list(kwargs):
                if k not in ('coerce', 'empty_value', 'choices', 'required',
                             'widget', 'label', 'initial', 'help_text',
                             'error_messages', 'show_hidden_initial'):
                    del kwargs[k]
        defaults.update(kwargs)
        if form_class is None:
            form_class = forms.CharField
        return form_class(**defaults)


class BooleanField(Field):
    empty_strings_allowed = False

    def __init__(self, *args, **kwargs):
        kwargs['blank'] = True
        super(BooleanField, self).__init__(*args, **kwargs)

    def clean(self, instance, value):
        return bool(value)

    def formfield(self, **kwargs):
        # Unlike most fields, BooleanField figures out include_blank from
        # self.null instead of self.blank.
        if self.choices:
            include_blank = not (self.has_default() or 'initial' in kwargs)
            defaults = {
                'choices': self.get_choices(include_blank=include_blank)}
        else:
            defaults = {'form_class': forms.BooleanField}
        defaults.update(kwargs)
        return super(BooleanField, self).formfield(**defaults)


class IntegerField(Field):
    empty_strings_allowed = False

    def clean(self, instance, value):
        return int(value)

    def formfield(self, **kwargs):
        defaults = {'form_class': forms.IntegerField}
        kwargs.pop('choices', None)
        # assert not choices, choices
        defaults.update(kwargs)
        return super(IntegerField, self).formfield(**defaults)


class DecimalField(Field):
    empty_strings_allowed = False

    def clean(self, instance, value):
        return Decimal(value)

    def formfield(self, **kwargs):
        defaults = {'form_class': forms.DecimalField}
        defaults.update(kwargs)
        return super(DecimalField, self).formfield(**defaults)


class CharField(Field):
    def __init__(self, **kwargs):
        self.max_length = kwargs.pop('max_length', None)
        super(CharField, self).__init__(**kwargs)

    def clean(self, instance, value):
        value = unicode(value)
        if self.max_length:
            value = value[:self.max_length]
        return value

    def formfield(self, **kwargs):
        # Passing max_length to forms.CharField means that the value's length
        # will be validated twice. This is considered acceptable since we want
        # the value in the form field (to pass into widget for example).
        defaults = {'max_length': self.max_length}
        defaults.update(kwargs)
        return super(CharField, self).formfield(**defaults)


class TextField(Field):
    def __init__(self, **kwargs):
        self.max_length = kwargs.pop('max_length', None)
        super(TextField, self).__init__(**kwargs)

    def clean(self, instance, value):
        value = unicode(value)
        if self.max_length:
            value = value[:self.max_length]
        return value

    def formfield(self, **kwargs):
        # Passing max_length to forms.CharField means that the value's length
        # will be validated twice. This is considered acceptable since we want
        # the value in the form field (to pass into widget for example).
        defaults = {'max_length': self.max_length, 'widget': forms.Textarea}
        defaults.update(kwargs)
        return super(TextField, self).formfield(**defaults)


class JSONField(TextField):
    form_class = JSONFormField

    def __init__(self, **kwargs):
        self.dump_kwargs = kwargs.pop('dump_kwargs', {
            'cls': JSONEncoder,
            'separators': (',', ':')
        })
        self.load_kwargs = kwargs.pop('load_kwargs', {})
        super(JSONField, self).__init__(**kwargs)

    def clean(self, instance, value):
        return value

    def formfield(self, **kwargs):

        if "form_class" not in kwargs:
            kwargs["form_class"] = self.form_class

        field = super(JSONField, self).formfield(**kwargs)
        field.load_kwargs = self.load_kwargs

        if not field.help_text:
            field.help_text = "Enter valid JSON"

        return field

    def value_from_object(self, obj):
        value = super(JSONField, self).value_from_object(obj)
        if self.null and value is None:
            return None
        return self.dumps_for_display(value)

    def dumps_for_display(self, value):
        kwargs = {"indent": 2}
        kwargs.update(self.dump_kwargs)
        if isinstance(value, six.string_types):
            return json.dumps(json.loads(value), **kwargs)
        elif value.__class__.__name__ == 'DynamicRestObject':
            return json.dumps(value._obj, **kwargs)
        else:
            return json.dumps(value, **kwargs)


class DateField(CharField):
    pass


class DateTimeField(DateField):
    pass


class URLField(CharField):
    def __init__(self, **kwargs):
        self.verify_exists = kwargs.pop('verify_exists', False)
        super(URLField, self).__init__(**kwargs)

    def clean(self, instance, value):
        value = super(URLField, self).clean(instance, value)
        validate = URLValidator()
        try:
            validate(value)
        except ValidationError, e:
            raise e
        return value

    def formfield(self, **kwargs):
        # As with CharField, this will cause URL validation to be performed
        # twice.
        defaults = {
            'form_class': forms.URLField,
        }
        defaults.update(kwargs)
        return super(URLField, self).formfield(**defaults)
