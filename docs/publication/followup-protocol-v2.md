# Follow-up v2: variance adaptation and temporal cost coherence

## Timing and scope

Written October 22, 2026 after inspection of all baseline v1 synthetic and
retrospective market results. Those results and reviews remain unchanged. The
v1 Hoeffding comparators never rejected, its turnover difference kept one sign,
and its large equal-turnover gain arose by construction from shared-cost
cancellation. These observations motivate this separately specified follow-up.
This is a local specification, not external preregistration or a fresh market
holdout. No additional trading-rule or historical-market optimization is planned.

The contribution being investigated is a diagnostic finding about where power
is lost: per-trial cost pessimism, discarding a common coefficient across time,
or choice of the base sequential method. The robust-counterpart, nuisance-profile
and betting principles are established. No new general theorem is claimed.

## Design fixed before substantive v2 outcomes

The 24-case factorial crosses materiality-adjusted first-stream effect
`{0, .02, .05}`, turnover contrast `{positive, alternating}`, cost information
`{static_initial, contracting}`, and volatility scale `{1, .4}`. An additional
prefix-weak diagnostic has all streams' conditional means -.06 for the first
400 labels and +.06 for the remaining 400, positive turnover, contracting costs,
and volatility scale 1. Its cumulative conditional mean is nonpositive at every
prefix; it is not a strong conditional null in the second half.

Each substantive case uses 4,000 independent worlds, 800 non-overlapping matured
labels and ten simultaneous streams. Family alpha is .05, with .01 for one
global simultaneous cost envelope and .04/10 per stream.
Each comparator's ten-stream family has this bound separately. The experiment
does not offer 5% FWER for the union of discoveries across all ten methods, nor
for selecting the most favorable method after comparison. Only stream zero has
the stated positive effect; the other nine are null. Null cases have ten null
streams. The run ends after every specified case, regardless of outcomes.
All cases use seed 20261023 with separate outcome and calibration RNG streams.
They share underlying innovations by world index to support paired factorial
comparisons. Worlds, rather than streams or cases, are the Monte Carlo units.
Do not pool cases as independent replications. No optional addition of cases is
permitted without a disclosed amendment and separate run.

Before each outcome, candidate/reference turnover is (.8,.4). In alternating
cases this pair swaps every 20 labels, starting with positive difference. Let
`d=qA-qR`, fixed true coefficient theta=.08, materiality m=.01, support [0,.2].
With independent fair signs S_t and I_jt, and past common sign S_(t-1), define

```
sigma_t = volatility_scale * (.2 + .1*(1+sin(2*pi*t/80))
                              + .15*1{S_(t-1)>0})
D_jt = effect_jt + sigma_t*(.6*S_t + .4*I_jt)
A_jt = D_jt + d_t*theta
G_jt = A_jt + m
```

All true and support-counterfactual utilities, including separate proxies, are
bounded in [-1,1] by the deterministic bound
.65+.06+.4*.08+.8*.2=.902<1; enforce this rather than clip. The recorded sample maximum
is only an implementation diagnostic, not the justification for that bound.
Decisions use
past observed gross outcomes and cost samples. The null is stated in the oracle
history containing past latent utilities and all decision/calibration information.
The observable constant-cost coefficient is not inferred from market candles.

Initial calibration is 32 independent draws equal to .2 with probability .4 and
zero otherwise. Use the v1 bounded Hoeffding n^-2-spending confidence sequence,
delta=.01, intersected with all past intervals and [0,.2]. Static cases retain
the initial interval throughout. Contracting cases reveal one new calibration
sample after each outcome/evidence update, usable only on the next label.
Calibration draws are generated in every case, including static cases, to keep
factorial coupling explicit. Empty intersections permanently suspend cost-based
evidence and are reported as conflicts; they never generate discoveries.
Used-at-issue coverage/conflict events are recorded separately from a conflict
first caused by the last post-horizon sample, which cannot affect any test.
The inherited n^-2 spending rule is deliberately conservative: although it
allocates delta over all n>=1, this study begins querying at n=32. The union
bound over n>=32 is `delta*(6/pi^2)*sum_{n>=32}1/n^2`, about .000193; static
initial calibration queries only its n=32 slice. Keep the declared .01 global
allocation and unchanged intervals. The comparison isolates geometry under
this calibrator; it does not establish optimal calibration efficiency or power.

## Comparators

Ten methods are retained, with no selection of the best-looking method:

1. Oracle fixed linear mixture.
2. Joint per-trial fixed linear mixture.
3. Separate per-trial fixed linear mixture.
4. Oracle one-sided aGRAPA betting.
5. Joint per-trial one-sided aGRAPA betting.
6. Separate per-trial one-sided aGRAPA betting.
7. Oracle predictably centered empirical-Bernstein mixture.
8. Joint per-trial robust empirical-Bernstein mixture.
9. Separate per-trial robust empirical-Bernstein mixture.
10. Whole-history joint empirical-Bernstein nuisance profile.

