# MenuKeeper

A shared household cookbook for Ricky and Ellie. FastAPI, SQLAlchemy, SQLite and a mobile-first browser interface, hosted by Docker Desktop on Windows. No login in v1, as requested. Anyone who can reach the configured hostname can view and change the household cookbook.

## Start and stop

In PowerShell:

```powershell
Set-Location D:\Projects\RecipeApp
# First setup only: copy .env.example to .env, then edit .env locally.
docker compose up -d --build
docker compose ps
```

Open <http://localhost:5059> or, after tunnel configuration, <https://recipes.pixelwood.co>. Docker binds only to Windows loopback; the existing Windows Cloudflare service supplies public HTTPS. The stack does not contain cloudflared.

```powershell
docker compose stop                 # Stop; keep all data
docker compose start                # Start again
docker compose logs --tail 100      # Recent server logs
docker compose down                # Remove container; ./data remains
```

Docker Desktop must be running. Enable its normal start-at-login setting if wanted; `restart: unless-stopped` restarts the container with Docker.

## Configuration

`.env` is local and ignored by Git and the image build:

```dotenv
OPENAI_API_KEY=your-key-here
OPENAI_MODEL=gpt-4.1-mini
PUBLIC_ORIGIN=https://recipes.pixelwood.co
```

The model is configurable. The key is read only on the server. It is never returned by the API, inserted into frontend JavaScript, or included in import diagnostics. After changing `.env`, run `docker compose up -d --force-recreate`. `/api/health` reports only whether a key is configured, not whether the account has credit.

No key is required for viewing, searching, scaling, editing, conversions or Cook Mode. Without a key, text/PDF extraction and local image OCR still work. Less structured imports are flagged for manual review.

## Use the cookbook

- **Add recipe:** paste text, enter a public recipe URL, upload one PDF or an image, or write it manually. Images use local Tesseract OCR; scanned PDF pages are rendered with Poppler and OCR'd. OCR always triggers a visible review warning. Upload limit: 20 MB; PDF limit: 20 pages. JPEG/PNG/WebP are the most reliable phone formats; export HEIC to JPEG if needed.
- **Sources and quality:** preserve original text, downloaded HTML, PDF or image, plus extracted text, normalized output, validation warnings and redacted errors. Open these from the recipe's **The original** section. Websites with Recipe JSON-LD are preferred; blocked or JavaScript-only sites may require pasted text or a PDF.
- **Structured source priority:** recognizable ingredient/step sections are parsed locally. If all quantities and most ingredient links can be read, AI suggests metadata only; it cannot reinterpret the source amounts. Messy sources use structured AI extraction, with one retry for invalid ingredient links and a local fallback. Review all imports before cooking. A model can make extraction mistakes; original sources remain available.
- **Edit:** ingredients have stable IDs, separate amounts/ranges, units, names, preparation, alternatives, optional flags and group labels. Steps contain ingredient-reference tokens inserted by the editor. Expand a reference to choose the full amount, an explicit amount, a stated fraction of total, or name-only mention. A token must occur exactly once and link to an existing ingredient. Plain numbers typed outside references do not scale and measured unlinked quantities trigger warnings.
- **Scale:** select 0.5×, 1×, 1.5× or 2×, or enter target servings if the original yield is known. The same deterministic backend renderer updates both ingredients and steps. Cooking times and oven temperatures do not scale.
- **Units:** choose Metric first (Ricky) or US first (Ellie). The preference is remembered on that browser. Recipe-supplied equivalent measurements outrank the editable local dictionary. Flour starts at 125 g/cup; granulated sugar at 200 g/cup. Known liquids use 240 ml/cup, 15 ml/tbsp and 5 ml/tsp. Unknown dry ingredients retain their original volume; no universal density is assumed. Weight-to-weight conversions use standard factors. Displayed values are rounded to three decimals; stored amounts are not rounded.
- **Cook Mode:** one large step at a time, previous/next, current scale and unit preference. Attempts screen wake lock in supported secure browsers, reacquires when returning to the page, and releases on exit. Unsupported browsers keep their normal screen timeout.
- **History:** Made it saves a date, optional note and optional shared rating. Prior cooking notes remain visible. Make again is a household favorite flag.
- **Delete:** moves a recipe to Recently deleted with immediate Undo. Restore remains available indefinitely in v1; there is no automatic irreversible purge.
- **Search:** words match title, ingredients, preparation/alternatives, tags, cuisine, category, description and notes. Filter by diet, cuisine, meal type, total time, tag, or Make again. Unknown total times are excluded by a time filter.

On iPhone, open the HTTPS hostname in Safari and optionally use **Share → Add to Home Screen**. Photo upload uses the browser's photo library/camera chooser. A dedicated offline mode or native app is not included.

## Data and migrations

```text
data/
  app.db                 SQLite structured recipes, conversions and history
  app.db-wal, app.db-shm  SQLite runtime files when present
  originals/             Uploaded or downloaded originals
  images/                Browser-safe resized recipe photos
  diagnostics/           Extracted text, normalization and warnings
```

