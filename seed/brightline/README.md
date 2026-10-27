# Brightline Electricals (fictional demo company)

A fictional micro manufacturer of current transformers (CTs) and potential transformers (PTs).
Its documents go here, generated for the demo, with three deliberate traps:

1. A turnover certificate worded "Trading Business" where tenders require a manufacturer.
2. No BIS licence.
3. Turnover just under a common eligibility threshold.

Fictional data only: no real company names, people, GST/PAN numbers or prices (AGENTS rule 6).
Loaded by `make seed` (lane C).

`profile.json` is the company profile the demo judges against (`greenink.core.models.CompanyProfile`).
Its traps: `business_nature_wording` is "Trading Business", there is no BIS certification, and
average turnover is about 46.7 lakh, just under a common 50 lakh threshold.
