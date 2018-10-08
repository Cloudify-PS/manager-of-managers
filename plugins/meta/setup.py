from setuptools import setup, find_packages

setup(
    name='cloudify-meta-manager',
    version='0.1',
    author='Cloudify',
    author_email='hello@cloudify.co',
    packages=find_packages(include='meta*'),
    description='Cloudify Meta Manager of Managers plugin',
    install_requires=[
        'cloudify-common==4.5'
    ],
)