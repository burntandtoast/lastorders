# Regression eval: acme-widgets-support-bot

- Old model: `gpt-4o-2024-08-06`  ->  New model: `gpt-6-luna`
- API: chat | Mode: **openai** | Run: 2026-10-15T09:50:43+0100
- old: `gpt-4o-2024-08-06` 531 in / 293 out tokens, est. $0.0043
- new: `gpt-6-luna` 765 in / 205 out tokens, est. $0.0002

| Status | Count |
|---|---|
| drift | 4 |
| pass | 2 |

| Case | Type | Status | Key checks |
|---|---|---|---|
| `ticket-summary-refund` | structured | **DRIFT** | schema valid old=True new=True; 4 field difference(s); similarity 0.634 |
| `ticket-summary-question` | structured | **DRIFT** | schema valid old=True new=True; 1 field difference(s); similarity 0.86 |
| `book-table-simple` | tool_call | **PASS** | tools ['book_table'] -> ['book_table'] |
| `book-table-relative-date` | tool_call | **DRIFT** | tools ['book_table'] -> ['book_table']; 2 argument difference(s) |
| `order-lookup` | tool_call | **PASS** | tools ['lookup_order'] -> ['lookup_order'] |
| `apology-tone` | text | **DRIFT** | similarity 0.343 |

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
      "path": "tags[0]",
      "change": "changed",
      "old": "refund_issue",
      "new": "damaged-order"
    },
    {
      "path": "tags[1]",
      "change": "changed",
      "old": "repeat_issue",
      "new": "refund-request"
    },
    {
      "path": "tags[2]",
      "change": "changed",
      "old": "express_delivery",
      "new": "repeat-issue"
    },
    {
      "path": "tags[3]",
      "change": "changed",
      "old": "customer_dissatisfaction",
      "new": "order-4411"
    }
  ],
  "ignored_fields": [
    "summary"
  ],
  "similarity": 0.634,
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
      "path": "tags",
      "change": "changed",
      "old": [
        "Shipping",
        "Ireland",
        "Delivery Time"
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
  "similarity": 0.86,
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
          "old": "2023-11-03",
          "new": "2026-10-23"
        },
        {
          "path": "time",
          "change": "changed",
          "old": "19:30",
          "new": "7:30 PM"
        }
      ]
    }
  ]
}
```

## apology-tone (drift)

```json
{
  "similarity": 0.343,
  "missing_phrases": [],
  "similarity_threshold": 0.5
}
```
