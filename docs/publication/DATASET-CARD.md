# Research companion data card

This is a preserved-results research companion, not a live market feed or a
trained model. It accompanies the technical report by Abdullah Hamza,
Independent Researcher, with the title and citation in `CITATION.cff`.

| Component | Contents and interpretation |
| --- | --- |
| `results/publication-v1/simulation` | 24 synthetic cases, 4,000 worlds per case, 800 steps, 10 hypotheses; seed 20261021. JSON summaries and compressed NPZ outcome arrays. |
| `results/publication-v2/study` | 25 separately specified synthetic cases with the same world/step/hypothesis counts; seed 20261023. Cases share innovations and are not independent replications of one another. |
| `results/publication-v1/market` | Six retrospective Bitcoin cases, nine books and five assumed cost levels: 270 paths. Saved account/NAV arrays and metrics. |
| `results/bot-extension-v1` | Dated exploratory daily SMA/EMA extension: 40 matched paths, 10 contrasts, 30 bootstrap intervals; separately preserved corrected delivered-bot evidence. |
| `paper/generated` | Traceable CSV/TeX tables, numerical macros and plots derived from those collections. Row counts and detailed fields are documented in `CLAIM-EVIDENCE.md` and their traceability JSON. |
| `data/*.manifest.json` | Four exact upstream snapshot identities and restoration instructions. Raw and normalized exchange candles are excluded. |

The synthetic utilities and known-null indicators are simulations. Market
results are retrospective strategy calculations using assumed per-side costs
of 0, 10, 25, 50, 100 basis points; they are not broker fills. Metrics are defined in
the manuscript and generating code, not inferred from a filename. Returns in
machine-readable results are fractions unless a column explicitly says
otherwise; manuscript percentages multiply those fractions by 100. The Kaggle
viewer reports 216 baseline summaries, 250 follow-up summaries, 270 registered
market rows and 40 matched-extension rows, not that many independent experiments.

The market inputs cover September 2017 through October 20, 2026 and originate
from Binance Vision (native 1h/4h/1d BTC/USDT) and Bitstamp's public API (4h
BTC/USD). See the four manifests, source-freeze records, `REPRODUCE.md` and
`THIRD_PARTY.md` for exact hashes, URLs, timestamp normalization, missingness,
quarantines and rights. Current snapshots do not establish historical feed
availability. Vendor revisions can prevent exact-input restoration; saved-result
inspection remains possible without those inputs.

Original software is MIT; original prose and synthetic displays are CC BY 4.0.
Binance-derived outputs/displays retain Binance Vision attribution,
CC BY-NC-SA 4.0 and provider terms; Bitstamp attribution/terms also remain.
The mixed Kaggle bundle uses `other` with these component notices, not a
blanket unrestricted grant. No human-subject, private account or model-weight
dataset is present.

Use this companion for accounting/inference diagnostics and reproducibility.
Its conditional synthetic guarantees do not calibrate real trading costs.
The short retrospective market window and exploratory bot comparisons do not
establish causal alpha, future profitability or deployment capacity. The visible
AI-assistance statement in the README/manuscript also applies to preparation,
analysis, figures and documentation of this companion; automated reviews are
not independent human peer review.
