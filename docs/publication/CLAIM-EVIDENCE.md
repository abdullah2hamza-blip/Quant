# Claim and evidence map

Checked 2026-10-28. This is an AI-assisted internal traceability review, not
independent human peer review. The contribution is a controlled diagnostic of
established sequential methods and a retrospective Bitcoin application. It is
not a new general theorem, a priority claim for sequential finance testing, or
evidence of prospective trading profitability.

## Verification categories

- **R — reproduced this task:** the specified saved-output calculation, hash
  check or regression test was performed in the October 28 review. This does
  not mean that the complete study was rerun.
- **T — traceable prior run:** accepted outputs and completed archived-source
  replay records exist; the substantive experiment was not rerun this task.
- **U — unverified here:** no execution or external validation is asserted.

The [release review](RELEASE-REVIEW-2026-10-28.md) records fresh checks of 335
portfolio paths, all 466 synthetic null-family summaries, and all 30 bot
extension bootstrap intervals. The maximum accounting residual was 1.70e-16,
the maximum fee residual 3.00e-16, and the bootstrap discrepancy 8.33e-17.
The 124 focused scientific tests passed in 12.28 seconds. These checks support
implementation and reporting; they do not establish the assumptions on real
markets. In this traceability pass, all 39 generated display files, all three
registered-study source ZIPs, and all 64 bot-collection inventory entries
matched their recorded SHA-256 values.

## Accepted evidence and scientific source identity

Paths below are relative to the repository root. JSON registries/manifests
contain the complete file hashes, case identifiers, settings and attempt
receipts. NPZ files are saved world/account arrays, not vendor candle data.

| Evidence | Code, config and randomness | Saved outputs and scope | Category |
|---|---|---|---|
| Baseline synthetic study | `src/quant/publication.py`, `cost_evidence.py`; `configs/research/publication-study-v1.json`; seed 20261021, SHA-256-derived separate case/outcome and calibration streams | `results/publication-v1/simulation`: 24 JSON/NPZ cases, 4,000 independent worlds per case, 800 calendar steps, nine methods; `counterexamples.json` retains deterministic failure examples | T experiment; R null-summary and principal-number checks |
| Follow-up synthetic study | `src/quant/followup.py`, `cost_evidence.py`; `configs/research/followup-study-v2.json`; seed 20261023, separate spawned outcome/calibration streams aligned across cases | `results/publication-v2/study`: 25 JSON/NPZ cases, 4,000 worlds, 800 labels, ten streams and ten comparators; 250 method rows and 150 paired contrasts | T experiment; R null-summary/truth and principal-number checks |
| Registered market application | `src/quant/market_study.py`, `engine.py`, `stats.py`; `configs/research/market-study-v1.json`, `btc-trend.toml`; bootstrap seed 20261022 plus the first eight hex digits of SHA-256(case ID) | `results/publication-v1/market/<case>`: `report.json`, `paths.npz`, `selections.json`, `base-cost-trades.json`; six cases, nine books, five assumed costs, 270 paths | T backtest; R direct price/account checks |
| Post-protocol bot extension | `scripts/bot_extension_study.py`, archived engine/stats and delivered bot sources; `configs/research/bot-extension-study-v1.json`; bootstrap seed 20261023 | `results/bot-extension-v1`: 40 matched paths, ten contrasts, 30 intervals; `attempts/b477dff8-2d0a-485b-821e-3a9e29431283/{report.json,paths.npz,trades.json}` | T experiment; R accounting and all intervals |
| Preserved delivered bot | `results/bot-extension-v1/delivered/bot`, including `legacy/original-v2.zip`; installation/source inventory in collection | Delivered `validation/legacy-{report.json,paths.npz,trades.json}` preserves 25 paths. Its .15 band/150-bar warm-up differs from the matched experiment's .10/334 | T delivered evidence; R account/endpoint checks |

The three immutable registry anchors are:

