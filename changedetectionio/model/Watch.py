"""
Watch domain model for change detection monitoring.

1. CHAIN RESOLUTION (Watch → Tag → Global Settings)
   - Current: Manual resolution scattered across codebase
   - Future: @computed_field properties with automatic resolution
   - Examples: resolved_fetch_backend, resolved_restock_settings, etc.

