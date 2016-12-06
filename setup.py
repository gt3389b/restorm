#!/usr/bin/env python
import os
import sys
import restorm
from setuptools import setup, find_packages


def read_file(name):
    return open(os.path.join(os.path.dirname(__file__), name)).read()


readme = read_file('README.rst')
changes = read_file('CHANGES.rst')


install_requires = [
    'requests>=2.7.0',
    'django==1.8.16',
]
tests_require = [
    'nose',
    'unittest2',
    'mock',
    'oauth2', # For Twitter example.
]

if sys.version_info < (2,6):
    install_requires += [
        'simplejson>=2.2.1'
    ]


setup(
    name='restorm-setuptools',
    version='.'.join(map(str, restorm.__version__)),

    # Packaging.
    packages=find_packages(exclude=('tests', 'examples')),
    install_requires=install_requires,
    test_suite='nose.collector',
    tests_require=tests_require,
    include_package_data=True,
    zip_safe=False,

    # Metadata for PyPI.
    description='RestORM allows you to interact with resources as if they were objects.',
    long_description='\n\n'.join([readme, changes]),
    author='Joeri Bekker',
    author_email='joeri@maykinmedia.nl',
    license='MIT',
    platforms=['any'],
    url='http://github.com/goinnn/restorm',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development',
    ],
)
