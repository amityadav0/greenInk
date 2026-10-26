# Prompts

Versioned prompt files, for example `extract.v1.md`. The version is part of the cache key,
so changing a prompt means adding a new file and bumping the extractor or judge version.

Tender and website text never goes in these files. The LLM gateway wraps it in a delimited
data block and tells the model it is content to analyse, never instructions to follow.

`extract.v1.md` is written after reading five bids by hand (SPEC ship plan, Oct 26).
