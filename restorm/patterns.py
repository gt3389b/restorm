import re
import urllib

from restorm.utils import reverse


class ResourcePattern(object):
    """
    # TODO: This class needs cleaning up and refactoring.
    """

    def __init__(self, pattern, obj_path=None):
        self.pattern = pattern
        self.obj_path = obj_path

    @classmethod
    def parse(cls, obj):
        if isinstance(obj, tuple):
            return cls(*obj)
        return cls(obj)

    def params_from_uri(self, uri):
        return re.search(self.pattern.strip('^$'), uri).groupdict()

    def clean(self, response):
        if self.obj_path:
            return response.content[self.obj_path]
        return response.content

    def get_url(self, query=None, **kwargs):
        if query:
            query = '?%s' % urllib.urlencode(query)
        else:
            query = ''
        return '%s%s' % (reverse(self.pattern, **kwargs), query)

    def get_absolute_url(self, root=None, query=None, **kwargs):
        if root is None:
            root = ''
        return '%s%s' % (root, self.get_url(query, **kwargs))
