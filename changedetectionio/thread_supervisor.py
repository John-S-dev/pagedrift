"""
Keep critical background threads alive.

A threading.Thread cannot be restarted. Once its target returns, the thread is
finished and calling start() again raises RuntimeError("threads can only be
started once"). There is no built-in "respawn on death" option. So recovery has
to be built into the target itself.

