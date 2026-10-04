# maddison-project

A reproducible collection of the Maddison Project Database (MPD): long-run
estimates of GDP per capita and population by country, from year 1 to the
present, maintained by the Groningen Growth and Development Centre (GGDC),
University of Groningen. The releases 2018, 2020 and 2023 are taken, as
published. This repository holds the code; `data/raw/` is generated.

Official source: https://www.rug.nl/ggdc/historicaldevelopment/maddison/
(releases listed at https://www.rug.nl/ggdc/historicaldevelopment/maddison/releases/).
The 2023 release is on DataverseNL, https://doi.org/10.34894/INZBF2 .

| release | where | files taken |
|---|---|---|
| 2018 | www.rug.nl | `mpd2018` (xlsx, dta), regional data, 1990 benchmark data, documentation paper `gd174.pdf` |
| 2020 | www.rug.nl | `mpd2020` (xlsx, dta), documentation paper `wp15.pdf` |
| 2023 | DataverseNL | `mpd2023_web.xlsx`, `maddison2023_web.dta` |

MPD 2013 and the Maddison Database 2010 are not taken: their pages state no
licence.

## Licence and citation

The 2018, 2020 and 2023 releases are published under the Creative Commons
Attribution 4.0 International licence,
https://creativecommons.org/licenses/by/4.0/ (2023: "Maddison Project
Database, version 2023 by Jutta Bolt and Jan Luiten van Zanden").

Cite the 2023 release as: Bolt, Jutta and Jan Luiten van Zanden (2024),
"Maddison style estimates of the evolution of the world economy: A new 2023
update", Journal of Economic Surveys, 1-41. DOI: 10.1111/joes.12618 .
The 2020 release asks for Bolt, Jutta and Jan Luiten van Zanden (2020),
"Maddison style estimates of the evolution of the world economy. A new 2020
update" (the paper fetched as `wp15.pdf`); the 2018 release asks for Bolt,
Jutta, Robert Inklaar, Herman de Jong and Jan Luiten van Zanden (2018),
"Rebasing 'Maddison': new income comparisons and the shape of long-run
economic development", Maddison Project Working paper 10 (fetched as
`gd174.pdf`).

The 2020 and 2023 release pages ask that all original papers be cited when
the data is shown in any graphical form, or when a subset of fewer than a
dozen (12) countries is used for statistical analysis or any other purpose.
The list of original papers is in the Sources sheet of the database (for
2018, Appendix A of Bolt et al. 2018). Otherwise the MPD as a whole is cited.

The code in this repository fetches and checks the files; it does not change them.

## Running it

```sh
uv run python scripts/01_download.py   # fetch what is missing
uv run python scripts/02_verify.py     # re-check every file against its manifest
uv run python -m pytest                # parsing tests on trimmed real pages
```

`01_download.py` uses only the Python standard library. It finds the release
pages on the official listing, refuses a release page that does not link CC BY
4.0, takes the xlsx, dta and pdf links on each page, and for 2023 reads the
file list, sizes and SHA-1 checksums from DataverseNL's public dataset API.
Requests are sequential and at least one second apart; a file already in the
manifest with the same sha256 is not fetched again.

## Layout

```
scripts/01_download.py        release pages -> files -> data/raw/<release>/ and MANIFEST.json
scripts/02_verify.py          sha256, stated SHA-1, zip test of xlsx, Stata and PDF headers
tests/                        parsing tests
tests/fixtures/               trimmed copies of the listing, release pages and dataset API response
data/raw/<release>/           generated: the files as served, and MANIFEST.json
```

`MANIFEST.json` records the release page, the licence check, for 2023 the
DataverseNL dataset version and release time, and for each file its url,
link label, bytes, sha256, Last-Modified, Content-Type and fetch time (UTC).