| Registry | SHA-256 |
|---|---|
| [Baseline and market](../../results/publication-v1/registry.json) | `dd8f573a1c8af69f14ea777a5d6516cdae7f6110fb39c2040a565fb91c5c0c8a` |
| [Follow-up](../../results/publication-v2/registry.json) | `e869065cd00ffedbd9e5d10684ff6238d950713bbecec140a27723e222490c5a` |
| [Bot extension](../../results/bot-extension-v1/registry.json) | `36e058d341ad1ba31192b86dec45e43fa7884e0c0ecab09172ae3eef8cf6c828` |

Use the archived scientific sources for exact replay, rather than treating the
current release commit as the original experiment's commit:

| Scientific capsule | SHA-256 of source ZIP | Specification SHA-256 |
|---|---|---|
| `results/publication-v1/source-snapshots/publication-baseline-freeze-v1.sources.zip` | `409d87a5724a4da9168323f58d0bda689ab78c5c8c931bb8c212df4d8baed013` | `ee88dff71cc989114b79a616ab1a3e95abc7be2ded867093060531bd7814d625` |
| `results/publication-v1/source-snapshots/market-freeze-v1.sources.zip` | `e41275dffcc7f5617758adc12cb80edd76f5cda6b36c7ac460ee963a92a78271` | `62ecbff1622c3e399c9d0d4bd0e5d660e9ffa4f145572029e6d0685cdd917e39` |
| `results/publication-v2/source-snapshots/followup-freeze-v2.sources.zip` | `d6a37ffc045b07461dacc30ff454de072a5e7600aa69a7b9f7f58b6fa1efa13e` | `e683706368446fe27d019c6b0984a35ded9938f80e689699937dc70b81d24211` |
| `results/bot-extension-v1/sources.zip` | `39deba48da8e66818c05334584075225a58d015b7099c977eaecf27fb5620691` | `218f5e72a2ff94d8f666137830bd9dbc3f0e826b3507a33e02e7e1f06d1225ac` |

Each capsule's adjacent freeze JSON records the executed inventory and runtime.
The current market source differs from its scientific capsule by a descriptive
original-bot chronology clarification; the numerical implementation is unchanged.
The current numerical module hashes match those inspected in the October 28
scientific review. Documentation, disclosures, packaging and bibliography may
change for release. The release's commit/tag and file manifest identify those
current bytes separately; this document does not invent a final commit or tag.

## Input provenance

The market freeze pins all four normalized CSVs, their manifests and independent
audit records. Vendor candles are excluded from the public bundle. Restoration
must recover the exact hashes; newly revised vendor data are not an interchangeable
input. Manifests contain every original request URL and source-response/archive
hash, not just the normalized CSV hash.

| Input, through 2026-10-20 | Normalized CSV SHA-256 | Manifest SHA-256 |
|---|---|---|
| Binance BTCUSDT spot 1h | `a040641dc5e6b52a92abaa19a2fb91b68ff0b09114827b02e508d0747e002356` | `4a46bb879e5ff006363d75f16e96b0bcc23cabb7e55ac564ad643e57e323dbce` |
| Binance BTCUSDT spot 4h | `5eea975ec9aa32b88579a99d05ac9e722fd3fe9aa7024ae78350618a8333c78d` | `ebc379f88f04f08bd50e865fc191823a18e82fb5658c807988f01a1d8c438dc5` |
| Binance BTCUSDT spot 1d, also used by bot extension | `56ab80047fbac8705dd99677dd74e3a946af33de79072b9ef49e042e249dda25` | `a78fdee98158fa0b271eb3d749fec217e4fb84caf415d89d52dc291fd244498f` |
| Bitstamp BTCUSD spot 4h | `d415dbdaf84731c4b9f7a7aab5cdc314fb830368c3d2f833ffbb34069505893a` | `c2e09f6175693a7dd2f29d076701a40bae8e229118f2b9837d3fe3473559d66f` |

The root filenames are `data/btc-{1h,4h,1d}-through-2026-10-20` and
`data/btc-bitstamp-4h-through-2026-10-20`, with `.csv`/`.manifest.json`
extensions. Audits are `docs/publication/data-audit{,-1h,-1d,-bitstamp-4h}-v1.json`;
the unsuffixed audit is the Binance 4h audit. Binance source ZIPs were checked
against published checksums. Bitstamp has locally hashed response bytes, without
a supplier checksum or point-in-time archive guarantee; its candle close times
are inferred from the interval. Neither venue's historical candles authenticate
fills. The venues share the same underlying asset and have different quote units.
See [the input/replay instructions](REPRODUCE.md) and [third-party notices](../../THIRD_PARTY.md).

