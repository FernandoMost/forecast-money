# Config rules — agent notes

## Files
- `category_rules.yaml` — maps description patterns to `(category, subcategory)`
- `clean_description_rules.yaml` — maps description patterns to a short friendly label

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

## Full taxonomy (category → subcategories)

| Category | Subcategories |
|---|---|
| `income` | `payroll`, `transfer_in`, `bizum_in`, `refund`, `paypal_in` |
| `housing` | `rent`, `utilities_electricity`, `utilities_water`, `utilities_heating`, `internet_phone` |
| `subscriptions` | `streaming`, `gym`, `sports_club`, `paypal_sub`, `pagatelia`, `other_sub` |
| `groceries` | `supermarket`, `other_food_shop` |
| `restaurants` | `fast_food`, `restaurant`, `cafe_bakery`, `bar_pub` |
| `transport` | `parking`, `fuel`, `rideshare`, `public_transit`, `train_station`, `tyre_service` |
| `health` | `pharmacy`, `medical` |
| `shopping` | `online`, `clothing`, `electronics`, `general` |
| `entertainment` | `cinema`, `events`, `gaming` |
| `transfers` | `rent_contribution`, `bizum_out`, `transfer_out` |
| `cash` | `atm_withdrawal` |
| `admin` | `city_tax`, `travel_tickets` |
| `uncategorized` | `other` (fallback — hardcoded, not in YAML) |

**Important:** this taxonomy is mirrored in `frontend/components/CategoryTree.tsx` (`CATEGORY_TREE` constant). If you add/remove categories or subcategories here, update that file too.
