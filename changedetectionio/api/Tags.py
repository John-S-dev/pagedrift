from changedetectionio import queuedWatchMetaData
from changedetectionio import worker_pool
from flask_restful import abort, Resource
from loguru import logger

import threading
from flask import request
from . import auth

from . import validate_openapi_request, strip_internal_api_fields


def validate_tag_colour(json_data):
    """Return an error message when tag_colour is set to anything but a hex colour.

    The value is rendered into a <style> block, so anything else is CSS injection.
    The OpenAPI schema carries the same pattern, this is the belt to that's braces.
    """
    from changedetectionio.blueprint.tags.colour import is_safe_css_colour

    tag_colour = json_data.get('tag_colour')
    if tag_colour and not is_safe_css_colour(tag_colour):
        return "tag_colour: must be a hex colour, for example #4f8ef7"

    return None


class Tags(Resource):
    def __init__(self, **kwargs):
        # datastore is a black box dependency
        self.datastore = kwargs['datastore']

    @auth.check_token
    @validate_openapi_request('listTags')
    def get(self):
        """List tags/groups."""
        result = {}
        for uuid, tag in self.datastore.data['settings']['application']['tags'].items():
            result[uuid] = {
                'date_created': tag.get('date_created', 0),
                'notification_muted': tag.get('notification_muted', False),
                'title': tag.get('title', ''),
                'uuid': tag.get('uuid')
            }

        return result, 200