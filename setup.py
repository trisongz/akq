from pathlib import Path

from importlib.machinery import SourceFileLoader
from setuptools import setup

description = 'Job queues in python with asyncio and keydb/redis'
readme = Path(__file__).parent / 'README.md'
if readme.exists():
    long_description = readme.read_text()
else:
    long_description = description + '.\n\nSee https://arq-docs.helpmanual.io/ for documentation.'
# avoid loading the package before requirements are installed:
version = SourceFileLoader('version', 'akq/version.py').load_module()

setup(
    name='akq',
    version=version.VERSION,
    description=description,
    long_description=long_description,
    long_description_content_type='text/markdown',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Framework :: AsyncIO',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Operating System :: Unix',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Topic :: Internet',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: System :: Clustering',
        'Topic :: System :: Distributed Computing',
        'Topic :: System :: Monitoring',
        'Topic :: System :: Systems Administration',
    ],
    python_requires='>=3.6',
    author='Samuel Colvin, Tri Songz',
    author_email='ts@growthengineai.com',
    url='https://github.com/trisongz/akq',
    license='MIT',
    packages=['akq'],
    package_data={'akq': ['py.typed']},
    zip_safe=True,
    entry_points="""
        [console_scripts]
        akq=akq.cli:cli
    """,
    install_requires=[
        'aiokeydb>=0.0.9',
        'prometheus_client>=0.14.1',
        'click>=6.7',
        'pydantic>=1',
        'dataclasses>=0.6;python_version == "3.6"',
        'typing-extensions>=3.7;python_version < "3.8"'
    ],
    extras_require={
        'watch': ['watchgod>=0.4'],
    }
)
