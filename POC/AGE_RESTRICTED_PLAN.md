# Plan: Scraping Age-Restricted (TEREA / Tobacco) Products

_Created 2026-07-09_

## Root cause
- TEREA heat-sticks (and some IQOS devices) are **tobacco/nicotine products → age-gated**.
- Tokopedia decides visibility from the **account's age/verification**, server-side. Logged-out
  or non-age-verified sessions get these products **filtered out of search results**.
- Our scraper currently runs **anonymously** (Playwright anti-bot cookie, no login) and sends
  `show_adult=false` in the search params. That is exactly why TEREA sticks came back scarce —
  they were never served to us, not missing from the market.

## Objective
- Retrieve the full age-restricted catalog by scraping with an **authenticated, age-verified
  Tokopedia session** (and `show_adult=true`).

## Prerequisites / decisions needed from you
1. **A dedicated Tokopedia account** for scraping — strongly recommend a **burner account, not a
   personal one**, that is:
   - **age-verified as adult** (18+/21+); complete any KTP / date-of-birth verification Tokopedia
     requires before tobacco listings become visible;
   - **confirmed** to actually show TEREA products in a normal browser before we automate.
2. **Risk acceptance.** Authenticated automated access is more clearly against Tokopedia's ToS
   than anonymous browsing and carries a real **account-suspension risk**. Mitigate with a
   disposable account, low volume, and human-like pacing. Needs your/your client's sign-off.

## Approach: manual login + persistent profile (recommended)
Reuse the existing Playwright persistent profile (`data/pw_profile`), but logged in:
- **One-time interactive login** in a visible browser (handles password + OTP/2FA + age
  verification manually — these are hard/unsafe to fully automate).
- The persistent profile stores the **logged-in session**; the harvester then captures the
  **authenticated cookie** (same mechanism as today) and reuses it until it expires.
- **No credentials in code** — login is always manual/interactive. Profile dir stays gitignored.

## Implementation phases
1. **Phase 0 — capture a logged-in request (do this first).**
   Log into Tokopedia in Chrome with the age-verified account, search `terea`, then in
   DevTools → Network → `SearchProductV5Query` capture:
   - whether `show_adult` is now `true` in the params;
   - any **auth signals** the request carries that the anonymous one didn't — e.g.
     `Authorization: Bearer …`, a non-empty `tkpd-userid`, `Account-ID`, or extra cookies;
   - confirm TEREA sticks actually appear in the response.
   This tells us exactly what to replicate (cookie alone may be enough, or a header/token too).

2. **Phase 1 — authenticated harvester.**
   Add a `--login` mode to `src/cookie_harvester.py`: launch the headful persistent browser,
   prompt "log in + verify age, then press Enter", detect the logged-in state (e.g. `tkpd-userid`
   set / a `me` query succeeds), then save the profile and cache the authenticated cookie
   (+ any auth header found in Phase 0). Warn loudly if still logged out.

3. **Phase 2 — `show_adult` + auth headers.**
   Add a `show_adult` param (config/flag, default `false`; `true` for authenticated runs) to
   `search.build_params`, and add any required auth header to `client.build_headers`.

4. **Phase 3 — validate.**
   Re-scrape `terea` logged-in vs the current anonymous baseline; confirm TEREA sticks now
   appear and count how many more products we recover.

5. **Phase 4 — session lifecycle.**
   Detect auth expiry (age-gated results disappear again) → prompt re-login. Keep the anonymous
   mode as the default for non-restricted products; use the logged-in mode only when needed.

## Risks & mitigations
- **Account ban** → burner account; low request rate + jitter; off-peak; small page caps.
- **ToS / legal** → internal competitive analysis only; keep volume respectful; get sign-off.
- **Credential safety** → manual login only; never store passwords; profile dir gitignored.
- **Detection** → keep persistent-profile + stealth + `curl_cffi`; authenticated requests must
  mimic the logged-in browser exactly (same UA + cookie + headers as captured in Phase 0).

## Open questions
- Can you provide/create a dedicated **age-verified** account for this?
- Is authenticated scraping acceptable given the higher account/ToS risk?
- Which products are age-gated — only TEREA sticks, or also devices? (Sets the scope of what
  the login unlocks.)
</content>
