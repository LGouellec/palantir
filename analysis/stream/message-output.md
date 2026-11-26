# Topic financial-news

JSON Schema
```
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "http://example.com/myURI.schema.json",
  "title": "SampleRecord",
  "description": "This schema has been created from JSON messages.",
  "type": "object",
  "properties": {
    "id": {
      "type": "string"
    },
    "author": {
      "type": "string"
    },
    "category": {
      "type": "string"
    },
    "content": {
      "type": "string"
    },
    "content_md": {
      "type": "string"
    },
    "published_date": {
      "type": "string"
    },
    "scraped_at": {
      "type": "string"
    },
    "title": {
      "type": "string"
    },
    "url": {
      "type": "string"
    },
    "source": {
      "type": "string",
      "enum": ["investing", "seeking-alpha", "wsj", "twitter"]
    }
  }
}
```