## Claim, figure and table map

TeX labels are used because printed numbering may change. Generated paths are
under `paper/generated/`. Each generator's `traceability.json` binds its input
registry, generator, numeric macros and every output hash. Case/method/policy/cost
keys in CSV rows identify the corresponding source JSON fields without rounding.

| Manuscript claim or label | Saved evidence and derived output | Interpretation/category |
|---|---|---|
| Proposition `prop:composition`; Table `tab:methodscope`; coherent/EB formulas | `paper/sections/{methods,followup-methods}.tex`; `src/quant/cost_evidence.py`; fixed-lambda mixture, known latent support, calibration and oracle-filtration assumptions; frozen protocols | Analytic/code review R; established-method derivation, not an empirical theorem test |
| Shared-cost width advantage; failure counterexamples | `simulation/counterexamples.json`; `cost_evidence.py`; appendix `app:counterexamples` | Deterministic examples T; the support-function identity is elementary robust optimization |
| Figure `fig:power` | `simulation-power.{png,svg}`, `simulation-all-methods.csv`; v1 `effect02_*`/`effect05_*` overlap cases, `methods.<method>.first_stream_power` | Equal-turnover joint/separate 92.425%/0.025%; R checked numbers, T worlds |
| Figure `fig:validity` | `simulation-validity.{png,svg}`; same CSV and raw `rejected`/`null_at_birth` masks; includes explicitly invalid symmetric-upper and drifting-cost cases | Valid-joint maximum 0.675%; upper-both 12.95%, drift/plugin 43.55%. R summaries; no universal empirical FWER proof |
| Figure `fig:utility` | `simulation-delay-utility.{png,svg}`; JSON restricted detection time and materiality-adjusted paper utility, raw first-crossing/utility arrays | T; fixed calendar horizon means delay also reduces labels/calibration; births change exposure. No isolated delay causal effect |
| All baseline synthetic rows | `simulation-full-table.tex`, `simulation-all-methods.csv` (216 rows), `simulation-paired-comparisons.csv` (24 rows) | T/R summaries; `joint_hoeffding`, `separate_hoeffding`, `fixed_horizon_hoeffding`, `naive_peek_hoeffding` have zero rejections throughout, limiting comparative conclusions |
| Figures `fig:followup-power`, `fig:followup-paired`; Table `tab:followup-paired` | `followup/{power,paired-power}.{png,svg}`, `primary-paired-table.tex`, `method-results.csv`, `paired-results.csv`; eight effect-.05 factorial cells, primary within-world pairs | Coherent/local EB 33.5%/0% in high-volatility static alternating case; contracting 35.325%/4.6%. T/R principal numbers; no uniform ranking |
| All follow-up results and diagnostics | `followup/{case-key.tex,full-table.tex,method-results.csv,paired-results.csv,calibration-compute.csv}`; all 25 reports/NPZs | 250 method/150 paired/25 calibration rows; maximum supported null-family rate 1.15%; weak-effect .02 coherent power at most 1.825%. T/R summaries |
| Prefix-weak diagnostic | v2 `prefix_weak_diagnostic` case as identified by `followup/case-key.tex`; raw truth/hits; `followup-results.tex` | First-stream rejections zero; family counts one oracle-linear and two oracle-aGRAPA worlds. Adaptive-bet rows are unsupported for this null. T/R |
| Table `tab:market`; Figure `fig:marketpaths` | `market-primary-table.tex`, `market-primary-paths.{png,svg}`, `market-all-policies-costs.csv`; `binance_primary_4h`, base cost 25 bps | Adaptive/fixed return 2.6067%; ensemble -2.2112%; no scored-window switches, coincident adaptive/fixed paths. R saved-account checks; T history |
| Table `tab:pairedmarket`; Figure `fig:pairedmarket` | `market-comparisons-table.tex`, `market-paired-intervals.{png,svg}`, `market-paired-costs.csv`; all six cases, base cost 25 bps | Hourly annual mean-log difference -9.6527%, CI [-32.1750%,2.6101%]; daily -6.6806%, CI [-22.4194%,5.0424%]. R checked; approximate unadjusted intervals |
| Table `tab:blockedges` | `market-diagnostics/{edge-table.tex,diagnostics.csv,diagnostics.json}`; exact analytic expectation over the saved MBB starts | Post-outcome edge-weighting diagnostic, not a replacement interval or coverage calibration. R traceability; saved diagnostic T |
| Market cost/control supplement | `market-cost-table.tex`, `market-control-table.tex`, `market-paired-costs.csv` (30 rows), `market-control-comparisons.csv`; frozen selections, costs 0/10/25/50/100 bps | T; assumed-cost sensitivity, not calibrated slippage or optimized fee selection |
| Delivered original-bot 11.8784% return | `results/bot-extension-v1/delivered/bot/validation/legacy-report.json` and saved arrays/trades; original source archive and installation receipts | R endpoint/account check; preserved delivered variant, distinct from later matched settings; the unshipped fee-only 13.6577% variant is excluded |
| Tables `tab:botextensionmetrics`, `tab:botextensionpaired` | `bot-extension/{table.tex,metrics.csv,paired.csv,numbers.tex}`; all 40 matched paths, all ten cost/target contrasts and 30 block-length intervals | SMA/EMA at targets .20/.40, native 1d, volatility window 30, band .10, common 334-bar validity. R all accounts/intervals; post-outcome exploratory T experiment |

