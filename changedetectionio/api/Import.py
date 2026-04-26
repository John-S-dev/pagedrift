from changedetectionio.strtobool import strtobool
from flask_restful import abort, Resource
from flask import request
from functools import wraps
from . import auth, validate_openapi_request
from ..validate_url import is_safe_valid_url
import json

# Number of URLs above which import switches to background processing
IMPORT_SWITCH_TO_BACKGROUND_THRESHOLD = 20


def default_content_type(content_type='text/plain'):
    """Decorator to set a default Content-Type header if none is provided."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not request.content_type:
                # Set default content type in the request environment
                request.environ['CONTENT_TYPE'] = content_type
            return f(*args, **kwargs)
        return wrapper
    return decorator


def convert_query_param_to_type(value, schema_property):
    """
    Convert a query parameter string to the appropriate type based on schema definition.

    Args:
        value: String value from query parameter
        schema_property: Schema property definition with 'type' or 'anyOf' field

    Returns:
        Converted value in the appropriate type

    Supports both OpenAPI 3.1 formats:
    - type: [string, 'null']  (array format)
    - anyOf: [{type: string}, {type: null}]  (anyOf format)
    """
    prop_type = schema_property.get('type')

    # Handle OpenAPI 3.1 type arrays: type: [string, 'null']
    if isinstance(prop_type, list):
        # Use the first non-null type from the array
        for t in prop_type:
            if t != 'null':
                prop_type = t
                break
        else:
            prop_type = None

    # Handle anyOf schemas (older format)
    elif 'anyOf' in schema_property:
        # Use the first non-null type from anyOf
        for option in schema_property['anyOf']:
            if option.get('type') and option.get('type') != 'null':
                prop_type = option.get('type')
                break
        else:
            prop_type = None

    # Handle array type (e.g., notification_urls)
    if prop_type == 'array':
        # Support both comma-separated and JSON array format
        if value.startswith('['):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return [v.strip() for v in value.split(',')]
        return [v.strip() for v in value.split(',')]

    # Handle object type (e.g., time_between_check, headers)
    elif prop_type == 'object':
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON object for field: {value}")

    # Handle boolean type
    elif prop_type == 'boolean':
        return strtobool(value)

    # Handle integer type
    elif prop_type == 'integer':
        return int(value)

    # Handle number type (float)
    elif prop_type == 'number':
        return float(value)

    # Default: return as string
    return value


class Import(Resource):
    def __init__(self, **kwargs):
        # datastore is a black box dependency
        self.datastore = kwargs['datastore']

    @auth.check_token
    @default_content_type('text/plain') #3547 #3542
    @validate_openapi_request('importWatches')
    def post(self):
        """Import a list of watched URLs with optional watch configuration."""
        from . import get_watch_schema_properties
        # Special parameters that are NOT watch configuration
        special_params = {'tag', 'tag_uuids', 'dedupe', 'proxy'}

        extras = {}

        # Handle special 'proxy' parameter
        if request.args.get('proxy'):
            plist = self.datastore.proxy_list
            if not request.args.get('proxy') in plist:
                proxy_list_str = ', '.join(plist) if plist else 'none configured'
                return f"Invalid proxy choice, currently supported proxies are '{proxy_list_str}'", 400
            else:
                extras['proxy'] = request.args.get('proxy')

        # Handle special 'dedupe' parameter
        dedupe = strtobool(request.args.get('dedupe', 'true'))

