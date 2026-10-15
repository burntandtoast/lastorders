# Regression eval: acme-widgets-support-bot

- Old model: `gpt-4o-2024-08-06`  ->  New model: `gpt-6-luna`
- API: responses | Mode: **openai** | Run: 2026-10-15T09:51:05+0100
- old: `gpt-4o-2024-08-06` 501 in / 187 out tokens, est. $0.0031
- new: `gpt-6-luna` 511 in / 232 out tokens, est. $0.0002

| Status | Count |
|---|---|
| drift | 4 |
| pass | 2 |

| Case | Type | Status | Key checks |
|---|---|---|---|
| `ticket-summary-refund` | structured | **DRIFT** | schema valid old=True new=True; 1 field difference(s); similarity 0.789 |
| `ticket-summary-question` | structured | **DRIFT** | schema valid old=True new=True; 2 field difference(s); similarity 0.79 |
| `book-table-simple` | tool_call | **PASS** | tools ['book_table'] -> ['book_table'] |
| `book-table-relative-date` | tool_call | **DRIFT** | tools ['book_table'] -> ['book_table']; 1 argument difference(s) |
| `order-lookup` | tool_call | **PASS** | tools ['lookup_order'] -> ['lookup_order'] |
| `apology-tone` | text | **DRIFT** | similarity 0.425 |

## ticket-summary-refund (drift)

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
      "path": "tags",
      "change": "changed",
      "old": [
        "order_issue",
        "refund_request",
        "repeat_issue",
        "customer_service"
      ],
      "new": [
        "damaged-order",
        "refund-request",
        "repeat-issue"
      ]
    }
  ],
  "ignored_fields": [
    "summary"
  ],
  "similarity": 0.789,
  "similarity_threshold": 0.85
}
```

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
      "old": "medium",
      "new": "low"
    },
    {
      "path": "tags",
      "change": "changed",
      "old": [
        "shipping",
        "Ireland",
        "delivery time"
      ],
      "new": [
        "shipping",
        "Ireland"
      ]
    }
  ],
  "ignored_fields": [
    "summary"
  ],
  "similarity": 0.79,
  "similarity_threshold": 0.85
}
```

## book-table-relative-date (drift)

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
    "new": []
  },
  "argument_diff": [
    {
      "call": 0,
      "tool": "book_table",
      "diff": [
        {
          "path": "date",
          "change": "changed",
          "old": "2023-10-20",
          "new": "2025-05-30"
        }
      ]
    }
  ]
}
```

## apology-tone (drift)

```json
{
  "similarity": 0.425,
  "missing_phrases": [],
  "similarity_threshold": 0.5
}
```