The central bot contrasts are annual mean-log SMA-minus-EMA differences:
5.4077% with 30-day CI [-6.3797%,15.2184%] at target .20, and 4.4566%
[-12.6727%,17.7382%] at .40. Both include zero. Target matching does not equalize
realized risk or identify causal signal alpha. All costs and controls remain
reported; there is no best-setting selection.

The baseline display generator is `scripts/build_publication_artifacts.py`;
follow-up uses `scripts/build_followup_artifacts.py`; edge diagnostics use
`scripts/build_market_diagnostics.py`; the extension uses
`scripts/bot_extension_study.py build`. Their output inventories contain,
respectively, 21, 11, 3 and 4 files. Numeric macros in `numbers.tex` files feed
the prose; the follow-up trace explicitly records every macro's source field.

## Required boundaries on interpretation

1. The null concerns **materiality-adjusted** bounded paired mean utility and
   every prefix from the declared birth. It is not a final-horizon-only or
   unconditional zero-alpha null. Conditional means use the stated full/oracle
   filtration. Hypothesis choices, fixed grids/weights and bets must obey their
   respective predictability requirements; immature labels are unavailable.
2. Fixed linear/Hoeffding/EB constructions support the stated prefix-weak null;
   adaptive aGRAPA is asserted only under the strong per-trial conditional null.
   Whole-history coherent profiling uses a shared fixed nuisance parameter and
   nested simultaneous confidence sets. It is not adaptive strategy refitting.
3. Calibration assumes bounded observations with the same conditional mean
   cost coefficient. Coverage failure is added by event inclusion/union bound,
   not by pretending conditioning on coverage preserves a supermartingale.
   The .04 testing plus .01 envelope allocation gives .05 **per comparator's
   family within a case**; it does not cover selecting a method/case after
   comparing results. The calibration spending is deliberately conservative.
4. Simulations are known-truth model diagnostics, not fitted Bitcoin execution
   models. Wilson intervals use independent worlds; paired normal intervals are
   approximate and unadjusted. A zero observation retains uncertainty; a
   degenerate normal interval is unavailable rather than proof of no effect.
5. The 243-day market comparisons contain only 8.1 nominal 30-day blocks.
   Moving-block percentile intervals have unvalidated finite-sample coverage,
   dependence/stationarity requirements and measurable edge weighting. They
   are not time-uniform, multiplicity-adjusted, or calibrated economic exclusion
   tests. Four-hour [0,0] resampling reflects identical saved paths, not certain
   future equivalence; roundoff signs do not identify an economic break-even cost.
