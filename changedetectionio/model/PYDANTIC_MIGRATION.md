# Pydantic Migration

Plan for incrementally moving the app's storage dicts behind Pydantic models. Driven by
security (CWE-915 mass-assignment, see [GHSA-h3x5-5j56-hm2j][advisory]) and schema
enforcement, not just type tidying.

[advisory]: https://github.com/dgtlmoon/changedetection.io/security/advisories/GHSA-h3x5-5j56-hm2j

## The goal

Every form/API endpoint that mutates a stored dict should validate input against a
declared schema before writing. `extra='forbid'` rejects unknown keys — so an attacker
POSTing extra fields like `uuid=…`, `last_checked=…`, `history=[…]` can't smuggle them
into storage. Per-route allowlists work but rot; one declared schema per stored shape
doesn't.

## Prefer a migration over permanent complexity

```python
class LLMSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')

    enabled: bool = True
    model: str = ''
    ...

    # System-managed counters
    tokens_total_cumulative: int = 0
    ...

    # Field groups
    CONNECTION_FIELDS: ClassVar[Tuple[str, ...]] = ('model', 'api_key', ...)
    PROTECTED_FIELDS:  ClassVar[Tuple[str, ...]] = ('tokens_total_cumulative', ...)
```

Boundary pattern at the route handler:

```python
# Read
settings = LLMSettings.model_validate(
    datastore.data['settings']['application'].get('llm') or {}
)

# Merge form input
form_input = dict(form.data.get('llm') or {})
for protected in LLMSettings.PROTECTED_FIELDS:
    form_input.pop(protected, None)  # counters never come from form
merged = LLMSettings.model_validate({**settings.model_dump(), **form_input})

# Write — re-validates the schema on every write
datastore.data['settings']['application']['llm'] = merged.model_dump()
```

## Unresolved architectural decisions

Two decisions need answers before the `WatchInput` slice. They're not blockers for `App.py`.

### OpenAPI spec vs Pydantic model — who's source of truth?

Today: `docs/api-spec.yaml` declares the Watch/Tag shape; `model/schema_utils.py` reads
it to compute readonly fields; the API layer validates against it; the model layer is a
plain dict that doesn't know about either. When `WatchInput` lands, that's a third
shape declaration.

Two ways to live:
- **Pydantic is source.** Generate / sync `api-spec.yaml` from the model
  (e.g. via `model_json_schema()`). One declaration, multiple consumers. Long-term
  right answer; needs tooling.
- **Parallel sources with discipline.** Hand-keep them aligned. Faster to ship but
  drift is inevitable — that's the bug class we're already trying to close.

Recommendation: start parallel (keep `api-spec.yaml` for now), but write Watch's
Pydantic model so it could be the eventual single source. Don't *invent* a new
field shape — match the spec.

### Plugin / processor_config_* extensibility

