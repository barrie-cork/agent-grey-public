# Search Strategy App

PIC framework search query generation.

## Models

| Model | Purpose |
|-------|---------|
| `SearchStrategy` | PIC model. Methods: `generate_queries`, `generate_split_queries`, `validate_completeness`, `check_query_lengths`, `get_stats` |
| `SearchQuery` | Generated boolean queries. Denormalised session reference. `extract_domain`, `get_search_terms`, `get_file_types` |

## Views

| Symbol | Purpose |
|--------|---------|
| `SearchStrategyView` | Main strategy form with submission/execution handling |
| `update_strategy_ajax` | AJAX strategy updates |
| `check_query_lengths_ajax` | Query length validation |
| `strategy_status_api` | Strategy status API |

## Signals (`signals.py`)

| Handler | Purpose |
|---------|---------|
| `check_strategy_completion` | **Auto-transition trigger**: on `SearchQuery` post_save, transitions session to `ready_to_execute` when strategy is complete |
| `mark_strategy_complete` | Marks strategy as complete |
| `get_session_queries_data` / `get_query_count` | Data providers |

## Query Generation: File Type Operators

`generate_queries()` appends `filetype:` operators from `search_config.file_types`. Google treats spaces as implicit AND, so **no explicit `AND` before `filetype:`**:

```
site:nice.org.uk (population) AND (interest) AND (context) (filetype:pdf)
```

Multi-type uses `OR` with parentheses: `(filetype:pdf OR filetype:doc OR filetype:docx)`.

Full reference: `docs/serp/google-search-operators.md`

## Other Files

- `forms.py` -- strategy/query forms. `SearchStrategyForm` includes `serp_providers` `TypedMultipleChoiceField` populated from `SerpProviderConfig`; stored in `search_config["serp_providers"]`
- `services/` -- strategy services
