# Google Search Operators Reference

Reference for Google search operators used in SERP query generation. This document covers syntax rules, combining operators, and known limitations relevant to Agent Grey's `SearchStrategy.generate_queries()` pipeline.

Last verified: February 2026.

## Core Operators

| Operator | Syntax | Example | Notes |
|----------|--------|---------|-------|
| `filetype:` | `filetype:pdf` | `cancer screening filetype:pdf` | No space after colon. Returns results of specified file type. |
| `site:` | `site:domain.com` | `site:nice.org.uk guidelines` | Restricts to a specific domain. |
| `"exact phrase"` | `"exact phrase"` | `"intellectual disabilities"` | Matches the exact phrase. |
| `-term` | `-excluded` | `cancer screening -pediatrics` | Excludes results containing the term. |
| `OR` | `term1 OR term2` | `filetype:pdf OR filetype:docx` | Matches either term. Must be uppercase. |

## Implicit AND

Google treats **spaces between terms as implicit AND**. You do not need to write `AND` explicitly:

```
cancer screening guidelines filetype:pdf
```

This means: results must match `cancer` AND `screening` AND `guidelines` AND be a PDF.

**Do NOT use explicit `AND`**: Google interprets the literal word `AND` as a search term, not a Boolean operator. Writing `cancer AND screening` searches for pages containing the word "AND".

## File Type Operator Rules

### Single file type

```
your search terms filetype:pdf
```

- `filetype:` can appear anywhere in the query; order does not matter semantically
- No space after the colon: `filetype:pdf` not `filetype: pdf`
- Equivalent operator: `ext:pdf` works the same as `filetype:pdf`

### Multiple file types

Use `OR` with parentheses:

```
your search terms (filetype:pdf OR filetype:doc OR filetype:docx)
```

**Do NOT stack without OR**: `filetype:pdf filetype:doc` effectively only applies the last one.

### Combining with `site:`

```
site:nice.org.uk cancer screening (filetype:pdf)
```

Order: `site:` first, then search terms, then file type filter.

## Agent Grey Query Structure

`SearchStrategy.generate_queries()` builds queries in this format:

### Domain-specific with file type

```
site:{domain} ({population}) AND ({interest}) AND ({context}) (filetype:pdf)
```

Note: `AND` is used between PIC term groups (where it acts on the Boolean-grouped terms within parentheses), but NOT before `filetype:`. The PIC `AND` usage is within Google's Boolean parsing of grouped terms, which is distinct from appending a search operator.

### General search with file type

```
({population}) AND ({interest}) AND ({context}) (filetype:pdf)
```

### Multi-type example

```
site:nice.org.uk (adults) AND (cancer) AND (screening) (filetype:pdf OR filetype:doc OR filetype:docx)
```

## Known Limitations

### `filetype:` is a hint, not a hard filter

Google's `filetype:` operator is advisory. Google may return non-matching file types, especially when:

- The query is very specific and few PDFs match
- The domain has limited PDF content
- Google's index has stale file type metadata

**Mitigation**: Agent Grey enforces file type restrictions in post-processing. Results that don't match the requested file type are stored with `processing_status='filtered'` and `processing_error_category='file_type_mismatch'` for audit trail transparency. Only matching results appear in the review interface.

### Supported file types

Stick to common extensions for reliable results:

| Extension | Operator | Notes |
|-----------|----------|-------|
| PDF | `filetype:pdf` | Most reliable |
| Word | `filetype:doc`, `filetype:docx` | Both needed for full coverage |
| Excel | `filetype:xls`, `filetype:xlsx` | Not currently used |
| PowerPoint | `filetype:ppt`, `filetype:pptx` | Not currently used |

### Query length limits

Google has an undocumented query length limit (approximately 2048 characters including operators). Long PIC term combinations with domain and file type filters can exceed this. Agent Grey handles this via query splitting (`SearchStrategy.generate_split_queries()`).

## SERP Provider: Serper API

Agent Grey uses the [Serper API](https://serper.dev/) (Google SERP data). Key details:

- **Endpoint**: `POST https://google.serper.dev/search`
- **Query field**: `"q"` -- receives the full query string including all operators
- **The API does not add or modify operators** -- what we send is what Google searches
- **Rate limiting**: Per-provider via scoped Redis keys
- **Circuit breaker**: Protected with pybreaker for fault tolerance
- **Pagination**: Configurable via `pagination_config` in `search_config`

### API payload example

```json
{
    "q": "site:nice.org.uk (adults) AND (cancer) AND (screening) (filetype:pdf)",
    "num": 10,
    "hl": "en",
    "gl": "uk"
}
```

## Future Considerations

### Exclusion terms (`-term`)

Google supports excluding terms with the minus operator: `cancer screening -pediatrics`. This could be exposed as a user configuration option in the Search Strategy form, allowing users to exclude irrelevant terms from results.

### Alternative file type handling via Serper parameters

Serper may support file type filtering as a separate API parameter in future versions, which could be more reliable than the `filetype:` query operator. Monitor Serper API changelog.

## File Reference

| File | Role |
|------|------|
| `apps/search_strategy/models.py` | `generate_queries()`, `_build_file_type_filter()` -- query generation |
| `apps/serp_execution/providers/serper_provider.py` | Serper API provider implementation |
| `apps/core/services/serper_client.py` | HTTP client, `sanitize_query()`, pagination |
| `apps/serp_execution/tasks/simple_tasks.py` | Execution task, passes `query.query_text` to provider |
| `apps/results_manager/services/processors/batch_processor.py` | Post-processing file type enforcement |
| `apps/results_manager/constants.py` | `ErrorCategory.FILE_TYPE_MISMATCH` |
