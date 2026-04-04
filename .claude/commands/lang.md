# /lang — Switch CLI Language

Switch the ClaudeSafeOps CLI output language at runtime.

## Arguments

- `/lang` — show current language and available options
- `/lang zh` — switch to Chinese
- `/lang ko` — switch to Korean
- `/lang en` — switch to English
- `/lang auto` — auto-detect from system locale

## How to execute

1. If no argument, show current language and list available locales:
   ```bash
   ls src/config/locales/*.yaml
   ```
   Display as: `Current: en | Available: en, zh, ko`

2. If a language code is provided:
   - Set the environment variable: `export CSOPS_LANG=<lang>`
   - Inform the user the language has been switched
   - Show a sample message in the new language to confirm (e.g., the banner tagline)

3. The language change takes effect for all subsequent CLI output in this session.

## Notes
- Language files are at `src/config/locales/{lang}.yaml`
- To add a new language, copy `en.yaml` to `{lang}.yaml` and translate the values
- The `auto` option detects from system locale variables (LC_ALL, LC_MESSAGES, LANG)
