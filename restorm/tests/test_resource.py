from unittest2 import TestCase

from restorm.examples.mock.api import LibraryApiClient, TicketApiClient
from restorm import fields
from restorm.resource import ResourceManager, ResourceOptions, Resource, SimpleResource
from restorm.query import RestQuerySet
from restorm.apps import RestormAppSetup


class ResourceTests(TestCase):

    def setUp(self):
        RestormAppSetup()
        self.client = LibraryApiClient()

        class Author(Resource):
            id = fields.IntegerField(primary_key=True)
            name = fields.CharField()

            class Meta:
                resource_name = 'author'
                list = (r'^author/$', 'author_set')
                item = r'^author/(?P<id>\d)$'
                client = self.client
                verbose_name = 'Author'
                verbose_name_plural = 'Authors'

        self.author_resource = Author

        class BookManager(ResourceManager):

            def filter_on_author(self, author_resource):
                return self.all(query=[('author', author_resource), ])

        self.book_manager = BookManager

        def get_author_id(data, resource):
            return {
                'id': data.split('/')[-1]
            }

        class Book(Resource):
            some_class_attribute = 'foobar'

            isbn = fields.CharField(primary_key=True)
            title = fields.CharField()
            author = fields.ToOneField('author', Author, get_author_id)

            objects = BookManager()

            class Meta:
                resource_name = 'book'
                list = r'^book/$'
                item = r'^book/(?P<isbn>\d)$'
                client = self.client

            def __init__(self, *args, **kwargs):
                self.some_instance_attribute_before_init = 'foobar'
                super(Book, self).__init__(*args, **kwargs)
                self.some_instance_attribute_after_init = 'foobar'

            def get_title(self):
                return self.title.title()

        self.book_resource = Book

        class Store(Resource):
            id = fields.IntegerField(primary_key=True)
            name = fields.CharField()

            class Meta:
                resource_name = 'store'
                list = r'^store/$'
                item = r'^store/(?P<id>\d)$'
                client = self.client
                verbose_name = 'Storage'
                verbose_name_plural = 'Storages'

        self.store_resource = Store

    def test_meta_class(self):
        self.assertTrue(hasattr(self.book_resource, '_meta'))
        self.assertIsInstance(self.book_resource._meta, ResourceOptions)
        self.assertEqual(self.book_resource._meta.list, r'^book/$')
        self.assertEqual(self.book_resource._meta.item, r'^book/(?P<isbn>\d)$')
        self.assertIsInstance(self.book_resource._meta.client, LibraryApiClient)

        self.assertTrue(hasattr(self.author_resource, '_meta'))
        self.assertIsInstance(self.author_resource._meta, ResourceOptions)
        self.assertEqual(self.author_resource._meta.verbose_name, 'Author')
        self.assertEqual(self.author_resource._meta.verbose_name_plural, 'Authors')
        self.assertIsInstance(self.author_resource._meta.client, LibraryApiClient)

        self.assertTrue(hasattr(self.store_resource, '_meta'))
        self.assertIsInstance(self.store_resource._meta, ResourceOptions)
        self.assertEqual(self.store_resource._meta.verbose_name, 'Storage')
        self.assertEqual(self.store_resource._meta.verbose_name_plural, 'Storages')
        self.assertIsInstance(self.store_resource._meta.client, LibraryApiClient)

        self.assertNotEqual(self.author_resource._meta, self.store_resource._meta)
        self.assertNotEqual(self.book_resource._meta, self.author_resource._meta)
        self.assertNotEqual(self.book_resource._meta, self.store_resource._meta)

    def test_default_manager(self):
        """
        By default, there should be a default manager on RestObject.
        """
        self.assertIsInstance(self.book_resource.objects, ResourceManager)
        self.assertTrue(self.book_resource.objects.object_class, self.book_resource)

        self.assertIsInstance(self.author_resource.objects, ResourceManager)
        self.assertTrue(self.author_resource.objects.object_class, self.author_resource)

        self.assertNotEqual(self.book_resource.objects, self.author_resource.objects)

        book = self.book_resource()
        # Cannot test AttributeError with self.assertRaises
        try:
            book.objects.all()
        except AttributeError as e:
            self.assertEqual('%s' % e, 'Manager is not accessible via Book instances')

    def test_custom_manager(self):
        """
        Custom managers can be added on a RestObject.
        """
        self.assertIsInstance(self.book_resource.objects, self.book_manager)
        self.assertTrue(hasattr(self.book_resource.objects, 'filter_on_author'))
        self.assertTrue(self.book_resource.objects.object_class, self.book_resource)

        self.assertIsInstance(self.author_resource.objects, ResourceManager)
        self.assertTrue(self.author_resource.objects.object_class, self.author_resource)

        self.assertNotEqual(self.book_resource.objects, self.author_resource.objects)

        book = self.book_resource()
        # Cannot test AttributeError with self.assertRaises
        try:
            book.objects
        except AttributeError as e:
            self.assertEqual('%s' % e, 'Manager is not accessible via Book instances')

    def test_custom_functions_and_attributes(self):
        """
        Alot of fiddling with class attributes, functions, meta classes, etc.
        is done to build a proper instance and/or class.

        This test validates some basic Python stuff to actually work as
        expected.
        """

        self.assertTrue(hasattr(self.book_resource, 'get_title'))
        self.assertFalse(hasattr(Resource, 'get_title'))

        self.assertTrue(hasattr(self.book_resource, 'some_class_attribute'))
        self.assertEqual(self.book_resource.some_class_attribute, 'foobar')
        self.assertFalse(hasattr(self.book_resource, 'some_instance_attribute_before_init'))
        self.assertFalse(hasattr(self.book_resource, 'some_instance_attribute_after_init'))

        book = self.book_resource.objects.get(client=self.client, isbn='978-1441413024')
        self.assertEqual(book.data['title'], 'Dive into Python')
        self.assertTrue(hasattr(book, 'get_title'))
        self.assertEqual(book.get_title(), book.data['title'].title())

        self.assertTrue(hasattr(book, 'some_class_attribute'))
        self.assertEqual(book.some_class_attribute, 'foobar')
        self.assertTrue(hasattr(book, 'some_instance_attribute_before_init'))
        self.assertEqual(book.some_instance_attribute_before_init, 'foobar')
        self.assertTrue(hasattr(book, 'some_instance_attribute_after_init'))
        self.assertEqual(book.some_instance_attribute_after_init, 'foobar')

    def test_get(self):
        book = self.book_resource.objects.get(isbn='978-1441413024')
        self.assertIsInstance(book, Resource)
        self.assertIsInstance(book.data, dict)
        self.assertEqual(book.title, 'Dive into Python')

    def test_all(self):
        result = self.book_resource.objects.all()
        self.assertIsInstance(result, RestQuerySet)
        self.assertEqual(len(result), 2)

    def test_related_resources(self):
        book = self.book_resource.objects.get(isbn='978-1441413024')
        self.assertEqual(book.title, 'Dive into Python')

        self.assertIsInstance(book.author, self.author_resource)
        # self.assertEqual(author_url, author.absolute_url)
        self.assertEqual(book.author.name, 'Mark Pilgrim')