The whole directory is bind-mounted to `/data`; it survives container replacement and restart. Recipes are validated typed structures stored in a SQLAlchemy JSON column, not formatted prose. The body contains ingredients, linked usages and steps. Separate relational tables hold cooking history and the conversion dictionary. Stable ingredient IDs and a centralized household lookup leave room for future authentication. Alembic applies schema migrations before the server starts.

## Update

```powershell
Set-Location D:\Projects\RecipeApp
.\scripts\Backup.ps1
git pull --ff-only
docker compose up -d --build
docker compose ps
```

Do not overwrite `.env` or delete `data`. Code updates rebuild the image; database migrations run automatically. Back up before migrations. To roll back code, check out a known commit and rebuild; restore the corresponding data backup if a migration is incompatible.

## Backup and restore

Run `scripts\Backup.ps1` to briefly stop the app, zip the complete data folder, and start it again. Backups default to `backups\` (Git-ignored). Copy archives to another disk for protection against host failure. Keep `.env` separately in a secure location; it is intentionally omitted from archives.

To restore: stop the app, rename the current `data` folder to a dated recovery folder, extract a backup ZIP into the project so it recreates `data`, then start the container. Never mix files from two database backups or copy only `app.db` while the app is writing. Keep the previous data folder until you verify recipes and originals.

## Existing Cloudflare Tunnel

The route is an addition to `C:\cloudflared\config.yml`, before its existing final 404 rule:

```yaml
  - hostname: recipes.pixelwood.co
    service: http://localhost:5059
```

`scripts\Add-CloudflareRoute.ps1` preserves the existing config text and all ingress rules, writes a timestamped backup, validates a candidate before applying, then validates the actual config and checks rule matching. It refuses to replace an existing conflicting hostname. It does not overwrite existing DNS records.

```powershell
# Administrator PowerShell is generally required for the service restart.
.\scripts\Add-CloudflareRoute.ps1 -ConfigureDns -RestartService
```

The script uses the tunnel ID already in the config and the existing Windows service `CloudflaredOverseerr`. Change parameters if those paths/names differ. DNS creation requires cloudflared's existing account certificate. If DNS creation fails, add a proxied CNAME for `recipes` pointing at the existing tunnel's `<tunnel-id>.cfargotunnel.com`, then validate and restart the service. Existing routes remain intact.

Manual verification:

```powershell
cloudflared tunnel --config C:\cloudflared\config.yml ingress validate
cloudflared tunnel --config C:\cloudflared\config.yml ingress rule https://recipes.pixelwood.co
Invoke-RestMethod https://recipes.pixelwood.co/api/health
```

Reference: [Cloudflare configuration and ingress validation](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/configuration-file/).

## API / future iPhone Shortcut

Interactive API schema: <http://localhost:5059/docs>. A Shortcut can use **Get Contents of URL**, POST to `https://recipes.pixelwood.co/api/import`, and send JSON:

```json
{"text":"Recipe title\nIngredients\n1 tbsp olive oil\nInstructions\nAdd olive oil (1 tbsp)."}
```

or `{"url":"https://example.com/recipe"}`. File imports use multipart field `file` at `/api/import/file`. Responses include the recipe ID; open `https://recipes.pixelwood.co/#recipe/<id>`. The request can take up to a few minutes for OCR/AI. Originals are local; source text is sent to OpenAI only for configured AI import processing (`store=false`). API integration follows [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

Other endpoints: `/api/recipes` (GET/POST), `/api/recipes/{id}` (GET/PUT/DELETE), `/{id}/restore`, `/{id}/history`, `/{id}/image`, and `/api/conversions` (GET/POST/PUT/DELETE). Rendering parameters are `factor` and `preference=metric|us`.

## Tests and private reference PDF

```powershell
docker compose run --rm -v "${PWD}:/app" recipes python -m pytest -q
```

Tests use a temporary database and disable OpenAI calls. Coverage includes split quantities, range/fraction scaling, conversions and recipe-specific priority, link rejection, CRUD/restore/search/history, safe URL handling, JSON-LD, photo upload, image OCR and scanned PDF OCR. Put the private sample at `tests\fixtures\Sweet Potato One Pan Bake.pdf` to enable the optional reference PDF tests; otherwise those tests skip. The PDF is ignored by Git and Docker builds.

The reference checks groups, ranges, alternatives, to-taste amounts, split oil, sauce, preserved originals and the vinegar reconciliation warning. No test fixture upload or database belongs in Git.

## Practical v1 limits

Single-recipe imports only. Local OCR is English and can misread scans. Local parsing expects recognizable sections; ambiguous content is saved with warnings for editing. AI normalization has structural validation, but its interpretation still needs source review. No accounts, offline sync, meal planning or automatic multi-recipe PDF splitting. The server is designed for a small trusted household, not an anonymous high-traffic recipe hosting service.
