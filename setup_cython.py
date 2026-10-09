import os
import sys
from setuptools import setup, find_packages
from Cython.Build import cythonize

modules = [
    "app/core/selector_engine.py",
    "app/core/ast_normalizer.py",
    "app/core/recorder.py",
    "app/core/runner.py",
    "app/core/catalog_manager.py",
    "app/core/evidence_manager.py",
    "app/core/test_data_manager.py",
    "app/core/report_generator.py",
    "app/core/claude_engine.py",
    "app/core/migration_engine.py",
    "app/ui/main_window.py"
]

setup(
    name="conduit",
    packages=find_packages(),
    ext_modules=cythonize(
        modules,
        compiler_directives={"language_level": "3", "always_allow_keywords": True},
        build_dir="build_cython"
    )
)
