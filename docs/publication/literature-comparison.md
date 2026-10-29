# Nearest-work comparison and contribution limits

The initial broad novelty claim does not survive the nearest literature. This
table records the specific comparisons that shape the implemented study. It is
not a claim of exhaustive priority search. Seventeen verified records and their
access/version limitations are preserved in `bibliography.json` and the generated
manuscript bibliography. Abstract-only access is not evidence that a paper lacks
an overlapping contribution.

| Primary work | Passage inspected | What it already establishes | Consequence for this project |
|---|---|---|---|
| Choe and Ramdas, [Comparing Sequential Forecasters](https://arxiv.org/html/2110.00115v4), DOI 10.1287/opre.2021.0792 | Sections 3, 4.2-4.4; delay discussion checked through the companion paper | Bounded paired-score sequential inference, observable/oracle histories, strong and average nulls | Sequential comparison of adaptive forecasts is prior art; include a weak-null baseline and avoid equating rejection of uniform non-improvement with a durable economic edge |
| Arnold et al., [Sequential model confidence sets](https://arxiv.org/html/2404.18678v3), DOI 10.1093/jrsssb/qkag066 | Sections 2, 3.2-3.4, Propositions 3.2-3.3 | Time-uniform model comparisons with predictable bounded score differences, varying superiority notions | No first sequential model-selection claim; normalization can change the target |
| Choe and Ramdas, [Combining Evidence Across Filtrations](https://arxiv.org/html/2402.09698v3) | Section 5.2 and surrounding filtration examples | Evidence valid in a coarser history may need adjustment for full-information stopping; lagged forecast constructions already exist | Restrict the initial delay experiment to non-overlapping matured trials and state what information is actually observed |
| Waudby-Smith and Ramdas, [Estimating means of bounded random variables by betting](https://arxiv.org/html/2010.09686v6), DOI 10.1093/jrsssb/qkad009 | Sections 2.1-2.2 and bounded-betting setup | Confidence sequences, predictable bets, fixed mixtures and bounded-mean testing | The betting mechanism and calibration machinery are established methods |
| Jiao, Wang and Zhao, [Comparative e-backtests for general risk measures](https://arxiv.org/html/2511.05840v2) | Sections 1, 4.1-4.2, Theorem 3 and betting discussion | Financial comparative sequential e-backtests and predictable test processes | No first financial application claim; distinguish forecast scoring from paired execution-cost uncertainty |
| Xu and Ramdas, [Online multiple testing with e-values](https://proceedings.mlr.press/v238/xu24a.html) | Proceedings abstract and full-paper setup | Online FDR control under dependence given valid e-values | Applying an online procedure does not repair invalid cost proxies; this study uses explicit FWER spending instead |
| Ben-Tal and Nemirovski, [Robust Convex Optimization](https://www2.isye.gatech.edu/~nemirovs/MOR_RCO_1998.pdf), DOI 10.1287/moor.23.4.769 | Independent reviewer checked the robust-counterpart foundation | Worst-case linear objectives over joint uncertainty sets | The shared-cost support-function identity is elementary robust optimization |
| Li and Zhu, [Sequential Confidence Sets for Coverage-Constrained Conformal Model Selection](https://arxiv.org/html/2609.28522v1) | Sections 1-3, stated guarantee and delayed-feedback discussion | Sequential constrained comparison through simultaneous uncertainty sets, with explicit limits on post-selection interpretations | Cost-constrained sequential pipeline comparison is adjacent existing work; do not use broad uncertainty-set language as evidence of novelty |
| Wasserman, Ramdas and Balakrishnan, [Universal inference](https://doi.org/10.1073/pnas.1922664117) | Independent review of Section 7, running-MLE sequential likelihood ratio | Whole-history nuisance profiling, validity by comparison at the true parameter | Temporal cost coherence is an established composite-inference principle, not a new methodological contribution |
| Ramdas, Ruf, Larsson and Koolen, [Testing exchangeability](https://arxiv.org/html/2102.00630v4), DOI 10.1016/j.ijar.2021.06.017 | Sections 1.5-1.6 and 2.1, independent profiling review | Composite e-processes need not themselves be simultaneous nonnegative supermartingales; retaining one parameter across time matters | Do not claim the broader process distinction or temporal nuisance principle as new |
| Le and Ruthbah, [Trend-following Strategies for Crypto Investors](https://www.monash.edu/__data/assets/pdf_file/0011/3744821/Trend-following-Strategies-for-Crypto-Investors.pdf), August 2023 author manuscript | Sections 2, 4.1 and transaction-cost discussion, pp. 5-9 | Daily crypto trend comparisons with multiple lookbacks, risk overlays and assumed trading costs | Crypto trend following and sensitivity to fees are prior art; our new-period observations do not imply a first trading strategy |
| Bysik and Slepaczuk, [Machine Learning-Based Bitcoin Trading Under Transaction Costs](https://arxiv.org/html/2606.00060v1) | Sections 3.2, 4.1, 4.8, Appendix A.1 | Hourly BTC/USDT walk-forward trading, cost-aware turnover suppression, paired block resampling and gap audit | Cost-aware BTC evaluation is established; our gap reset policy differs from their declared forward-filled zero-volume candles, and ours does not claim their findings are replicated |
| Liu, [Anytime-Valid Tests of Factor Alphas](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7357270) | Indexed primary abstract; direct paper and PDF requests returned 403 | Advertises predictable residual betting for sequential factor-alpha testing | This precludes broad priority claims, but its uninspected full theorem assumptions cannot be endorsed or criticized here |
| Stephan, [Sequential Tradeability Testing for Alpha Signals](https://ssrn.com/abstract=6922558) | Indexed primary abstract; full PDF returned 403 | Bayesian sequential continuation/activation/rejection with an economic implementation hurdle | Sequential economically motivated alpha activation is prior art; distinguish that decision problem from our conditional error-control diagnosis |

Internal mathematical checks also considered broader conceptual predecessors. Additional direct checks on October 22:

| Primary work | Passage inspected | Consequence |
|---|---|---|
| Howard et al., [Time-uniform, nonparametric, nonasymptotic confidence sequences](https://arxiv.org/html/1810.08240v5) | Sections 2 and 4.1, Theorem 4; Section 6 running-intersection discussion | Predictable-centered variance adaptation and stationary-parameter interval intersections are established; an empty intersection is not a new discovery |
| Tian and Ramdas, [Online control of the familywise error rate](https://arxiv.org/pdf/1910.04900) | arXiv v2 Section 2 alpha-spending formula and Section 3 dependence/efficiency discussion | Our conservative spending is an existing baseline, not a new multiple-testing method; stronger recycling procedures require their own conditions |
| Kunsch, [The Jackknife and the Bootstrap for General Stationary Observations](https://doi.org/10.1214/aos/1176347265) | Publisher metadata and author publication list; publisher full/PDF endpoints returned an inaccessible iframe | Bibliographic attribution is verified; no claim to have checked a finite-sample coverage theorem. Market intervals remain explicitly approximate with a heuristic reporting threshold |

The surviving empirical question is narrower: how large is the power cost of
discarding defensible shared cost structure, and how badly do comparison,
coverage and information-timing shortcuts mislead in a reproducible financial
research workflow? The completed two-cohort experiment supports a modest established-method
diagnostic and negative application. It does not establish high methodological
novelty; external publication fit remains an editorial judgment.

Access limitations: the OUP sequential-model-confidence-set publisher page was
unavailable to the browser; arXiv v3 supplied the inspected text. Direct SSRN
access to nearest financial alpha-validation papers was retried at both paper
and PDF endpoints and remained blocked. No public author full-text alternative
was located in the targeted title searches. Abstract-level comparisons are
explicitly limited; they are not proof that the papers omit our proposed scope.
Different preprint timestamps and internal manuscript dates must be reconciled
in the final bibliography rather than silently conflated.

See the [release review](RELEASE-REVIEW-2026-10-28.md) for the current mathematical and numerical check scope. The separately frozen v2 protocol supplied sign-changing turnover contrasts
and matched evidence forms. Its completed outcomes are reported in the current manuscript; the follow-up preserves rather than replaces the original v1 experiment.

## Separately specified comparator follow-up

The v1 results exposed inactive Hoeffding competitors and fixed-sign turnover
contrasts. The [v2 protocol](followup-protocol-v2.md), written after those results,
adds the following existing-method comparisons. None is a new inference principle.

| Comparator | Primary passage checked | Implemented specialization and limits |
|---|---|---|
| aGRAPA bounded betting | Waudby-Smith and Ramdas, Appendix B.3, [version 6](https://arxiv.org/html/2010.09686v6) | Transform a [-1,1] utility to [0,1] and test mean 1/2; one-sided truncated prior empirical mean/second-moment stake. This is a declared one-sided specialization, with strong conditional-null validity and no claim to reproduce their whole confidence-set method |
| Predictably centered empirical-Bernstein evidence | Choe and Ramdas, Theorems 2-3 and Appendix A.1 Proposition 1, [version 4](https://arxiv.org/html/2110.00115v4) | Fixed lambda mixture with c=2B and a shared predictable center; valid latent domination for the prefix-weak null. Robustify each concave factor over its full utility interval, rather than inserting a lower proxy into a nonmonotone function |
| Whole-history EB cost profile | Composite profiling foundation above and [manuscript derivation](../../paper/sections/followup-methods.tex) | Componentwise endpoint minimization with five sufficient sums; matched local/coherent methods isolate discarded temporal structure. Constant-parameter profiling and scalar concavity are established tools |

The follow-up separates static versus contracting calibration intervals,
fixed-sign versus alternating turnover differences, and two noise scales. The
baseline outcome access is explicit. The completed comparative results and their independent audit are preserved.
They strengthen the mechanism diagnosis while revealing weak-effect and
base-method limits. They establish neither a first-method claim nor a market
execution-cost model. All results, including inactive or inferior modern
competitors, are retained.

## PI current-version and classical-context addendum,2026-10-23

The October 23 nearest-work update checked Choe and
Ramdas forecasters[v6](https://arxiv.org/abs/2110.00115v6), Arnold et al.
model confidence sets[v4](https://arxiv.org/abs/2404.18678v4), Choe/Ramdas
filtration[v5](https://arxiv.org/abs/2402.09698v5), and comparative e-backtests
[v2](https://arxiv.org/abs/2511.05840v2). Detailed earlier theorem derivations
retain their explicitly inspected version; historical protocol sources are
unchanged. Current-version checks support the restrained scope comparison,
not exhaustive priority or invariance of theorem numbering across versions.

Classical context added: White(2000), *A Reality Check for Data Snooping*,
Econometrica68(5):1097-1126, DOI10.1111/1468-0262.00152, primary publisher
abstract/metadata; Hansen, Lunde and Nason(2011), *The Model Confidence Set*,
Econometrica79(2):453-497, DOI10.3982/ECTA5771, publisher and author-institution
record. They provide fixed-sample time-series model-search context. The paper
does not implement those procedures or claim adjusted market superiority.
The bibliography export now distinguishes journal, conference and working-paper
entry types; long access-history notes remain in this audit register rather
than obscuring the printed reference list.