class ResourceCreateAndUpdateTests(TestCase):

    def setUp(self):
        RestormAppSetup()
        self.client = TicketApiClient()

        class Issue(Resource):
            id = fields.IntegerField(primary_key=True)
            title = fields.CharField()
            description = fields.TextField()

            class Meta:
                list = r'^issue/$'
                item = r'^issue/(?P<id>\d+)$'
                client = self.client

        self.issue_resource = Issue

    def test_create_resource(self):
        issue = self.issue_resource.objects.create(
            title='Cannot create an issue',
            description='This needs more work.'
        )
        self.assertEqual(issue.title, 'Cannot create an issue')
        self.assertEqual(issue.description, 'This needs more work.')

    def test_update_resource(self):
        issue = self.issue_resource.objects.get(id=2)
        issue.description = 'This needs more work.'
        issue.save()


class SimpleResourceTests(TestCase):
    def setUp(self):
        RestormAppSetup()
        self.client = LibraryApiClient()

    def test_get(self):
        class Book(SimpleResource):
            title = fields.CharField()

            class Meta:
                item = r'^book/(?P<isbn>\d)$'
                client = self.client

        book = Book.objects.get(isbn='978-1441413024')
        self.assertIsInstance(book, Book)
        self.assertEqual(book.title, 'Dive into Python')

    def test_all(self):
        class Book(SimpleResource):
            isbn = fields.IntegerField(primary_key=True)

            class Meta:
                list = r'^book/$'
                client = self.client

        result = Book.objects.all()
        self.assertIsInstance(result, RestQuerySet)
        self.assertEqual(len(result), 2)