Fixed linear stakes are {.05,.1,.2,.4,.8} with equal birth-fixed weights. The
one-sided aGRAPA specialization of Waudby-Smith and Ramdas, Appendix B.3, uses
stake `clip(sum(previous x)/sum(previous x^2),0,.8)`, with first stake .1 and
zero stake when the denominator is zero. Each method uses its own past proxy
(oracle uses latent D). This is a declared one-sided bounded-score specialization,
not a claim to reproduce all confidence-set machinery. Its guarantee is for the
strong conditional null only. Do not claim pathwise joint/separate dominance
when their fitted stakes differ. The prefix-weak diagnostic labels these three
methods unsupported even if their observed error is small.

Empirical-Bernstein methods use Choe and Ramdas' predictable-centering
construction with c=2 and fixed lambdas {.025,.05,.1,.2,.4}, equal mixture weights,
and `psi(lambda)=(-log(1-2*lambda)-2*lambda)/4`. Each stream's shared center gamma
is its prior observed plugin-utility mean, clipped to [-1,1], initially zero.
The plugin utility at a past label uses the coefficient sample mean available
when that label was issued; never retrospectively revise an old center.

For A=G-m, d=qA-qR, the component log factor at theta is
`lambda*(A-d*theta) - psi*(A-d*theta-gamma)^2`. Its minimum over a scalar interval
is the smaller endpoint, since it is concave. Joint local EB multiplies these
per-label minima. Separate local EB minimizes the same factor over the larger
rectangle-induced utility interval `[A-qA*u+qR*l, A-qA*l+qR*u]`. Do not simply
insert a lower utility into this nonmonotone factor.

The coherent method retains the five sums `sum A`, `sum d`,
`sum (A-gamma)^2`, `sum (A-gamma)*d`, `sum d^2`; it evaluates each component's
entire-history log evidence at the current two cost endpoints and takes the
minimum before mixing. This is componentwise profiling, not an unsupported
endpoint minimization of the entire mixture. It uses the same centers, lambdas,
normalization and error allocation as joint local EB. Nested intervals imply
pathwise coherent evidence at least joint local evidence, up to numerical error.
Static positive-d linear coherence would equal local linear evidence; any EB
gain there can also reflect its quadratic variance penalty. Do not attribute
every EB gain to sign-changing turnover cancellation.

## Validity arguments and restrictions

For fixed linear stakes and every-prefix nonpositive cumulative conditional
means, the v1 multiplicative-mean compensator dominates true-parameter evidence.
For EB, Choe and Ramdas' sub-exponential test supermartingale dominates the true
fixed-lambda product under the same prefix-weak null with predictable centers.
Mixing birth-fixed components preserves domination. Joint/local separate
infima and whole-history profiling are bounded above by the corresponding
true-parameter process on the one global simultaneous cost-coverage event.
Ville plus the per-stream union bound and .01 coverage failure give FWER<=.05.
The observed cost-profile process need not itself be an exact e-process.

For aGRAPA under the strong null, each stake is predictable, in [0,.8], and the
true bounded linear factor has conditional expectation at most one. Lower
proxy factors are no larger on simultaneous coverage. This proof does not
extend arbitrary predictable stakes to the prefix-weak null. A deterministic
counterexample uses 400 values -.06 followed by 400 values +.06 and stakes zero
in the first half, .8 in the second: all cumulative means are nonpositive, yet
the product crosses any declared threshold below (1+.8*.06)^400 with certainty.

No delayed/overlapping-label or adaptive-birth extension is added in v2; those
v1 experiments and restrictions remain. No guarantee transfers to market P&L.

## Endpoints, review and reporting

Primary diagnostic contrasts are first-stream power for joint aGRAPA minus
joint fixed linear, coherent EB minus joint local EB, and joint local EB minus
separate local EB, at effect .05. Report all factorial cells and the .02/0 cases,
not only favorable contrasts. Prespecify no universal dominance between base
method families. Null FWER, paired power differences, horizon-censored detection
time, additive post-discovery materiality-adjusted utility, calibration conflict
and coverage events, runtime, and algorithm-state memory are retained.

Power/FWER intervals are Wilson 95% intervals across worlds. Paired differences,
censored times and utility use paired world-level normal Monte Carlo intervals;
these are estimation diagnostics, not multiplicity-adjusted discovery claims.
Choose the lowest-index first-discovered stream, activate only on subsequent
labels, and do not compound synthetic utility into a funded account.

Save world-level event, timing, utility and cost-coverage arrays, all method/case
summaries, deterministic traces and manifests. Hash actual reviewed source and
protocol before the substantive run. Mechanical smoke runs are separately
labeled and cannot replace the study. Preserve failures. Independently review
the implementation, proof restrictions and results before manuscript integration.
