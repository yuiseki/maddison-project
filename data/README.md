---
license: cc-by-4.0
language:
- en
pretty_name: Maddison Project Database (2018, 2020, 2023)
task_categories:
- time-series-forecasting
- tabular-regression
tags:
- economics
- economic-history
- gdp
- gdp-per-capita
- population
- maddison
- ggdc
size_categories:
- 100K<n<1M
configs:
- config_name: '2023.full_data'
  data_files: parquet/2023/full_data.parquet
  default: true
- config_name: '2020.full_data'
  data_files: parquet/2020/full_data.parquet
- config_name: '2018.full_data'
  data_files: parquet/2018/full_data.parquet
- config_name: '2018.regional_data'
  data_files: parquet/2018/regional_data.parquet
- config_name: '2018.region_composition'
  data_files: parquet/2018/region_composition.parquet
- config_name: '2018.benchmark_1990'
  data_files: parquet/2018/benchmark_1990.parquet
---

# maddison-project

The Maddison Project Database (MPD): long-run estimates of real GDP per
capita and population by country, from year 1 to the present, kept by the
Groningen Growth and Development Centre (GGDC), University of Groningen,
continuing the work of Angus Maddison. Three releases, 2018, 2020 and 2023,
each as published, with a typed Parquet of each table beside the original
files.

CC BY 4.0, with the citations each release asks for (see Licence).

## Releases

| subset | rows | countries | years | values | from |
|---|---:|---:|---|---|---|
| `2023.full_data` | 131,144 | 169 | 1 to 2022 | gdppc 21,366, pop 17,875 | `raw/2023/mpd2023_web.xlsx`, sheet Full data |
| `2020.full_data` | 21,682 | 169 | 1 to 2018 | gdppc 19,706, pop 17,199 | `raw/2020/mpd2020.xlsx`, sheet Full data |
| `2018.full_data` | 19,873 | 169 | 1 to 2016 | cgdppc 17,441, rgdpnapc 17,712, pop 16,859 | `raw/2018/mpd2018.xlsx`, sheet Full data |
| `2018.regional_data` | 1,039 | 7 regions and the World | 1870 to 2016 | 761 each | `raw/2018/mpd2018_region_data.xlsx`, sheet Long data |
| `2018.region_composition` | 147 | 147 | | | `raw/2018/mpd2018_region_data.xlsx`, sheet Composition |
| `2018.benchmark_1990` | 17,872 | 169 | 1 to 2016 | gdppc 17,872 | `raw/2018/mpd2018_1990bm.xlsx`, sheet LongForm |

"values" counts the rows where the column is not empty. The 2023 table has
a row for every country and every year that any country has (776 years), so
most of its rows are empty; the 2018 and 2020 tables have rows only where
there is a value.

The releases cannot be stacked into one series. Each is a full revision
made with its own method, so the same country and year has other values in
another release. The 2020 release page says it "uses a different methodology
compared to the 2018 update", having "to some extent gone back to the
original Maddison approach". Of the 19,213 country-years with `gdppc` in
both 2020 and 2023, 6,601 differ. Japan in 1950:

| release | column | value |
|---|---|---:|
| 2018 | `cgdppc` (2011 US$, multiple benchmarks) | 2,519 |
| 2018 | `rgdpnapc` (2011 US$, 2011 benchmark) | 3,023 |
| 2018 | `benchmark_1990.gdppc` (1990 US$) | 1,921 |
| 2020 | `gdppc` (2011 US$) | 3,062 |
| 2023 | `gdppc` (2011 US$) | 3,062 |

and in 2016: 36,452 and 37,465 (2018), 37,465 (2020), 37,384.56 (2023).
Use one release, and say which.

The xlsx and dta files of each release and the documentation papers of 2018
and 2020 are under `raw/<release>/`, byte for byte as served; each
release's `MANIFEST.json` gives their URLs, sizes, sha256 and Last-Modified,
and for 2023 the SHA-1 DataverseNL states. MPD 2013 and the Maddison
Database 2010 are not here: their pages state no licence.

## Files and columns

The Parquet is made from the xlsx with DuckDB's excel extension. The dta
files were not read and are only carried unchanged.

