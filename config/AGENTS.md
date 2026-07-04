# Config rules — agent notes

## Files
- `category_rules.yaml` — maps descriptions to `(category, subcategory)`
- `clean_description_rules.yaml` — maps descriptions to a short friendly label

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
- Order matters — **first match wins**
- Patterns are case-insensitive regex
- Multiple patterns per rule = OR logic (any match triggers the rule)
- Backslashes must be double-escaped in YAML: `\\b` not `\b`
- `clean_description_rules.yaml` returns `null` if no match (AI fills it if enabled)
- `category_rules.yaml` falls back to `("uncategorized", "other")` if no match

## After editing
Always run recategorize to apply changes to existing transactions:
```bash
curl -X POST http://localhost:8000/api/v1/recategorize
```
The server reloads the YAML on each call — no restart needed.

## Valid categories (category_rules.yaml)
`income, housing, subscriptions, groceries, restaurants, transport,
health, shopping, entertainment, transfers, cash, admin, uncategorized`
