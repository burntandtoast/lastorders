# Regression eval: acme-widgets-support-bot

- Old model: `gpt-4o-2024-08-06`  ->  New model: `gpt-6-luna`
- API: chat | Mode: **mock** | Run: 2026-10-15T09:51:49+0100
- **Dry run: outputs are simulated, not real model responses.**

| Status | Count |
|---|---|
| drift | 1 |
| fail | 1 |
| pass | 4 |

| Case | Type | Status | Key checks |
|---|---|---|---|
| `ticket-summary-refund` | structured | **PASS** | schema valid old=True new=True; similarity 1.0 |
| `ticket-summary-question` | structured | **DRIFT** | schema valid old=True new=True; 2 field difference(s); similarity 0.745 |
| `book-table-simple` | tool_call | **PASS** | tools ['book_table'] -> ['book_table'] |
| `book-table-relative-date` | tool_call | **FAIL** | tools ['book_table'] -> ['book_table']; 2 argument difference(s) |
| `order-lookup` | tool_call | **PASS** | tools ['lookup_order'] -> ['lookup_order'] |
| `apology-tone` | text | **PASS** | similarity 0.556 |

## ticket-summary-question (drift)

```json
{
  "schema_valid": {
    "old": true,
    "new": true
  },
  "schema_errors": {
    "old": [],
    "new": []
  },
  "field_diff": [
    {
      "path": "priority",
      "change": "changed",
      "old": "low",
      "new": "medium"
    },
    {
      "path": "tags",
      "change": "changed",
      "old": [
        "shipping"
      ],
      "new": [
        "shipping",
        "international"
      ]
    }
  ],
  "ignored_fields": [
    "summary"
  ],
  "similarity": 0.745,
  "similarity_threshold": 0.85
}
```

## book-table-relative-date (fail)

```json
{
  "tool_names": {
    "old": [
      "book_table"
    ],
    "new": [
      "book_table"
    ],
    "match": true
  },
  "errors": {
    "old": [],
    "new": [
      "book_table: date: '23/10/2026' does not match '^\\\\d{4}-\\\\d{2}-\\\\d{2}$'"
    ]
  },
  "argument_diff": [
    {
      "call": 0,
      "tool": "book_table",
      "diff": [
        {
          "path": "date",
          "change": "changed",
          "old": "2026-10-23",
          "new": "23/10/2026"
        },
        {
          "path": "time",
          "change": "changed",
          "old": "19:30",
          "new": "7:30pm"
        }
      ]
    }
  ]
}
```
