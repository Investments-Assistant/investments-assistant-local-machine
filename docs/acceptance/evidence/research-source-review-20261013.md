# Historical research source review — 2026-10-13

Status: documentation-only review. No source was configured, queried for data,
or downloaded; no dataset or user-specific information was sent. This does not
authorize a source or pass L14.

## Candidate news inputs

- **GDELT 2.0 GKG/event archive:** GDELT describes its datasets as free and
  unrestricted for academic, commercial, or government use, subject to
  attribution. Its 2.0 graph data updates every 15 minutes and archives support
  historical analysis. GDELT's timestamping note says retrieval-completion time
  is authoritative for untrusted open-web material while the publisher-claimed
  creation time is secondary. This helps avoid treating a publisher timestamp
  as the time our system could have observed a story. It does not establish the
  first time this application could have accessed a story, preserve every
  article's full text, prove article-level completeness, or establish that any
  chosen instrument universe is represented. Prefer retaining attributable
  metadata, source URL, archive batch/availability time and content hash; do not
  assume linked publishers grant full-text storage rights.
- **SEC EDGAR submissions and filing history:** SEC says `data.sec.gov` APIs
  need no API key and are updated as filings are disseminated; it also provides
  RSS feeds and more than 20 years of filing search. This is an official,
  timestamped primary disclosure source, not a broad news source or a market
  price feed. Automated use must follow SEC fair-access and privacy guidance.

## Price-data boundary

- No reviewed source here establishes a no-cost, license-cleared historical
  daily price series for the eventual eligible instruments and horizon.
- FRED's S&P 500 series is a daily market-close **price index**, not an
  investable instrument or total-return series; its current notes limit the
  displayed history to ten years and identify S&P Dow Jones Indices as the
  copyright owner, with reproduction requiring prior written permission. FRED's
  general/API terms also leave third-party-series rights with the series owner
  and require an API key. It is not a drop-in free substitute for an approved
  instrument universe, dividend-inclusive benchmark or retained application
  dataset. No FRED request or data download was made.
- Nasdaq Data Link's WIKI/PRICES page describes 3,000 US equities with price,
  dividend and split data, but states that the community feed has not been
  supported since April 2018 and is not recommended for investment or analysis;
  current account pricing must be checked. It is not suitable as verified
  acceptance evidence for this Goal. No account or data was requested.
- The existing optional `src/research/history.py` adapter uses
  `yfinance.Ticker.history`. The yfinance maintainers state that the project
  is not affiliated with Yahoo, that Yahoo's API is intended for personal use,
  and that Yahoo's terms govern rights to the downloaded data. Yahoo's linked
  legal pages rejected automated retrieval during this review, so the exact
  applicable rights for this application's investment research, backtesting,
  retention and possible commercial use remain unverified. The Python package's
  open-source license does not grant rights to Yahoo's data. Do not invoke this
  adapter for acceptance evidence or persist its results until those data
  rights and permitted use are established. No Yahoo request was made.
- Nasdaq Data Link offers some free datasets/samples, but its terms bind use to
  the dataset-specific order form and third-party provider terms. A free account
  or sample is not evidence that a selected series covers the approved universe
  or grants this application's intended research/storage use.
- Alpha Vantage's published terms default to personal, non-commercial use and
  explicitly classify individual investment analysis, research and testing as
  commercial use. It is therefore not treated as an approved free source here.

## Existing application boundary

Persistent news ingestion already fails closed unless an operator-reviewed,
current source policy is configured (`src/news/policy.py` and
`src/news/ingestion.py`). It records the application's local observation time;
publisher time does not backdate it. The replay model separately requires
timezone-aware publication and availability times (`src/research/replay.py`),
and ignores news before `available_at`.

A GDELT retrieval-completion timestamp describes when GDELT observed untrusted
web content. It is not evidence of when this application first had access to
that item. Do not copy it into the application's observed-time field or claim it
proves strategy availability. A future permitted adapter would need to retain
both clocks and an attributable source-availability record; until that evidence
exists, historical replay must exclude the item or report the availability gap.
No adapter was added or source policy enabled in this review.

## Consequence for L14

GDELT plus SEC are plausible no-cost news-source candidates for review, with
different coverage and timestamp semantics. They do not solve the historical
market-price requirement or select a representative universe. The next
decision-dependent step is for the user to approve the permitted news-source
scope and provide/approve a price dataset with instrument coverage, timestamp
provenance, retention rights and cost. Until then, keep the fixed evaluation
unchanged, report `INSUFFICIENT EVIDENCE`, and keep live `NO-GO`.

## Primary documentation reviewed

- [GDELT terms and attribution](https://gdeltproject.org/about.html)
- [GDELT 2.0 archive/update information](https://gdeltproject.org/data.html)
- [GDELT timestamping approach](https://blog.gdeltproject.org/a-behind-the-scenes-look-at-how-we-think-about-master-file-formats-and-timestamping/)
- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [SEC EDGAR search and RSS](https://www.sec.gov/search-filings)
- [Nasdaq Data Link license terms](https://data.nasdaq.com/terms)
- [Alpha Vantage terms](https://www.alphavantage.co/terms_of_service/)
- [yfinance maintainer notice and Yahoo-terms links](https://github.com/ranaroussi/yfinance)
- [Yahoo API for YDN terms](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html) (automated retrieval unavailable during review)
- [Yahoo API terms and conditions](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apitnc/index.html) (automated retrieval unavailable during review)
- [Yahoo Developer Network guidelines](https://legal.yahoo.com/us/en/yahoo/guidelines/ydn/index.html) (automated retrieval unavailable during review)
- [FRED S&P 500 series notes](https://fred.stlouisfed.org/series/SP500)
- [FRED API terms](https://fred.stlouisfed.org/docs/api/terms_of_use.html)
- [Nasdaq Data Link WIKI/PRICES dataset status](https://data.nasdaq.com/databases/WIKIP)
