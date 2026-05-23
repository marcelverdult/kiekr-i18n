# Glossary

Per-language canonical translations of recurring tech terms, fed to
the DeepL API as a glossary when seeding new keys.

Format: TSV (tab-separated, two columns, no header). One row per
term:

```
node	Knoten
repeater	Repeater
region	Region
```

Add new entries when you notice a term being translated inconsistently
across keys. Open a PR; the KiekR team will merge after a sanity
check.

The English column is the lookup term; the right column is the
translation in the target language. Case-insensitive lookup at DeepL.
