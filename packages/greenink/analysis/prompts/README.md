# Prompts

Versioned prompt files, for example `extract.v1.md`. The version is part of the cache key,
so changing a prompt means adding a new file and bumping the extractor or judge version.

Tender and website text never goes in these files. The LLM gateway wraps it in a delimited
data block and tells the model it is content to analyse, never instructions to follow.

`extract.v1.md` was written after reading five live GeM current-transformer bids by hand
(notes in `docs/GEM_NOTES.md`). Its output schema is `greenink.core.models.ExtractionResult`.
