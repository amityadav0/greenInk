# GeM relay (Vercel, Mumbai)

GeM (bidplus.gem.gov.in) refuses connections from outside India; Railway has no Indian region
(tested from US and Singapore). This one function runs in Vercel's Mumbai region (`bom1`) and
forwards Green Ink's GeM requests. It only reaches `*.gem.gov.in` over HTTPS and requires the
`RELAY_KEY` shared secret.

    cd infra/gem-relay
    npx vercel login
    npx vercel deploy --prod          # first run links a project
    npx vercel env add RELAY_KEY production

Then set `GEM_RELAY_URL=https://<project>.vercel.app/api/relay` and the same `GEM_RELAY_KEY`
on the Railway api and worker services. Responses over ~4.5 MB (Vercel Hobby limit) fail;
bid PDFs are typically 100-250 KB, and oversized attachments are skipped.
