---
name: stale-feed-triage
description: Diagnostic playbook for when a JSON or CSV data feed appears to have stopped updating — content frozen at an old date even though the HTTP endpoint still returns 200. Use this skill whenever the user reports that a data source "hasn't updated", is "stuck", "frozen", or "stale", or when a polled feed's content date stops advancing while the endpoint stays alive. Especially relevant for government data feeds (CDC, BLS, Census, etc.) that have a history of silently migrating to new URLs without announcement.
---

# Stale Feed Triage

## When this applies

Something we poll or read regularly has stopped advancing. The HTTP request still succeeds. The file still parses. But the timestamps and "as-of" dates inside the content are frozen at some point in the past. Everything *looks* fine from a monitoring standpoint, which is exactly what makes this insidious.

The default instinct is to assume the source is having an outage and to wait it out, or to assume our code broke. Both are usually wrong. The most common cause — at least for government and large-institution data feeds — is that the vendor has silently published a new endpoint with a different URL and/or schema, kept the old endpoint serving cached or empty content, and made no announcement. Our code is reading the right URL; the URL is just dead.

## What to verify first

Before doing any hunting, confirm what's actually true:

1. **Is the content frozen, or just the headers?** Fetch the feed and read the dates *inside* the content (fields like `date_updated`, `last_updated`, `week_end`, `as_of`, or whatever the schema uses). Do not trust HTTP `Last-Modified` — vendors often re-write the file on schedule even when nothing inside changed, so the header keeps advancing while the content is stale. The polling log (if there is one) usually tells the same story across many fetches.

2. **Is our code reading the field correctly?** Briefly verify that the parser isn't dropping the field on the floor. Usually it isn't, because the same code worked last week. But rule it out so you can move on with confidence.

3. **Is the public-facing site that displays this data also showing the stale value?** If yes, the data is genuinely frozen at the source for everyone — but the *displayed* page often comes from a different feed than the one we're polling, so confirm this carefully (see below). If the public site shows fresh data and our feed shows stale data, the answer is almost certainly "they moved the endpoint and didn't tell anyone."

## The single most useful move: ask the user to look at the dashboard

When curl can render the data feed but not the dashboard (because the dashboard is a JS-rendered SPA), the fastest path is to **ask the user to open the public-facing page in a real browser and tell you what date it's showing**. This sounds trivial but it's the highest-signal step in the whole playbook. In thirty seconds you find out:

- whether the live page is showing the same stale week we are (→ real source-side freeze)
- or whether it's showing a fresher week (→ we're on a deprecated endpoint and need to find the new one)

Do not propose installing Selenium or chromedriver to render the page yourself. It's heavy infrastructure for a one-shot question that the user can answer in seconds. The same goes for any other "let me automate a browser" idea — the user's eyeballs are faster.

If you do need DOM details the user can't easily eyeball (the value of a specific element, what a network request returned), ask them to open DevTools, look at the Network tab, and either describe what they see or paste a URL. This is still faster than headless browser setup for a one-off.

## Finding the new endpoint when the old one is dead

Once you've confirmed the public site has fresher data than our feed, the new endpoint is somewhere. Here's where to look, roughly in order of speed:

### 1. The dashboard page itself

Fetch the HTML of the page that displays the fresh data and search for clues:

- Attributes like `data-config-url`, `data-source`, `data-feed`, `data-api`, or similar. These are often dropped on a widget div and point straight at a JSON config file that lists the real data URLs.
- Script `src` attributes pointing at framework bundles (e.g., `openVizWrapper`, `cdc-viz`, `tableau`, custom widget libs). The framework name tells you what to grep for in the next step.
- Inline `fetch(`, `XMLHttpRequest`, or `axios.get(` calls — sometimes the URLs are literally embedded.
- Iframe `src` attributes — sometimes the dashboard is just an embed of a Tableau / Power BI / custom viz hosted elsewhere.

If you find a config URL, fetch it and grep for `.json`, `.csv`, or absolute/relative URLs that look like data paths. Government dashboards in particular often use a one-config-points-to-many-data-files pattern, so the config is gold.

### 2. Sibling files in the same directory

If the dead endpoint is at, say, `vendor.gov/data/path/oldname.json`, try:

