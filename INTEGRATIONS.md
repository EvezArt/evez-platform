# Integrations

## Supported Providers

### Inference
- Groq (primary)
- GitHub Models
- SambaNova
- Cerebras (coming)

### Channels
- Discord
- Telegram
- Slack
- StreamChat

### Storage
- Local filesystem
- S3-compatible
- Cloudflare R2

## Using

```python
from client import EVEZClient
client = EVEZClient()
result = client.inference("Hello")
```
