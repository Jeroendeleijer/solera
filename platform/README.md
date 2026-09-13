# Solera platform — reference implementation

The data model, the per-tax-year rules and the Modelo 210 calculation engine
from Part 3 of the concept note. Python 3.11, **standard library only** — no
install, no dependencies, no network.

```bash
cd platform
python3 -m unittest discover -s tests -t .   # 28 tests
python3 demo.py                              # worked example
```

## What this is

A reference implementation: it proves the logic and is meant to be read and
checked. It is not the production system and it files nothing.

| Module | Holds |
|---|---|
| `solera/model.py` | Owner, Property, Ownership, RentalPeriod, Filing; the EU/EEA residency mapping |
| `solera/rules.py` | `TaxYearRules` per tax year — rates, percentages, whether expenses are deductible, form version |
| `solera/calendar.py` | Filing windows per tax year and income type |
| `solera/engine.py` | Imputed-income and rental-income calculations |

## The decisions worth reviewing

**Money is `Decimal`, never `float`.** Binary floats cannot represent tenths
exactly. Rounding is half-up to the cent, applied to the base and the tax and
nowhere in between.

**Rules are data, versioned by tax year.** A rate change is a new
`TaxYearRules` row plus a test, never an edit to the calculation. Years absent
from the table raise `UnknownTaxYear` rather than falling back to the most
recent rules — filing a year whose rules nobody confirmed is how surcharges
happen.

**Unknowns resolve to the higher figure.** An unrecognised country maps to
non-EU/EEA (24%). An unknown cadastral revision year applies 2% rather than
1.1%, and says so in the filing notes. Under-declaring on a guess creates a
liability; over-declaring on a guess creates a question.

**Leap years are prorated over 366 days.** The website calculator divides by a
hard-coded 365, which is fine for an estimate and wrong for a filing. 2024 and
2028 are leap years.

**The EU/EEA distinction is the expensive one.** Same property, same 50% share,
tax year 2026: an EU owner pays €156.75, a UK owner €198.00. On €8,000 of rent
with €3,000 of costs, €475.00 against €960.00 — because outside the EU/EEA the
rate is 24% *and* expenses are not deductible at all. `demo.py` prints both.

The first two engine tests use the same figures as the public calculator on the
website (€150,000 → €156.75 and €720.00), so the two can be cross-checked.

## Not here, and deliberately not stubbed

- **`.210` file generator** — blocked on the 2027 record design, which the
  concept note calls the critical path. A generator written against a guessed
  layout would be worse than none.
- **AEAT batch filer** — needs *colaborador social* registration and a
  qualified certificate. Neither belongs in a repository.
- **Authentication and persistence** — production concerns, and handling real
  NIE, IBAN and cadastral data needs the DPIA the risk table already lists.

## Before any of this is used in anger

Every regulatory detail must be verified against the AEAT Sede Electrónica.
The rules encoded here follow the concept note's appendix (Orden EHA/3316/2010;
Orden HAC/623/2026, BOE 23 June 2026; rates 19% EU/EEA and 24% otherwise) and
were current as drafted in September 2026. This is planning code, not tax advice.