- The same filename in adjacent directories (`/path2/oldname.json`, `/newpath/oldname.json`)
- Variations on the naming convention in the same directory: capitalization changes, abbreviation changes, `_v2` suffixes, dropping a prefix the vendor used to brand the old version (e.g., a project-name prefix that's no longer relevant). Government agencies often rename feeds when reorganizing program ownership.
- Probe with HEAD requests rather than full GETs to keep this cheap.

### 3. Catalog/registry APIs

Many large data publishers run a catalog you can query directly. Two patterns worth knowing:

- **Socrata** (data.cdc.gov, data.cityofnewyork.us, dozens of others): `GET /api/catalog/v1?q=<keyword>&only=datasets&limit=10` returns datasets with their `updatedAt`. Compare that timestamp to "now" — if a dataset matching the topic was updated in the last week and our current dataset was last updated months ago, you've probably found the successor. Look for naming pattern shifts (e.g., the old dataset is called "X Public Y" and the new one is called "Vendor Z Data for Y" — that kind of rebrand is a strong signal of a migration).
- **CKAN** (data.gov and most US municipal portals): `GET /api/3/action/package_search?q=<keyword>` returns the equivalent. Same approach: filter by recent `metadata_modified`.

### 4. The vendor's GitHub org or status page

Worth a quick check but rarely productive. Vendors with engaged data teams (some CDC programs, NWS, USGS) sometimes announce migrations in their GitHub repo READMEs or release notes. Most don't. Don't spend more than a minute or two here unless the prior steps came up empty.

### 5. Web search

Almost always disappointing for this specific problem. Migrations of obscure data feeds rarely generate articles, and search results will be dominated by the vendor's own marketing pages for the product. Only worth trying if all other paths are exhausted, and budget it tightly.

## After finding the new endpoint

Once you've located the replacement:

1. **Compare schemas explicitly.** Don't assume field names carried over. Common changes: `snake_case` → `Title_Case`, separate per-category files combined into one with a category column, ISO timestamps replaced with human strings, week ranges replaced with single dates, addition of new dimensions like region or pathogen. List the field-by-field mapping before touching code.

2. **Look for what's *missing*.** Sometimes a migration drops fields we relied on. If the old feed had `Coverage` as a percentage and the new one doesn't, that's a quiet capability loss — flag it to the user rather than silently dropping the column.

3. **Verify update cadence.** The new feed may publish on a different day or time than the old one. If we have schedule-sensitive code (cron jobs, posting workflows), check what day the new endpoint actually refreshes and whether downstream timing assumptions still hold. The polling log is the cleanest evidence here once a week or two has passed.

4. **Keep the old field/column names if you reasonably can.** If our database, CSV, or analytics pipeline has historical data under specific column names, preserving them across the migration makes longitudinal analysis painless. Parse/convert the new feed's values into the old shape rather than reshaping everything downstream.

5. **Leave a breadcrumb for next time.** Write a project memory documenting: which endpoint was deprecated, which replaced it, schema differences, the date of the migration, and how you found the new one. The next time this happens (in the same project, with the same vendor, or both), you want to go straight to the productive step.

## What to avoid

- **Don't email the vendor first.** It's sometimes the right answer eventually, but response times are usually measured in weeks, and you can almost always find the new endpoint in fifteen minutes of investigation. Email is the *last* resort for confirming you've understood correctly, not the first move.
- **Don't add a "retry harder" loop in our code.** If the endpoint returns 200 with stale content, no amount of retrying will help. Retries are for transient failures, not for content staleness.
- **Don't paper over it with a fallback to a different field.** If you find yourself writing "if `date_updated` is missing, fall back to `Date_Updated`, then fall back to parsing `Time_Period`" — stop. You've found the migration. Update the code to read the new schema cleanly.
- **Don't claim "the source is just down" without checking the public dashboard.** That conclusion is only valid after you've confirmed the public-facing page is *also* showing the stale data.

## Why this skill exists

This pattern shows up across many vendors, and each time it costs hours if approached as either a vendor outage ("nothing to do, wait") or a bug ("our code must be broken"). The pattern's actual shape — silent migration with the old endpoint left alive — is unintuitive enough that it's worth having an explicit playbook for. The most expensive mistake is wasting time on the wrong hypothesis, and the second most expensive is reaching for heavy automation (Selenium, browser drivers) when a thirty-second question to the user gets you the same information.
