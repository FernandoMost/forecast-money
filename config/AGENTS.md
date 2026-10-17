# Config rules — agent notes

> **LEGACY.** These YAML files are only one-shot seeds: the backend imports them into
> `data/shared.db` on first startup (when the target table is empty) and never reads
> them again. Edit rules via the UI (`/rules`, `/categories`) or the API instead.

## Files
- `category_rules.yaml` — seeds the `category_rules` table: description patterns → `(category, subcategory)`
- `clean_description_rules.yaml` — seeds the `description_rules` table: patterns → short friendly label

## Format

**category_rules.yaml**
```yaml
- category: transport
  subcategory: fuel
  patterns:
    - "PETROPRIX|PLENOIL|GASOLINERA"
```

**clean_description_rules.yaml**
```yaml
- label: "Gasolina"
  patterns:
    - "PETROPRIX|PLENOIL|GASOLINERA"
```

## Rules
- Order matters — **first match wins** (preserved via `position` column after migration)
- Patterns are case-insensitive regex
- Multiple patterns per rule = OR logic (any match triggers the rule)
- Backslashes must be double-escaped in YAML: `\\b` not `\b`
- Description rules return `null` if no match (AI fills it if enabled)
- Categorization falls back to `("uncategorized", "other")` if no match

## Category taxonomy
Source of truth: `categories` table in `data/shared.db` (default seed:
`_DEFAULT_CATEGORIES` in `backend/main.py`). Managed via `/categories` UI or
`GET/POST/PATCH/DELETE /api/v1/categories`. To re-seed from scratch, delete
`data/shared.db` and restart the backend.