6. The matched bot extension follows inspected outcomes. It is explicitly
   exploratory, uses the same history and unadjusted intervals, and adds no
   independent market sample. Registered protocols and six market cases remain
   unchanged. Costs, daily-close drawdown and paper next-open execution do not
   establish latency, capacity, intraday risk or live-fill performance.

## Closest primary literature and citation accuracy

The current [bibliography register](bibliography.json),
[`references.tex`](../../paper/references.tex) and
[`references.bib`](../../paper/references.bib) distinguish issue years from
online dates and version-pin preprints. The essential release check found no
consequential mismatch. Primary publisher/author records checked in this task
support the following limited uses; this is not an exhaustive priority search.

| Citation keys | Official source and what it supports | Checked limit |
|---|---|---|
| `choe2024` | [Choe–Ramdas, Comparing Sequential Forecasters](https://pubsonline.informs.org/doi/abs/10.1287/opre.2021.0792); [author version v6](https://arxiv.org/abs/2110.00115v6) | Operations Research 72(4),1368–1387 (2024), online 2023; weak/average conditional comparison and EB antecedent. Earlier inspected-version theorem numbering is identified separately |
| `waudby2024` | [Waudby-Smith–Ramdas, Estimating means of bounded random variables by betting](https://academic.oup.com/jrsssb/article/86/1/1/7043257); [v6 including aGRAPA appendix](https://arxiv.org/html/2010.09686v6) | JRSSB 86(1),1–27 (2024), DOI qkad009; predictable bounded betting precedes this application |
| `howard2021` | [Howard et al., confidence sequences](https://arxiv.org/abs/1810.08240) | Official journal reference Annals of Statistics 49(2),1055–1080 (2021), DOI 20-AOS1991; no new CS method claimed here |
| `arnold2026`, `hansen2011` | [Sequential model confidence sets](https://doi.org/10.1093/jrsssb/qkag066); [The Model Confidence Set](https://doi.org/10.3982/ECTA5771) | Arnold et al. advance online 13 May 2026; Hansen–Lunde–Nason Econometrica 79(2),453–497 (2011). Sequential model comparison and selection uncertainty are established |
| `wasserman2020`, `ramdas2022` | [Universal inference](https://arxiv.org/abs/1912.11436); [Testing exchangeability](https://arxiv.org/abs/2102.00630) | Composite/nuisance inference and e-process domination have predecessors; a nuisance infimum need not itself be a common nonnegative supermartingale |
| `choefiltration2026` | [Combining Evidence Across Filtrations v5](https://arxiv.org/abs/2402.09698v5) | Version dated 15 March 2026; coarse-filtration validity does not automatically transfer to richer information. The paper states its stronger filtration assumption |
| `xu2024`, `tian2021` | [Online multiple testing with e-values](https://proceedings.mlr.press/v238/xu24a.html); [Online control of the familywise error rate](https://arxiv.org/abs/1910.04900) | PMLR 238,3997–4005 (2024); Tian–Ramdas 2021 journal DOI in register. FDR background is distinguished from this implementation's alpha-spending FWER |
| `bental1998` | [Ben-Tal–Nemirovski author PDF](https://www2.isye.gatech.edu/~nemirovs/MOR_RCO_1998.pdf) | Robust Convex Optimization, MOR 23(4),769–805 (1998); robust shared-cost geometry is not a new general optimization principle |
| `jiao2026`, `li2026` | [Comparative e-backtests v2](https://arxiv.org/abs/2511.05840v2); [Li–Zhu v1](https://arxiv.org/abs/2609.28522v1) | Exact titles/authors/version dates checked. Li–Zhu title is Sequential Confidence Sets for Coverage-Constrained Conformal Model Selection; CC-SMCS is its method name |
| `le2023`, `bysik2026` | [Le–Ruthbah author working paper](https://www.monash.edu/__data/assets/pdf_file/0011/3744821/Trend-following-Strategies-for-Crypto-Investors.pdf); [Bysik–Ślepaczuk v1](https://arxiv.org/abs/2606.00060v1) | Crypto trend/cost and walk-forward work precede this application. Le–Ruthbah cover says August 2023; no journal status invented |
| `white2000`, `kunsch1989` | [White publisher record](https://onlinelibrary.wiley.com/doi/10.1111/1468-0262.00152); [Künsch publisher DOI](https://doi.org/10.1214/aos/1176347265) | White issue year 2000, not the publisher's later electronic posting date. Künsch metadata/DOI traceable; full publisher text inaccessible in this pass, and no finite-sample MBB coverage theorem attributed to it |
| `liu2026`, `stephan2026` | [Anytime-Valid Tests of Factor Alphas](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7357270); [Sequential Tradeability Testing for Alpha Signals](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6922558) | Titles/authors/posting metadata and indexed primary abstracts checked; full PDFs blocked. Comparisons remain abstract-only, with no theorem-level critique or priority conclusion |

## Exact reproduction routes and execution status

Run from the repository root. See [REPRODUCE.md](REPRODUCE.md) for compiler/cache
setup, dependency versions and input rights. The frozen numerical environment
uses Python 3.13.7 and NumPy 2.5.4; paper builds use Tectonic 0.17.0.

```sh
uv sync --locked --python 3.13.7
uv run --locked pytest -q

# Integrity of accepted results, source capsules and receipts; no vendor CSVs.
uv run --locked python -m scripts.reproduce_complete_study --verify-only --output runs/verify-local

# Rebuild tables/figures/paper from saved results; no vendor CSVs or new study.
uv run --locked python -m scripts.reproduce_complete_study --results-only --output runs/paper-local --tectonic /path/to/tectonic

# Recover all four exact vendor inputs from a supplied cache.
uv run --locked python -m scripts.restore_market_inputs --cache-root /path/to/data/raw --receipt runs/restoration.json

# Audit restored inputs and rebuild the paper from accepted results.
uv run --locked python -m scripts.reproduce_complete_study --output runs/audited-paper --tectonic /path/to/tectonic

# Fresh archived-source replay, then exact comparisons and paper rebuilding.
uv run --locked python -m scripts.reproduce_complete_study --full --output runs/full-replay --tectonic /path/to/tectonic
```

Use a new output directory for each attempt; failures and terminal receipts are
preserved. Restoration may use the documented `--download` option; vendor
availability is external. The three mode flags are exclusive. Optional explicit
reuse of a previously completed baseline replay is recorded as reuse, not fresh
computation. `--full` replays all 24+25 synthetic cases, six market cases and the
bot extension from their scientific capsules. It compares arrays/dtypes and
scientific JSON; operational timestamps, run identifiers, paths and runtimes
have explicitly enumerated comparison exclusions.

For the focused tests actually executed in the October 28 scientific review:

```sh
.venv/Scripts/python.exe -m pytest tests/test_cost_evidence.py tests/test_publication.py tests/test_followup.py tests/test_engine.py tests/test_market_study.py tests/test_stats.py tests/test_bot_extension.py -q --basetemp=runs/pytest-release-science-2026-10-28 --tb=short
```

Prior completed archived-source replays are **T**, not fresh October 28 study
executions: baseline report SHA-256
`1099a8409b1258ff9d626984f39b38ad5871e42cf9af115983bf1315028a400b`
and combined report
`c2d893e61d0e061521b70b4bf11a4c3dd389f169ce40c37fad12017ced22f834`
record exact comparisons of 2,859 arrays (192 baseline synthetic, 2,442 market,
225 follow-up). The combined workflow explicitly reused the completed baseline
and freshly replayed the follow-up. The separately completed extracted-source
bot replay compared 251 arrays and scientific JSON/trades exactly; its execution
record SHA-256 is
`a6953072ca6fc405da469e3078bbc9ab9707da071ceed664f97a28bb919e1441`.
These are historical local execution records, not new observations or
independently seeded scientific replications. Their hashes identify the records
inspected here; the public bundle need not contain every historical local
execution directory. The accepted outputs, source capsules and replay commands
are the independently executable evidence supplied with the release.

Hosted Kaggle execution, public accessibility, remote Actions, upload/tag status
and venue acceptance are **U in this scientific review** until their separate
release receipts establish them. The Kaggle notebook's offline saved-results
review is not a full frozen numerical replay. Local PDF QA and packaging gates
must bind the final delivered bytes; historical PDF/package checks do not
automatically certify a later edited manuscript or release archive.
