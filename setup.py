from distutils.core import setup

setup(
    name='bulkdock',
    version='0.1',
    url='',
    license='',
    author='Stefan Junker',
    author_email='code@stefanjunker.de',
    description='A Gentoo-biased Docker container creation utility',
    entry_points={
        'console_scripts': [
            'bulkdock=bulkdock:main'
        ]
    },
    install_requires=[
        'jinja2','pyaml'
    ],
)
