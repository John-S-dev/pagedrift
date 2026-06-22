#!/usr/bin/env python3
"""
The language modal renders for anonymous users on the login page (base.html keeps it
outside the `current_user.is_authenticated or not has_password` guard that wraps the
search modal). Both of its actions must therefore work while logged out.

Regression: only `set_language` was exempted in check_authentication(), so an anonymous
user at the login screen could pick a specific language but clicking "Auto-detect from
browser" right below it 302'd to /login without clearing the session locale.
"""

