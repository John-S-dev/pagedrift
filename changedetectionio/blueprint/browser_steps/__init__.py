
# Dedicated event loop for ALL browser steps sessions
_browser_steps_loop = None
_browser_steps_thread = None
_browser_steps_loop_lock = threading.Lock()

