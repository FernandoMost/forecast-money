# Banks — agent notes

## Purpose
One YAML file per bank. The parser reads column mappings from the YAML — zero hardcoded bank logic in code.

## Reference files
| File | Purpose |
|---|---|
| `sample_bank.csv` | Minimal fictional statement — shows the expected column layout for CSV |
| `sample_bank.yaml` | Fully annotated reference config — **start here for new banks** |
| `santander.yaml` | Real xlsx example with metadata rows above the transaction table |

## Adding a new bank
```bash
cp banks/sample_bank.yaml banks/mybank.yaml
# edit banks/mybank.yaml
python3 backend/etl.py statement.csv --bank mybank
```

## YAML top-level keys

### `bank`
```yaml
bank:
  name: "My Bank"       # shown in UI
  id: "my_bank"         # stored as bank_id in DB — lowercase, no spaces
  locale: "en_US"
  currency: "EUR"
  encoding: "utf-8"
```

### `file`
```yaml
file:
  extension: "csv"      # "csv" or "xlsx"
```

### `sheet`
```yaml
sheet:
  index: 0              # 0-based sheet index (xlsx only, ignored for csv)
  header_row: 1         # 1-based row with column headers — rows above are skipped
  data_start_row: 2     # 1-based row where transactions begin

  # metadata block: xlsx only — extract account/balance from cells above the table
  # omit entirely for CSV or xlsx files without header metadata
  metadata:
    account_value_row: 2
    account_col: 3
    holder_value_row: 4
    holder_col: 3
    balance_value_row: 4
    balance_col: 4
    export_date_value_row: 2
    export_date_col: 4
```

### `columns`
All indices are **1-based**. Both xlsx and csv use this identical mechanism.
```yaml
columns:
  date_operation: 1     # required
  date_value: 1         # if same column as date_operation, repeat the index
  description: 2        # required
  amount: 3             # required — positive = credit, negative = debit
  balance: 4
  currency: 5           # omit if the bank doesn't export a currency column
```

### `parsing`
```yaml
parsing:
  date_format: "%Y-%m-%d"           # Python strptime string
  amount_strip_pattern: '\s'        # regex chars to strip before float conversion
  amount_decimal_separator: "."     # "." for English, "," for Spanish/EU
  reversal_prefix: "REVERSAL"       # transactions starting with this are flagged
  min_valid_columns: 3              # rows with fewer non-empty cols are skipped
```

## Parser behaviour by format

**CSV:**
- `sheet.metadata` is ignored — `BankMetadata` fields `account_number`, `account_holder`, `current_balance`, `export_date` will be `null`
- `bank_id`, `bank_name`, `currency` are always populated from the YAML

**xlsx:**
- Full `sheet.metadata` support
- `sheet.index` selects which worksheet to read
- `header_row` rows above the table are skipped during transaction parsing (but read for metadata)
