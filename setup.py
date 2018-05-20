#!/usr/bin/env python
import os.path
import re

from setuptools import setup, find_packages
from setuptools.command.build_py import build_py
import shutil

here = os.path.abspath(os.path.dirname(__file__))


def read(*parts):
    with open(os.path.join(here, *parts), 'r', encoding='utf-8') as f:
        return f.read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


class BuildPyCommand(build_py):
    """Custom build command to copy api-spec.yaml to the package."""
    def run(self):
        build_py.run(self)
        # Ensure the docs directory exists in the build output
        docs_dir = os.path.join(self.build_lib, 'changedetectionio', 'docs')
        os.makedirs(docs_dir, exist_ok=True)
        # Copy api-spec.yaml to the package
        shutil.copy(
            os.path.join(here, 'docs', 'api-spec.yaml'),
            os.path.join(docs_dir, 'api-spec.yaml')
        )


