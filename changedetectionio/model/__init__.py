import os
import uuid

from changedetectionio import strtobool
from .persistence import EntityPersistenceMixin, _determine_entity_type

__all__ = ['EntityPersistenceMixin', 'watch_base']

from ..browser_steps.browser_steps import browser_steps_get_valid_steps

class watch_base(dict):
    """
    Base watch domain model (inherits from dict for backward compatibility).

    WARNING: This class inherits from dict, which violates proper encapsulation.
    Dict inheritance is legacy technical debt that should be refactored to a proper
    domain model (e.g., Pydantic BaseModel) for better type safety and validation.

    TODO: Migrate to Pydantic BaseModel for:
          - Type safety and IDE autocomplete
          - Automatic validation
          - Clear separation between domain model and serialization
          - Database backend abstraction (file → postgres → mongodb)
          - Configuration override chain resolution (Watch → Tag → Global)
          - Immutability options
          - Better testing
          - USE https://docs.pydantic.dev/latest/integrations/datamodel_code_generator TO BUILD THE MODEL FROM THE API-SPEC!!!

    CHAIN RESOLUTION ARCHITECTURE:
        The dream is a 3-level override hierarchy:
            Watch settings → Tag/Group settings → Global settings

