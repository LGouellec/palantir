
# Topic investing-news

JSON Schema
```
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "http://example.com/myURI.schema.json",
  "title": "SampleRecord",
  "description": "This schema has been created from JSON messages.",
  "type": "object",
  "properties": {
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
    "excerpt": {
      "type": "string"
    },
    "id": {
      "type": "string"
    },
    "images": {
      "type": "array",
      "items": {
        "type": "string"
      }
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
    "word_count": {
      "type": "number"
    }
  }
}
```

# Topic twitter-tweets

JSON Schema
```
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Generated schema for Root",
  "type": "object",
  "properties": {
    "id": {
      "type": "string"
    },
    "conversationId": {
      "type": "string"
    },
    "userId": {
      "type": "string"
    },
    "username": {
      "type": "string"
    },
    "name": {
      "type": "string"
    },
    "text": {
      "type": "string"
    },
    "html": {
      "type": "string"
    },
    "permanentUrl": {
      "type": "string"
    },
    "timestamp": {
      "type": "number"
    },
    "timeIso": {
      "type": "string"
    },
    "likes": {
      "type": "number"
    },
    "retweets": {
      "type": "number"
    },
    "replies": {
      "type": "number"
    },
    "bookmarkCount": {
      "type": "number"
    },
    "hashtags": {
      "type": "array",
      "items": {}
    },
    "mentions": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "urls": {
      "type": "array",
      "items": {}
    },
    "photos": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "videos": {
      "type": "array",
      "items": {}
    },
    "isRetweet": {
      "type": "boolean"
    },
    "isReply": {
      "type": "boolean"
    },
    "isQuoted": {
      "type": "boolean"
    },
    "source": {
      "type": "string"
    },
    "scrapedAt": {
      "type": "string"
    },
    "content_md": {
      "type": "string"
    }
  },
  "required": [
    "id",
    "conversationId",
    "userId",
    "username",
    "name",
    "text",
    "html",
    "permanentUrl",
    "timestamp",
    "timeIso",
    "likes",
    "retweets",
    "replies",
    "bookmarkCount",
    "hashtags",
    "mentions",
    "urls",
    "photos",
    "videos",
    "isRetweet",
    "isReply",
    "isQuoted",
    "source",
    "scrapedAt",
    "content_md"
  ]
}
```

# Topic wsj-articles

JSON Schema
```
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "http://example.com/myURI.schema.json",
  "title": "SampleRecord",
  "description": "This schema has been created from JSON messages.",
  "type": "object",
  "properties": {
    "author": {
      "type": "string"
    },
    "base_url": {
      "type": "string"
    },
    "content": {
      "type": "string"
    },
    "content_md": {
      "type": "string"
    },
    "excerpt": {
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
    "word_count": {
      "type": "number"
    }
  }
}
```

# Topic seeking-alpha-news

JSON Schema
```
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "http://example.com/myURI.schema.json",
  "title": "SampleRecord",
  "description": "This schema has been created from JSON messages.",
  "type": "object",
  "properties": {
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
    "excerpt": {
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
    "word_count": {
      "type": "number"
    }
  }
}
```