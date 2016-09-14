from restorm.exceptions import RestServerException
from restorm.patterns import ResourcePattern

VALID_GET_STATUS_RESPONSES = (
    200,  # OK
    304,  # NOT MODIFIED
)


class RestQuerySet(object):
    """Rest query set."""
    def __init__(self, model=None, query=None, client=None):
        self.model = model or dict
        self.query = query or {}
        self._client = client
        self._pages_fetched = {}
        self._result_cache = {}
        # FIXME NOW
        self._page_size = model._meta.page_size
        self._item_pattern = ResourcePattern.parse(self.model._meta.item)


    def _request_list(self, query=None, uri=None, **kwargs):
        rp = ResourcePattern.parse(self.model._meta.list)
        if uri:
            kwargs = rp.params_from_uri(uri)
        absolute_url = rp.get_absolute_url(
            root=self.model._meta.root, query=query, **kwargs)

        response = self._client.get(absolute_url)

        if response.status_code not in VALID_GET_STATUS_RESPONSES:
            raise RestServerException('Cannot get "%s" (%d): %s' % (
                response.request.uri, response.status_code, response.content))

        return response

    def _page_for_index(self, index):
        if self._page_size:
            # offset = index % self._page_size
            page = (index / self._page_size)
            # if index and offset:
            #     page -= 1
        else:
            page = 0
        return page

    def _fetch_page(self, page):
        if page in self._pages_fetched:
            return
        params = self.query.copy()
        if self._page_size:
            params.update({
                'page_size': self._page_size,
                'page': page + 1
            })
        result = self._request_list(query=params)
        content = result.content
        if self._page_size:
            objects = content.pop('results')
            self._pages_fetched[page] = content
            offset_from = page * self._page_size
        else:
            objects = content
            offset_from = 0
        for i, r in enumerate(objects):
            self._result_cache[offset_from + i] = self.model(r)

    def _fetch_all(self):
        if self._page_size:
            count = self.count()
            pages = count / self._page_size
            if count % self._page_size:
                pages += 1
        else:
            pages = 1
        for page in range(pages):
            self._fetch_page(page)

    def _pages_for_slice(self, start, stop, step):
        from_page = self._page_for_index(start)
        to_page = self._page_for_index(stop-1)
        return range(from_page, to_page + 1)

    def __get_slice__(self, start, stop, step):
        if start < 0 or stop < 0:
            raise IndexError
        if start >= stop:
            raise IndexError
        if stop > self.count():
            raise IndexError
        if step is None:
            step = 1

        pages = self._pages_for_slice(start, stop, step)
        missing_pages = [p for p in pages if p not in self._pages_fetched]
        if missing_pages:
            for page in pages:
                self._fetch_page(page)
        return [self._result_cache[x] for x in range(start, stop, step)]

    def __getitem__(self, key):
        if isinstance(key, slice):
            return self.__get_slice__(key.start, key.stop, key.step)

        if key >= self.count():
            raise IndexError
        try:
            return self._result_cache[key]
        except KeyError:
            page = self._page_for_index(key)
            self._fetch_page(page)
            return self._result_cache[key]

    def __iter__(self):
        self._fetch_all()
        return iter(self._result_cache.values())

    def __bool__(self):
        return bool(self.count())

    def get_queryset(self):
        return RestQuerySet(
            self.model, query=self.query,
            client=self._client)

    def _clone(self):
        return self.get_queryset()

    def filter(self, **kwargs):
        query = self.query.copy()
        query.update(kwargs)

        return RestQuerySet(
            self.model, query=query, client=self._client)

    def values(self, *fields):
        self._fetch_all()
        return self._result_cache.values()

    def all(self):
        return self.get_queryset()

    def _request_item(self, query=None, uri=None, **kwargs):
        if uri:
            kwargs = self._item_pattern.params_from_uri(uri)
        absolute_url = self._item_pattern.get_absolute_url(
            root=self.model._meta.root, query=query, **kwargs)

        response = self._client.get(absolute_url)

        if response.status_code not in VALID_GET_STATUS_RESPONSES:
            raise RestServerException('Cannot get "%s" (%d): %s' % (
                response.request.uri, response.status_code, response.content))

        # data = self._item_pattern.clean(response)
        return response

    def get(self, **kwargs):
        response = self._request_item(**kwargs)
        obj = self.model(
            response.content, client=self._client,
            absolute_url=response.request.uri)
        return obj

    def count(self):
        _page = 0
        self._fetch_page(_page)
        if self._page_size:
            count = self._pages_fetched[_page].get('count')
        else:
            count = len(self._result_cache)
        return count

    def __len__(self):
        return self.count()
