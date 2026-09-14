# Solera

Tax, legal and insurance for foreign owners of Spanish property. The Modelo 210 is the hook: €29.99 per filing, per co-owner. Solera Anual is €249 per property per year.

Every non-resident owner must file the Modelo 210 every year, which makes it the one forced annual contact with the Spanish state — so it is priced as an acquisition product, not a revenue line, and every filing receipt carries a check-up report. Three service lines (tax, legal, insurance) each split between what recurs inside **Solera Anual** and what is done on demand at published fixed fees.

Site content follows `solera_concept_and_tech_brief_1.pdf` (September 2026). Note the 2027 filing change under Orden HAC/623/2026: rental income is filed annually, 1–20 April, not quarterly.

## Contents

- `platform/` — reference implementation of the Modelo 210 calculation engine, the per-tax-year rules and the data model from Part 3 of the brief. Python 3.11, standard library only: `cd platform && python3 -m unittest discover -s tests -t .` It files nothing; see `platform/README.md` for what is deliberately absent and why.

- `brand/solera-brand-v1.0.html` — brand identity v1.0 (September 2026): name, positioning, offer, mark & lockup, colour, typography, voice, applications. Self-contained bundle exported from Claude Design; open in a browser.

- `site/` — website mockups (static HTML, open in a browser):
  - `index.html` — homepage with the annual-cost ledger
  - `solera-verhuur.html` — owner rental listing page with live preview
  - `solera-diensten.html` — full list of tax, administration and legal services
  - `solera-modelo210.html` — free Modelo 210 calculator (no account) and how filing works; the acquisition page for the hook. English twin at `en/modelo210.html`
  - `privacy.html` / `en/privacy.html` — draft privacy statement; controller Solera Spain S.L. Settled alongside the DPIA before launch.
  - `favicon.svg` — the sanctioned two-tier cut of the mark at 16px
  - `solera-account.html` — client-file prototype: sign-up, filing history, properties, annual check-up. English twin at `en/account.html`. **Front-end only** — state lives in the visitor's own browser under `solera.demo.v1`; there is no server, no auth and no password. It is a demonstration of the portal described in Part 3 of the brief, not that portal.
  - `img/` — SVG illustrations of villas, town houses and fincas in the brand palette; drawn for the marketplace page, currently unused
  - `en/` — English version of the three pages (`index.html`, `rental.html`, `services.html`); the NL · EN control in the header swaps between counterpart pages, not to the homepage

The English version is written for English-speaking owners rather than translated line by line. Where a Spanish rule depends on the owner's residence it states both cases — rental income and capital gains are taxed at 19% with costs deductible for EU/EEA residents, and at 24% on gross with no deduction for everyone else — instead of asserting one. Home-country specifics from the Dutch copy (box 3, the NL–ES treaty, the consulate in The Hague, a choice of Dutch succession law) are generalised to "your own adviser" and "the law of your nationality".

## Template variables

Visible `{{…}}` placeholders are intentional and awaiting real values: `{{cif}}`, `{{asesoria}}`, `{{colegiado}}`, `{{corredor}}`, `{{dgs_number}}`, `{{privacy_email}}`, and `{{checkup_1..3}}` on the 210 confirmation block.

## Brand at a glance

- **Logo:** the Criadera mark — three tiers, base widest, terracotta on the top tier only, bars flush left. Wordmark Petrona Regular at −2.5%. Per *Solera Logo Guidelines v1.0*; the earlier arch mark was one of the five rejected directions.
- **Type:** Petrona (headlines, name) · Karla (body, UI)
- **Colour:** lime plaster ground, clay, olive ink, terracotta as punctuation (#B3623C; #98502C as type), grove for "done"
- **Voice:** name the cost · local, not exotic · calm, never urgent
- **Language:** Dutch first, English second, Spanish for official terms (always glossed)
