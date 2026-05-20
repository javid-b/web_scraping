# Per-shop setup playbook

A step-by-step guide for adding a new shop to the price scraper. Same recipe
for every shop — irshad, bakuelectronics, mgstore, elitoptimal, soliton, w-t,
and any future addition. Allow ~10 minutes per shop once you've done it twice.

For each shop, work through these steps **in order**. Stop as soon as a step
succeeds — you don't always need every step.

---

## Step 1 — Quick reachability check

Try the cheapest engine first.

```
price_scraper fetch --shop <shop_id> "https://<shop>.az"
```

Open `data\dump.html` in Notepad, **Ctrl-F** for a real category name you saw
on the site (e.g., "Smartfon", "Noutbuk", or any brand like "Samsung").

| Result | What it means | Next step |
|---|---|---|
| Word found in dump | Plain HTTP works. Keep default `engine: cloudscraper` | go to Step 2 |
| Word not found, dump ~50–200 KB | Site renders content via JS (kontakt-style) | switch to playwright (Step 1b) |
| Error 403 / 429 | Bot block on cloudscraper too | try playwright; if still blocked, paste me the error |

### Step 1b — Switch to Playwright for this shop

In `shops.yaml`, in the shop's block:

```yaml
    request:
      engine: playwright
      delay_seconds: 2.0
      timeout: 30
```

Re-run the `fetch` command. The word should now be in the dump.

---

## Step 2 — Find the menu

```
price_scraper suggest-menu <shop_id>
```

Look at **Candidate 1**. Ask yourself:

- Are these the URLs you want to scrape (real category pages)?
- Does the count look right (usually 10–200)?

| Result | Action |
|---|---|
| Looks right | Copy the `menu_selector` line into `shops.yaml` under the shop's `discovery:` block |
| Wrong / too broad / too narrow | Look at Candidate 2 and 3. Re-run with `--limit 10` for more |
| "No navigation menu detected" | Menu is JS-rendered → set `discovery.engine: playwright` (Step 2b) |

### Step 2b — JS-rendered menu

In `shops.yaml`:

```yaml
    discovery:
      mode: menu
      menu_selector: "<fill in after Step 2c>"
      engine: playwright
```

Then re-run `suggest-menu` — it now uses Playwright for the menu fetch and
you get more candidates.

### Step 2c — Manual selector (fallback)

If `suggest-menu` still doesn't find it, open the shop in your browser,
**right-click** the menu link → **Inspect**. Look at the anchor's class.
Plug it in directly:

```yaml
    discovery:
      mode: menu
      menu_selector: "a.<the-class>[href]"
```

---

## Step 3 — Pick one category to test

After `discovery:` is configured, do a dry-run to see how many URLs come back:

```
price_scraper suggest-menu <shop_id>
```

Pick **one** URL from the list (the simplest one — usually phones or
laptops). You'll use it in the next steps.

---

## Step 4 — Find the product card selectors

```
price_scraper suggest <shop_id> "<one category URL from Step 3>"
```

You'll see something like:

```
=== Layout 1 — 24 cards, 24 with valid price ===
  listing:
    product_selector: ".product-card"
    name_selector:    ".product-title"
    price_selector:   ".price"

  Sample extraction:
    1499.00 ₼   Apple iPhone 15 ...
```

Check the **Sample extraction**:

- Names look like real products?
- Prices look right (the **current** price, not a crossed-out old price)?

| Result | Action |
|---|---|
| Both look right | Paste the `listing:` block into `shops.yaml` |
| "No product layouts detected" | Listing page is JS-rendered too — set `request.engine: playwright` |
| Prices wrong (installment / shipping) | Re-run with `--limit 5`, try Layout 2 or 3 |

---

## Step 5 — Pagination

The `suggest` command also prints a pagination block automatically (at the
end of its output). Three patterns:

| Site shows... | YAML block to paste |
|---|---|
| `?page=2`, `?page=3` | `mode: query`, `param: page` |
| `/page/2/`, `/page/3/` | `mode: path`, `template: "/page/{n}"` |
| Next button / `<a rel="next">` | `mode: next_link`, `next_selector: 'a[rel="next"]'` |
| "Load more" button | `mode: next_link`, `next_selector: ".load-more-class"` |

Paste the entire `pagination:` block under `listing:` in `shops.yaml`. The
scraper auto-stops when there are no more pages — you don't have to count.

---

## Step 6 — Sanity-check selectors against a real page

Before running a full scrape, dry-run the configured selectors:

```
price_scraper inspect <shop_id> "<one category URL from Step 3>"
```

You should see real names and prices line by line. If you see
`found: 0 products`, go back to Step 4.

---

## Step 7 — Test scrape (one category)

Temporarily, in `shops.yaml`, change the shop's `discovery:` to:

```yaml
    discovery:
      mode: static
      category_urls:
        - <the one URL from Step 3>
```

Then:

```
price_scraper scrape --shop <shop_id>
```

Watch for:

- `categories=1`, `pages=N`, `stored=M`
- All `INFO` lines show pages incrementing 1, 2, 3, ...
- No errors

| Result | Action |
|---|---|
| `stored > 0`, no errors | Selectors work. Switch back to `mode: menu` and go to Step 8 |
| `stored = 0` | Selector wrong → repeat Step 4 |
| Errors | Read the error, paste it to me |

---

## Step 8 — Full scrape

Restore `discovery:` to whatever you set up in Step 2:

```yaml
    discovery:
      mode: menu
      menu_selector: "<from Step 2>"
      # engine: playwright   # if needed
```

Run the full thing:

```
price_scraper scrape --shop <shop_id>
```

This can take **minutes to hours** depending on shop size and engine. With
cloudscraper, ~0.5 s per page. With Playwright, ~3 s per page. A shop with
50 categories × 10 pages = 500 page loads = 4 min with cloudscraper,
25 min with Playwright.

---

## Rules of thumb

- **Always start with `cloudscraper`.** Only escalate to Playwright when
  proven necessary. Most kontakt-style sites use JS for the menu but
  server-render the listings — that's the case where
  `discovery.engine: playwright` + `request.engine: cloudscraper` is perfect.
- **One shop at a time.** Don't try to configure all 6 at once; do one
  end-to-end, then the next.
- **Save your work after each shop.** After kontakt works:
  `git add config\shops.yaml && git commit -m "configure kontakt"`.
  Same after each shop. If the YAML breaks during another shop's setup,
  you can `git checkout` to revert just that change.
- **The `inspect` and `suggest` commands NEVER write to the database.**
  They're safe to run as many times as you want while tuning.
- **The `scrape` command APPENDS rows** to the DB every time it runs.
  If you run it twice on the same day, you get duplicate observations
  with slightly different timestamps. That's fine for production; for
  testing you may want to drop the DB: `del data\prices.db`.

---

## Quick-reference: what each command does

| Command | Reads HTTP? | Reads HTML? | Writes DB? |
|---|---|---|---|
| `fetch --shop X URL` | yes | no | no (writes `data\dump.html`) |
| `suggest --shop X URL` | yes | yes | no |
| `suggest-menu X` | yes | yes | no |
| `inspect X URL` | yes | yes | no |
| `scrape --shop X` | yes | yes | **yes** |
| `merge` | no | no | **yes** |
| `history X "product"` | no | no | no (reads DB) |

---

## When you get stuck

Paste back to me:

1. The shop id
2. Which step you're on
3. The exact command + its output
4. (If `suggest` returns nothing) one product card's `outerHTML` from DevTools

That's usually enough to unblock you in one round.