Every cell is read as its text and typed by the column's name, never by
inference:

| columns | type |
|---|---|
| `year` | INTEGER |
| `gdppc`, `cgdppc`, `rgdpnapc`, `pop` | DOUBLE |
| everything else | VARCHAR, the text of the cell |

The columns of each table, with the definitions in the workbook's Legend or
Notes sheet:

| table | column | meaning |
|---|---|---|
| all country tables | `countrycode` | 3-letter ISO country code; includes former states such as CSK, SUN, YUG |
| | `country` | country name |
| | `year` | year |
| 2023, 2020 `full_data` | `gdppc` | real GDP per capita in 2011 US$ |
| | `pop` | population, mid-year (thousands) |
| 2023 `full_data` | `region` | one of 8 regions, as the release groups countries |
| 2018 `full_data` | `cgdppc` | real GDP per capita in 2011 US$, multiple benchmarks (for cross-country income comparisons) |
| | `rgdpnapc` | real GDP per capita in 2011 US$, 2011 benchmark (for cross-country growth comparisons) |
| | `pop` | population, mid-year (thousands) |
| | `i_cig` | whether the observation is extrapolated, a benchmark, or interpolated |
| | `i_bm` | for benchmarks, the kind of benchmark |
| 2018 `benchmark_1990` | `gdppc` | GDP per capita in 1990 US$, Maddison benchmark, updated time series |
| 2018 `regional_data` | `region` | two-letter code: af, ea, ee, la, wa, we, wo, wd (World) |
| | `region_name` | region name |
| | `year`, `cgdppc`, `rgdpnapc`, `pop` | as in 2018 `full_data` |
| 2018 `region_composition` | `countrycode` | country |
| | `region1870` | its region for the years before 1950 (40 countries) |
| | `region1950` | its region from 1950 (all 147) |

```sql
-- DuckDB, straight off the Hub: GDP per capita of Japan, release 2023
SELECT year, gdppc, pop
FROM 'hf://datasets/yuiseki/maddison-project/parquet/2023/full_data.parquet'
WHERE countrycode = 'JPN' AND gdppc IS NOT NULL
ORDER BY year;
```

Note that a chart like this one falls under the project's request to cite
the original sources (see Licence).

## Things to know

- In 2018 `full_data`, the Legend describes `i_cig` as "0/1/2" and `i_bm` as
  codes 1 to 5, but the xlsx holds the labels: `i_cig` is Extrapolated
  (10,318 rows), Interpolated (6,032), Benchmark (1,364) or an empty string
  (2,159); `i_bm` is ICP PPP estimates (1,144), Multiple of subsistence
  (122), Historical income benchmarks (68), Real wages and urbanization
  (21), Braithwaite (1968) PPPs (9) or an empty string (18,509). The empty
  strings are kept as empty strings, as in the sheet, not turned into NULL.
- The 2018 sheet Full data has 126 formatted but empty rows at its foot.
  They are not in the Parquet. No other row was dropped.
- In 2018, GDP per capita is rounded to the nearest dollar and population to
  the nearest thousand (the Legend says so). In 2020 and 2023 the values are
  not rounded; 2023 has 8,841 non-integer `gdppc` and 9,565 non-integer `pop`.
- 2018 `regional_data`: before 1950 the regions are made of fewer countries
  (`region1870` in `region_composition`) and linked to the 1950 regions. The
  Legend: "Data for the World in 1870 do not include Eastern Europe. Data for
  the World before 1950 do not include Africa and Western Asia." The years
  are not continuous before 1950; 278 of the 1,039 rows have no values.
- 2018 `region_composition` lists 147 countries, not all 169.
- The 2018 regions (7 two-letter codes and wd for the World, with Africa
  and Western Asia) are not the 2023 `region` values (8 names, with Middle East and North
  Africa, and Sub Saharan Africa).
- The 2020 and 2023 workbooks also have a Regional data sheet, wide, with
  two header rows and unlabelled columns, and the country values again in
  wide form (GDP pc, Population). They are not made into Parquet; they are
  in the xlsx under `raw/`. So are the 2018 sheet Partial countries (England
  from 1252 and Holland, in wide form with two header rows), the 2023 sheet
  Maddison original sources, and the Sources sheets.
