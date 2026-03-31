# 💰 NEXUS Revenue Guide

How to make money with the nexus entity farm.

## Revenue Streams (Ordered by Time-to-Money)

### 1. API-as-a-Service (Immediate)
Deploy nexus, charge for API access.

```bash
# Deploy to any $5/month VPS
bash vps-deploy.sh --chatgpt-key sk-... --perplexity-key pplx-...

# Generate client API keys
python3 nexus/api_server.py --generate-key client-001 --tier basic

# Clients call your API:
curl -X POST https://your-server.com/v1/tasks \
  -H "Authorization: Bearer nxk_..." \
  -H "Content-Type: application/json" \
  -d '{"type":"research","description":"Solana MEV strategies"}'
```

**Pricing:**
| Tier | Tasks/Day | Price |
|------|-----------|-------|
| Free | 10 | $0/month |
| Basic | 100 | $29/month |
| Pro | 1,000 | $99/month |
| Enterprise | Unlimited | Custom |

**Per-task pricing:**
| Task Type | Price |
|-----------|-------|
| Research | $0.50 |
| Writing | $1.00 |
| Coding | $2.00 |
| Analysis | $1.00 |
| Trading signals | $5.00 |

### 2. Freelance Automation (Days)
Use nexus to automate Upwork/Fiverr tasks.

```bash
# Accept a freelance task
python3 nexus/nexus_ctl.py chat "Write a 1500-word blog post about quantum computing trends" --provider chatgpt

# Research for a client
python3 nexus/nexus_ctl.py research "competitive analysis of AI chatbot platforms 2026"

# Generate code
python3 nexus/nexus_ctl.py chat "Write a Python FastAPI endpoint for user authentication with JWT"
```

**Workflow:**
1. Accept task on Upwork/Fiverr ($50-500/task)
2. Submit to nexus via CLI or API
3. Review and polish output (5 min)
4. Deliver to client
5. Net: $40-450/task for 10 min of your time

### 3. Content Generation (Weeks)
Monetize auto-generated content.

- **Blog posts** — SEO-optimized articles ($50-200/post)
- **Research reports** — market analysis, competitive intelligence ($100-500/report)
- **Documentation** — technical writing ($50-300/doc)
- **Social media** — thread creation, content calendars ($100-500/month)

### 4. GitHub Sponsors (Passive)
Open source nexus → attract sponsors.

```bash
# Enable Sponsors at: https://github.com/sponsors/EvezArt
# Add tiers: $5/month, $25/month, $100/month
```

### 5. Crypto Payments (Experimental)
Accept crypto for API access.

```bash
# Add to api_server.py:
# - Bitcoin Lightning invoice generation
# - Solana SPL token payments
# - Ethereum/USDC payments
```

## Deployment for Revenue

### Minimum Viable Deployment ($5/month VPS)

```bash
# 1. Get a VPS (DigitalOcean, Vultr, Hetzner, Linode)
# 2. SSH in
# 3. Run:
curl -sSL https://raw.githubusercontent.com/EvezArt/nexus/main/vps-deploy.sh | bash \
  --chatgpt-key "sk-..." \
  --perplexity-key "pplx-..." \
  --domain nexus.yourdomain.com

# 4. Generate your first API key
python3 /opt/nexus/nexus/api_server.py --generate-key client-001 --tier pro

# 5. Share the API endpoint with clients
```

### Scaling

| Revenue | Scale To | Cost |
|---------|----------|------|
| $0-100/mo | 1 VPS | $5/mo |
| $100-500/mo | 2 VPS + load balancer | $15/mo |
| $500-2000/mo | 3+ VPS + CDN | $30/mo |
| $2000+/o | Fly.io auto-scaling | $50+/mo |

## Marketing

1. **Product Hunt** — launch nexus as a product
2. **Twitter/X** — share results, demos, capabilities
3. **Reddit** — post in r/selfhosted, r/ChatGPT, r/artificial
4. **Hacker News** — "Show HN: NEXUS — Self-hosted multi-provider AI with memory"
5. **Dev.to** — write deployment tutorials

## Revenue Tracking

```bash
# Check revenue dashboard
curl http://localhost:8877/health | jq '.income'

# View ledger
cat nexus/income/ledger.jsonl

# Monthly report
python3 -c "
import json
from collections import defaultdict
monthly = defaultdict(float)
with open('nexus/income/ledger.jsonl') as f:
    for line in f:
        entry = json.loads(line)
        month = entry['ts'][:7]
        monthly[month] += entry.get('amount_usd', 0)
for month, total in sorted(monthly.items()):
    print(f'{month}: \${total:.2f}')
"
```
