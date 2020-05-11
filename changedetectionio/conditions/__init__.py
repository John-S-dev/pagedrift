from json_logic.builtins import BUILTINS
from flask_babel import lazy_gettext as _l

from .exceptions import EmptyConditionRuleRowNotUsable
from .pluggy_interface import plugin_manager  # Import the pluggy plugin manager
from . import default_plugin
from loguru import logger
# List of all supported JSON Logic operators
operator_choices = [
    (None, _l("Choose one - Operator")),
    (">", _l("Greater Than")),
    ("<", _l("Less Than")),
    (">=", _l("Greater Than or Equal To")),
    ("<=", _l("Less Than or Equal To")),
    ("==", _l("Equals")),
    ("!=", _l("Not Equals")),
    ("in", _l("Contains")),
]

# Fields available in the rules
field_choices = [
    (None, _l("Choose one - Field")),
]

# The data we will feed the JSON Rules to see if it passes the test/conditions or not
EXECUTE_DATA = {}


# Define the extended operations dictionary
CUSTOM_OPERATIONS = {
    **BUILTINS,  # Include all standard operators
}

def filter_complete_rules(ruleset):
    rules = [
        rule for rule in ruleset
        if all(
            rule.get(k) is not None
            and rule.get(k) is not False
            and rule.get(k) != ""
            and rule.get(k) != "None"
            for k in ("operator", "field", "value")
        )
    ]
    return rules

