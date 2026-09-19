# v1 deployment verification

Verified on 2026-09-19 on the requested Windows host with Docker Desktop.

- Local app: http://localhost:5059
- Public app: https://recipes.pixelwood.co
- Project: `D:\Projects\RecipeApp`
- GitHub: https://github.com/rickycatto2/MenuKeeper

## Results

| Requested check | Result |
| --- | --- |
| Container starts | Pass. Alembic migrations applied; container healthy. |
| Manual recipe creation | Pass. Browser-created recipe with structured quantity, yield and linked step. |
| PDF import | Pass. Provided private sample imported with 22 ingredients and 10 steps. |
| Edit imported recipe | Pass. Browser edit saved; API round-trip verified. |
| Delete recipe | Pass. Browser deletion moved the temporary recipe to Recently deleted; restore covered by integration tests. |
| Search | Pass. Public browser search by ingredient plus automated title, ingredient, tag, cuisine and note searches. |
| Scaling | Pass. Split oil, ranges and portions tested. Doubled list and step text verified in browser; custom serving factor verified. |
| Metric / US | Pass. Both display orders checked; no unknown dry density invented; recipe-specific equivalents take priority. |
| Cook Mode | Pass. Previous/next, step number and scaled inline quantities checked at 390 × 844 and desktop widths. |
| Persistence | Pass. Recipe JSON exactly matched before and after container restart. Originals remained available. |
| Cloudflare | Pass. Route and DNS added; config validated before service restart. Public root and health endpoint returned HTTP 200. |

## Import quality

The sample's structured quantities and step links are locally parsed and preserved. OpenAI metadata enrichment succeeded with the server-side key. The vinegar inconsistency and additional unmeasured salt usage remain visible warnings; the app did not silently reconcile either. Earlier verification imports are soft-deleted and remain recoverable.

Image OCR, scanned PDF OCR, public URL JSON-LD extraction, original-file preservation, photo uploads, household history and dictionary edits are covered by automated integration tests. OCR fixtures are generated during tests. The private reference PDF is never committed or included in the Docker build.

The local test run passed **17 tests**, including both private reference PDF tests. GitHub Actions passed the public suite, where the two private-PDF tests skip because the PDF is deliberately absent. See [the successful app milestone run](https://github.com/rickycatto2/MenuKeeper/actions/runs/35467194557).

## Operations

The existing Cloudflare config was backed up before editing. Removing just the new ingress stanza reproduces the prior config byte-for-byte. The existing Windows service was restarted by the user from Administrator PowerShell after validation. No tunnel container was added.

The documented backup script was exercised. Its ZIP contains `app.db` and preserved originals; the app recovered after restart. The archive is in the Git-ignored local `backups` folder. `.env` is intentionally excluded.

Staged files were checked for the configured API key and prohibited user-data paths before pushing. `.env`, databases, uploaded images/PDFs, private fixtures and backups are Git-ignored. No user data is needed to run CI.

## Limits of verification

Responsive behavior was checked using a mobile-sized browser viewport, not a physical iPhone. The test browser did not provide a screen wake lock; the graceful fallback was verified. Actual camera permission and wake-lock behavior depend on Safari/iOS and should be checked on the household phone. Website import can still be blocked by a publisher, and OCR/AI interpretations require source review. No authentication was added, as requested.
