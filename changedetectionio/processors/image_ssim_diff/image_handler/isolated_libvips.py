"""
Subprocess-isolated image operations for memory leak prevention.

This module wraps LibvipsImageDiffHandler operations in multiprocessing for
complete memory isolation without code duplication.

Research: https://github.com/libvips/pyvips/issues/234
"""

