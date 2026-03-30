"""
Subprocess-isolated image operations for memory leak prevention.

LibVIPS accumulates C-level memory in long-running processes that cannot be
reclaimed by Python's GC or libvips cache management. Using subprocess isolation
ensures complete memory cleanup when the process exits.

This module wraps LibvipsImageDiffHandler operations in multiprocessing for
complete memory isolation without code duplication.

Research: https://github.com/libvips/pyvips/issues/234
"""

import multiprocessing

# CRITICAL: Use 'spawn' context instead of 'fork' to avoid inheriting parent's
# LibVIPS threading state which can cause hangs in gaussblur operations
# https://docs.python.org/3/library/multiprocessing.html#contexts-and-start-methods


