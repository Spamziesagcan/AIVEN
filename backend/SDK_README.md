Lightweight SDK
================

This folder contains a minimal SDK wrapper around the project's LLM client.

Usage example:

```python
from backend.app.sdk import LightweightSDK

sdk = LightweightSDK()
messages = [{"role": "user", "content": "Hello"}]
resp = sdk.generate(messages)
print(resp["text"])
```

The `LightweightSDK` accepts an optional `client` parameter for dependency
injection to make testing easier.
