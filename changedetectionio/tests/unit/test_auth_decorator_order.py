"""
Static analysis test: verify @blueprint.route() is always the outermost
decorator on a view, so nothing sits above it.

In Flask, @route() must be outermost because it registers whatever function
it receives and then returns that function unchanged. Any decorator placed
above @route() is applied only to the module-level name, never to the view
the blueprint actually dispatches to — so it is silently dead code. When the
dead decorator is an auth wrapper, the route is left unprotected
(GHSA-jmrh-xmgh-x9j4).

Correct order (route outermost, auth inner):
    @blueprint.route('/path')
    @login_optionally_required
    def view(): ...

