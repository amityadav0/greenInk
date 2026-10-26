# GeM bidplus: notes from the Oct 26 spike

Findings from `scripts/gem_spike.py`, run from a laptop in India on Oct 26, 2026, and from reading five current-transformer bids by hand. These notes are for whoever builds `greenink.sources.gem` (lane C) and `analysis.extract` (lane A).

## Search

- Flow: GET `/all-bids` (session cookies plus the `csrf_bd_gem_nk` token embedded in the page script), then POST `/all-bids-data` with form fields `payload` (JSON) and `csrf_bd_gem_nk`. Results come 10 per page as `response.response.docs`, with the total in `numFound`.
- Useful fields: `b_id`, `b_bid_number`, `b_category_name[0]`, `bbt_title`, `ba_official_details_minName` and `ba_official_details_deptName` (buyer), `b_total_quantity`, `final_end_date_sort`, `b_bid_type`.
- `final_end_date_sort` holds IST wall-clock time with a `Z` suffix. The page renders it with UTC getters, so read it as IST.
- Documents: `/showbidDocument/{b_id}`. Reverse auctions use `/showradocumentPdf/{b_id}` (`b_bid_type` 2) or `/showdirectradocumentPdf/{b_id}` (type 5).
- `searchType: "fullText"` matches loosely: "current transformer" also returns calibration services and hand files (149 hits, of which 14 had the phrase in the title). `searchType: "exact"` answers HTTP 404 on this endpoint. Filter by title on our side.
- Sorting: `Bid-End-Date-Oldest` (the default) puts bids closing today first. `Bid-Start-Date-Latest` gives fresher bids.
- At 1 request a second, 30 PDFs plus their search pages took about 2 minutes. No blocking was seen from an Indian residential IP. A cloud host has not been tested yet.

## Bid documents

- The bid PDF is a GeM template of 5 to 11 pages with a text layer. Labels are bilingual: the Hindi glyphs extract as garbage with PyMuPDF and the English labels extract cleanly, so quotes must use the English text.
- A label and its value sit on separate lines. Quotes therefore span a line break, so the verifier should normalise whitespace before fuzzy matching.
- Page 1 holds the eligibility summary: OEM turnover, years of experience, MSE and startup relaxation, documents required. Page 2 holds EMD, ePBG, past performance %, bid type and inspection. Page 3 or later holds MSE and MII purchase preference, standard experience, turnover and past-performance clauses, the specifications, consignees and delivery days, then buyer-added terms (ATC).
- The last pages carry GeM's disclaimer to buyers and the GTC and labour-law boilerplate. That is not a bidder requirement, and the prompt excludes it.
- **Much of the risk sits outside the bid PDF.** Bids link to buyer-uploaded specifications and ATC documents (`mkp.gem.gov.in/.../buyer_documents/...` or `/uploaded_documents/...`), BoQ spreadsheets (`.xlsx` under `/resources/upload_nas/...`) and the GTC by date. The PDF itself says only "As per BHEL specification (Attached)" or "Buyer uploaded ATC document Click here to view the file". Ingest should follow these links (`page.get_links()`) and store each as a `tender_documents` row.
- The one linked specification fetched was a **scanned PDF with no text layer** (3 pages, 0 characters), so the Super VL vision path is needed for real bids, not only for edge cases.
- BoQ attachments are `.xlsx`. Parsing them needs a spreadsheet reader, which is not in the approved stack yet.
- Bid PDFs include buyer officials' names and email addresses. Never copy them into the repo, fixtures or prompts.
