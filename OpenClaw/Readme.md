## Pre-work(setup): 
* terminal: sudo curl -fsSL https://openclaw.ai/install.sh | bash
* type in ID password
* I understand this is personal-by-default and shared multi-user use requires lock-down, continue? - Choose "yes".
* Onboarding mode: - Choose "QuickStart"
* Model/Auth Provider: Choose model, register AI model accounts and copy API
* Skip(Skills, hooks, etc.) - can be set later.
* How do you want to hatch your bot? - choose "Hatch in TUI"./"Open the Web UI"

### My Configuration
| Setting | Value |
|---|---|
| Model | `google/gemma-4-31b-it:free` via OpenRouter |
| Fallbacks | `nvidia/nemotron-3-super-120b-a12b:free`, `meta-llama/llama-3.3-70b-instruct:free`, `mistralai/mistral-small-3.1-24b-instruct:free` |
| Channel | WhatsApp |
| Web Search | Tavily |

---
### Known Gotchas

- **OpenRouter `auto` router requires credits** — do not set it as your primary model if you're on the free tier. Use a specific model ID instead.
- **Free tier daily limit** - OpenRouter provides free,, rate-limited access to select AI models, with daily limits based on account credit history—typically 50 requests/day for new users, increasing to 1000/day after purchasing at least $10 in credits. Free models (ID ending in :free) also have a 20 requests-per-minute (RPM) limit and are designed for testing rather than production
- **Deprecated models** — free model availability changes. If you get a 404, check [openrouter.ai/models](https://openrouter.ai/models) for the current model ID.
- **API key not set** — the OpenRouter plugin needs an explicit `apiKey` in `openclaw.json`. The plugin being `enabled: true` alone is not enough.
- Set the key safely using:
```bash
  python3 -c "
  import json
  with open('/Users//.openclaw/openclaw.json', 'r') as f:
      c = json.load(f)
  c['plugins']['entries']['openrouter']['config'] = {'apiKey': 'sk-or-v1-...'}
  with open('/Users//.openclaw/openclaw.json', 'w') as f:
      json.dump(c, f, indent=2)
  print('Done!')
  "
```
- **Never manually edit `openclaw.json` with a rich text editor** — smart quotes will break the JSON5 parser. Use `nano` or the Python snippet above.