- The 2018 release has no Sources sheet; its page points to Appendix A of
  Bolt et al. (2018), the paper in `raw/2018/gd174.pdf`.
- The xlsx and the dta of a release were not compared with each other.

## Checked before upload

`scripts/02_verify.py` in the source repository checks:

- every raw file against its release's `MANIFEST.json` (size, sha256, and
  for 2023 the SHA-1 DataverseNL states) and that it opens as its type
- each sheet is read again with the Python standard library alone (zipfile
  and xml.etree, not DuckDB), and the Parquet has the same number of rows,
  equal to the pinned counts above
- every value of every row equals the cell it came from, typed the same way,
  in sheet order (sha256 over all values printed for both sides)
- the columns are the sheet's header, each of the type its name gives
- (countrycode, year) is unique in the country tables, (region, year) in
  `regional_data`, countrycode in `region_composition`
- a DuckDB with no extension loaded opens every file
- no row group has a bloom filter

## Licence

Each release page states CC BY 4.0. Read on 2026-10-05:

2023, https://www.rug.nl/ggdc/historicaldevelopment/maddison/releases/maddison-project-database-2023 :

> Maddison Project Database, version 2023 by Jutta Bolt and Jan Luiten van
> Zanden is licensed under a Creative Commons Attribution 4.0 International
> License.

DataverseNL (https://doi.org/10.34894/INZBF2) gives the 2023 dataset the
licence CC-BY-4.0.

2020, https://www.rug.nl/ggdc/historicaldevelopment/maddison/releases/maddison-project-database-2020 :

> Maddison Project Database, version 2020 by Jutta Bolt and Jan Luiten van
> Zanden is licensed under a Creative Commons Attribution 4.0 International
> License.

2018, https://www.rug.nl/ggdc/historicaldevelopment/maddison/releases/maddison-project-database-2018 :

> Maddison Project Database, version 2018 by Jutta Bolt, Robert Inklaar,
> Herman de Jong and Jan Luiten van Zanden is licensed under a Creative
> Commons Attribution 4.0 International License.

The 2020 and 2023 pages also ask, under "Attribution requirement":

> All original papers must be cited when: the data is shown in any
> graphical form subsets of the full dataset that include less than a dozen
> (12) countries are used for statistical analysis or any other purposes A
> list of original papers can be found in the source sheet of the database.
> When neither a) or b) apply, then the MPD as a whole should be cited.

(the two conditions are a list on the page). The Sources sheet is in
`raw/2020/mpd2020.xlsx` and `raw/2023/mpd2023_web.xlsx`. For 2018 the page
says: "For the references to the original research on individual
countries, see Appendix A of Bolt et al. (2018)."

What was changed: the xlsx, dta and pdf files are unchanged. The Parquet
holds six sheets of those xlsx files, typed by column name, with blank rows
left out; no value was changed. `LICENSE` beside this file says the same.

## Citation

Release 2023, as its page asks:

> Bolt, Jutta and Jan Luiten van Zanden (2024), "Maddison style estimates of
> the evolution of the world economy: A new 2023 update", Journal of
> Economic Surveys, 1-41. DOI: 10.1111/joes.12618

Release 2020, as its page asks:

> Maddison Project Database, version 2020. Bolt, Jutta and Jan Luiten van
> Zanden (2020), "Maddison style estimates of the evolution of the world
> economy. A new 2020 update".

(the paper is `raw/2020/wp15.pdf`)

Release 2018, including its regional and 1990 benchmark data, as its page
and the workbooks' Legend ask:

> Maddison Project Database, version 2018. Bolt, Jutta, Robert Inklaar,
> Herman de Jong and Jan Luiten van Zanden (2018), "Rebasing 'Maddison': new
> income comparisons and the shape of long-run economic development",
> Maddison Project Working paper 10

(the paper is `raw/2018/gd174.pdf`; the 1990 benchmark workbook writes
"Maddison Project Database, version 2018; 1990$ benchmark.")

When the data is charted, or fewer than 12 countries are used, also cite
the original papers in the release's Sources sheet (2018: Appendix A of
Bolt et al. 2018).
