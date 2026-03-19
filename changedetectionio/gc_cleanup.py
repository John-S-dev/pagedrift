#!/usr/bin/env python3

import ctypes
import gc
import re
import psutil
import sys
import threading
import importlib
from loguru import logger

def memory_cleanup(app=None):
    """
    Perform comprehensive memory cleanup operations and log memory usage
    at each step with nicely formatted numbers.
    
    Args:
        app: Optional Flask app instance for clearing Flask-specific caches
        
    Returns:
        str: Status message
    """
    # Get current process
    process = psutil.Process()
    
    # Log initial memory usage with nicely formatted numbers
    current_memory = process.memory_info().rss / 1024 / 1024
    logger.debug(f"Memory cleanup started - Current memory usage: {current_memory:,.2f} MB")

    # 1. Standard garbage collection - force full collection on all generations
    gc.collect(0)  # Collect youngest generation
    gc.collect(1)  # Collect middle generation
    gc.collect(2)  # Collect oldest generation

    # Run full collection again to ensure maximum cleanup
    gc.collect()
    current_memory = process.memory_info().rss / 1024 / 1024
    logger.debug(f"After full gc.collect() - Memory usage: {current_memory:,.2f} MB")
    

    # 3. Call libc's malloc_trim to release memory back to the OS
    libc = ctypes.CDLL("libc.so.6")
    libc.malloc_trim(0)
    current_memory = process.memory_info().rss / 1024 / 1024
    logger.debug(f"After malloc_trim(0) - Memory usage: {current_memory:,.2f} MB")
    
    # 4. Clear Python's regex cache
    re.purge()
    current_memory = process.memory_info().rss / 1024 / 1024
    logger.debug(f"After re.purge() - Memory usage: {current_memory:,.2f} MB")

    # 5. Reset thread-local storage
    # Create a new thread local object to encourage cleanup of old ones
    threading.local()
    current_memory = process.memory_info().rss / 1024 / 1024
    logger.debug(f"After threading.local() - Memory usage: {current_memory:,.2f} MB")

    # 6. Clear sys.intern cache if Python version supports it
    try:
        sys.intern.clear()
        current_memory = process.memory_info().rss / 1024 / 1024
        logger.debug(f"After sys.intern.clear() - Memory usage: {current_memory:,.2f} MB")
    except (AttributeError, TypeError):
        logger.debug("sys.intern.clear() not supported in this Python version")
    
    # 7. Clear XML/lxml caches if available
    try:
        # Check if lxml.etree is in use
        lxml_etree = sys.modules.get('lxml.etree')
        if lxml_etree:
            # Clear module-level caches
            if hasattr(lxml_etree, 'clear_error_log'):
                lxml_etree.clear_error_log()
            
