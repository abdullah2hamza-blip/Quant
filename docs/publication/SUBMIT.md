# Technical report release and future submission guide

Author: Abdullah Hamza, Independent Researcher, abdullah2hamza@gmail.com.
The planned public technical-report release is v1.0.1 on the existing Quant
GitHub repository and the author's Kaggle account `abdullah2hamza`. Publication
status, final URLs, the release commit/tag and hosted execution are unverified
until the publication record documents the actual checks. No DOI, journal
acceptance or independent human peer review is asserted by preparing these files.

## Technical report assets

Use the named revision `cost-aware-bitcoin-research-v5.pdf`, not the historical
anonymous 31-page PDF. The final submission folder contains:

- `manuscript-source-v5.zip`: main.tex at archive root, all included sections,
  generated tables/macros/figures and the bibliography. It does not need Python
  or vendor data to compile.
- `quant-research-release-v5.zip`: software, locks, frozen protocols/source,
  accepted results, original-bot extension and data-access manifests. It is a
  separate companion, not a substitute for the article's TeX source ZIP.
- `submission-metadata.json`: title, plain abstract, author information and
  suggested keywords for form fields. No invented DOI or journal reference.
- `release-receipt.json` and the final release-validation sidecar: exact hashes,
  layout check and extracted-source verification of the delivered bytes.

The scientific contribution is a controlled diagnostic of paired-cost and
temporal-nuisance information loss using established methods, plus a negative
EMA application and a separately labeled exploratory original-bot amendment.
Describe it that way in titles, abstracts and cover letters. It does not claim
a first sequential trading test, a new general theorem or a profitable bot.

GitHub/Kaggle hosting is a public research release, not peer review or a journal
publication. The user has authorized this repository's public transition and
the Kaggle release after the release checks pass. Journal, conference or an
additional preprint/archive service requires separate instructions.

## Optional future preprint-service route

Upload the manuscript-source ZIP through the service's TeX submission flow;
select main.tex if asked and inspect its generated PDF. The local build uses
Tectonic 0.17.0 and standard LaTeX packages. A service may use a different TeX
distribution, so the service-generated preview is the final platform check.
Provide the actual companion archive or its verified versioned release URL as
the replication material. Refer to the actual release tag/commit and tested
notebook version, rather than an unversioned scaffold. The technical-report
release does not itself submit the work to an additional archive service.

The author must complete account identity/endorsement and the service's
submission declarations. A plausible topical category is quantitative finance
with a statistical-methods emphasis; moderation determines the final category.
Copy the prepared abstract/author metadata and leave DOI/journal fields empty
until identifiers actually exist. Read the preview for missing figures, formulas,
citations and appendix pages before final submission.

## Licensing is component-specific

Original paper text/synthetic displays are CC BY 4.0 and original code is MIT,
as chosen by the author. Binance-derived market material is an explicit
CC BY-NC-SA 4.0 exception with attribution and provider terms. Do not certify an
unrestricted commercial grant over every component. Use a submission license
and venue that accommodate those exceptions; a venue requiring incompatible
rights needs provider permission or a separately reviewed replacement.
arXiv's current license page includes CC BY-NC-SA 4.0 as well as other options;
the platform license choice must remain consistent with the actual components.
The separate CC BY grant for original text does not grant rights to vendor data.

## Optional future journal route

The cover letter is supplied as an editable complete draft. Select an outlet
that accepts diagnostic/empirical methodological papers and negative financial
results, and check its article length, supplemental files, AI disclosure,
preprint and third-party-material policies. Keep the full proofs and complete
case/control tables available as supplementary material if the journal asks
for a shorter main article. Maintain the matched-settings controls and all
negative findings; do not trim them to imply trading superiority.

AI-assisted internal consistency checks and recorded-host reproduction are documented.
The author remains responsible for the submission and should read the entire
paper, equations, figures, limitations and declarations before making personal
authorship/originality certifications. Preparation cannot guarantee acceptance.

## AI assistance and responsibility

OpenAI Codex was used for literature research, experimental design, code
preparation and testing, statistical analysis, interpretation, figure generation,
manuscript drafting and revision, and reproducibility and release checks.
Exact model versions were not consistently recorded. The human author retains
responsibility for the final work. Automated checks and AI-assisted reviews are
not independent human peer review or evidence of completed human-author review.

## Primary platform and rights sources checked 2026-10-23

- https://info.arxiv.org/help/submit_tex.html
- https://info.arxiv.org/help/prep.html
- https://info.arxiv.org/help/license/index.html
- https://info.arxiv.org/help/ancillary_files.html
- https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md
- https://www.bitstamp.net/api/

Use the reproduction guide for the distinction between saved-result builds,
exact-input restoration, and full numerical replay. Archive integrity or a green
test suite alone does not establish statistical assumptions or publication fit.
