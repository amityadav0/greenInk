# Feedback

Running notes for the hackathon's required feedback section. Fill in as we go: exact errors,
endpoints and timings, not impressions.

## Nebius Token Factory

- **What we used it for:**
- **What worked:** Oct 27, 2026: `GET /v1/models` listed 30 models (5 Nemotron) and all four configured Nemotron models answered a 5-token chat call on the first try through the OpenAI SDK (`scripts/check_models.py`). One key covered all four models.
- **What broke (exact error and endpoint):**
- **Time from zero to first call:**
- **Would we build with it again, and why:**

## Nebius AI Cloud

- **What we used it for:**
- **What worked:**
- **What broke (exact error and endpoint):**
- **Time from zero to first call:**
- **Would we build with it again, and why:**

## NVIDIA Nemotron 3.5 Lightning (triage, company profile from a website)

- **What we used it for:**
- **What worked:** with `chat_template_kwargs.enable_thinking=false` and `response_format: json_schema`, a triage-style call returned schema-valid JSON in 55 output tokens.
- **What broke (exact error and endpoint):** with thinking left on, a 120-token cap was spent entirely on reasoning: `finish_reason: length`, `content: null` (POST /v1/chat/completions). Reasoning models need thinking off or a larger output cap.
- **Time from zero to first call:**
- **Would we build with it again, and why:**

## NVIDIA Nemotron 3 Super (requirement extraction)

- **What we used it for:** extracting requirements with page number and verbatim quote from GeM bid PDFs (6 to 11 pages, about 5k to 10k input tokens).
- **What worked:** about $0.002 to $0.006 per bid. Quotes from bilingual GeM pages matched their cited page about 90% of the time on the first try (the verifier drops the rest). Output is not fully deterministic at temperature 0: the same bid gave 14 to 18 requirements across runs, so we extract once per document and cache.
- **What broke (exact error and endpoint):**
- **Time from zero to first call:**
- **Would we build with it again, and why:**

## NVIDIA Nemotron 3.5 Super VL (scanned pages, BoQ tables)

- **What we used it for:**
- **What worked:**
- **What broke (exact error and endpoint):**
- **Time from zero to first call:**
- **Would we build with it again, and why:**

## NVIDIA Nemotron 3 Ultra (judging, fixes)

- **What we used it for:** judging each verified requirement against the company profile; drafting fixes.
- **What worked:** with thinking on, it caught every planted trap (missing BIS licence, type tests) and compared figures correctly. Thinking off halved cost but produced wrong fails (it failed a 3 lakh turnover threshold for a company with 46 lakh), so we keep thinking on for judging only. Thinking makes up most of the cost: about 500 to 800 output tokens per requirement, or $0.01 to $0.05 per bid. A fix draft costs about $0.002.
- **What broke (exact error and endpoint):**
- **Time from zero to first call:**
- **Would we build with it again, and why:**
