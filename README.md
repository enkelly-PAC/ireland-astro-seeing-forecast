# Ireland Astro Seeing Forecast

An imaging-first forecast and planning application for the Moon and planets
across Ireland. It combines UK Met Office cloud and upper-air forecasts with
an independent reconstruction of a meteoblue-style "Astronomy Seeing"
forecast, built only from public documentation and standard atmospheric
optics equations. **This project contains no
proprietary meteoblue source code, model internals, weights, or scraped
forecast data.** It is a best effort, clearly labelled approximation for
research, learning and permitted black box calibration purposes.

## Sources cited

The following public pages describe the documented mechanics this project
reconstructs. You are responsible for respecting each site's terms of use
and data licence when you view, save or calibrate against their content;
this project never fetches them automatically.

```
https://content.meteoblue.com/en/private-customers/website-help/outdoor-and-sports/astronomy-seeing
```

```
http://www.meteosurf.com/spastro/seeing/index.html
```

```
https://journals.ametsoc.org/view/journals/apme/49/8/2010jamc2350.1.xml
```

The first two pages are meteoblue's own public help text (a detailed help
article and a related discussion of the underlying seeing concept). The
third is a peer reviewed atmospheric science journal article used here only
as a standard physics reference for turbulence optics and refractivity
equations; it is not a meteoblue source and is not claimed to describe
meteoblue's internals.

## What this is, and is not

- It **is** a transparent, from-scratch implementation of standard
  atmospheric thermodynamics (potential temperature, gradient Richardson
  number), standard turbulence optics (Cn2, Fried parameter, seeing) and
  the specific numeric rules meteoblue states publicly (the bad layer
  gradient threshold, the CAT Richardson threshold, the 200 hPa jet stream
  sample level).
- It **is not** a decompilation, scrape, or reverse engineering of
  meteoblue's actual model code, coefficients, or proprietary datasets.
  Every coefficient we could not find publicly documented is explicitly
  labelled INFERRED/CALIBRATABLE and defaults to a placeholder value that
  you are expected to refine with your own permitted calibration data using
  the `calibrate` command.

## Confidence labelling convention

Every rule in the code carries one of three labels, both in docstrings and
in the `method_labels` section of forecast output:

| Label | Meaning |
| --- | --- |
| `PUBLICLY DOCUMENTED` | Stated in meteoblue's own public help text, reproduced as closely as the public wording allows. |
| `STANDARD PHYSICS` | A textbook atmospheric thermodynamics, dynamics or optics equation, independent of meteoblue. |
| `INFERRED/CALIBRATABLE` | Our own construction; the functional form may be grounded in standard physics but the scaling constants are placeholders, meant to be tuned against permitted black box data. |

## Reverse engineering confidence table

| Mechanic | Label | Confidence | Notes |
| --- | --- | --- | --- |
| Potential temperature `theta = T * (1000/p) ** (Rd/cp)` | STANDARD PHYSICS | High | Poisson's equation, universally used. |
| Bad layer gradient threshold `dtheta/dz >= 0.005 K/m` (0.5 K/100 m) | PUBLICLY DOCUMENTED | High | Directly stated in meteoblue's detailed help text. |
| Bad layer 2 K potential-temperature difference | PUBLICLY DOCUMENTED | High | The Meteosurf method linked by meteoblue gives this as the second bad-layer criterion. Merging adjacent qualifying interfaces and selecting the strongest run are implementation choices. |
| Gradient Richardson number | STANDARD PHYSICS | High | Standard definition using stability and total horizontal wind shear. |
| CAT flag `Ri <= 0.25` | PUBLICLY DOCUMENTED | High | Standard aviation meteorology convention, matches meteoblue's own wording. |
| Jet stream sampled at 200 hPa | PUBLICLY DOCUMENTED | High | Stated in meteoblue help text. |
| Jet stream poor thresholds (35 m/s detailed vs 20 m/s inline) | PUBLICLY DOCUMENTED (with a documented internal discrepancy) | Medium | See "Jet stream threshold discrepancy" below. |
| Cloud cover bands (0 to 4, 4 to 8, 8 to 15 km) | PUBLICLY DOCUMENTED | High | Stated in meteoblue help text; kept independent of seeing per the documentation. |
| Cn2 Model 1 functional form (stability, shear/CAT, refractivity scaling) | STANDARD PHYSICS form, INFERRED coefficients | Medium | Building blocks (temperature structure parameter, shear turbulence generation, dn/dT scaling) are standard; the combining weights are placeholders. |
| Cn2 Model 2 functional form (density/refractivity fluctuations, humidity gradients) | STANDARD PHYSICS form, INFERRED coefficients | Medium | Uses ideal gas law density gradients and the Smith-Weintraub wet refractivity term; weights are placeholders. |
| Cn2 vertical integration | STANDARD PHYSICS | High | Midpoint/trapezoidal rule over layer interfaces. |
| Fried parameter `r0 = [0.423 k^2 integral(Cn2 dz)] ** (-3/5)` | STANDARD PHYSICS | High | Fried (1966) definition, standard in adaptive optics literature. |
| Seeing `epsilon = 0.98 * lambda / r0` | STANDARD PHYSICS | High | Standard seeing disc FWHM approximation. |
| Seeing index 1 (poor) to 5 (excellent) thresholds | INFERRED/CALIBRATABLE | Low | The direction is published, but the arcsecond cut points are not; use `calibrate` to refine. |
| Display arcsecond blend and bad-layer penalty | INFERRED/CALIBRATABLE | Low | Our own construction to produce a single headline number; not a documented meteoblue output. |

## Jet stream threshold discrepancy

meteoblue's own public pages are internally inconsistent about when the 200
hPa jet stream is considered disruptive to seeing:

- The **detailed help article** states the jet is too weak below 5 m/s and
  disruptive/poor above **35 m/s**.
- A shorter **inline tooltip** on the same site states poor above **20 m/s**.

This project defaults to the detailed help figure (35 m/s), on the
assumption that the longer, more carefully written article is more likely
to be accurate, and exposes the 20 m/s figure as an explicit, documented
alternative:

```
python -m meteoblue_seeing forecast sample.json --use-inline-jet-threshold
```

or by setting `use_inline_jet_threshold: true` in a config JSON file passed
with `--config`.

## Equations implemented

```
theta = T_kelvin * (1000 hPa / P) ** (R_d / c_p)

bad layer interface: dtheta/dz >= 0.005 K/m (0.5 K/100 m)
bad layer report: merged run also needs theta_top - theta_bottom >= 2 K

Ri = (g / theta_ref) * (dtheta/dz) / ((du/dz)^2 + (dv/dz)^2)
CAT flag: Ri <= 0.25

r0 = [0.423 * k^2 * integral(Cn2 dz)] ** (-3/5),  k = 2 * pi / lambda

epsilon = 0.98 * lambda / r0   (radians, converted to arcseconds)

N = 77.6 * P / T + 3.73e5 * e / T^2   (Smith-Weintraub refractivity, N-units)

rho = P / (R_d * T)   (ideal gas law, dry air)
```

## Project layout

```
pyproject.toml
README.md
Run-Wicklow-Forecast.ps1
Run-Ireland-Forecast.ps1
src/meteoblue_seeing/
    __init__.py
    __main__.py
    config.py           configuration, coefficients and thresholds with labels
    validation.py       input validation
    physics.py          potential temperature, bad layer, Richardson/CAT, jet, cloud bands
    models.py           Cn2 models, integration, Fried parameter, seeing, index mapping
    forecast.py         orchestration, produces the final result document
    html_parser.py      local, network-free HTML table extraction (html.parser only)
    calibrate.py        deterministic grid search calibration utility
    ukv_clouds.py       Windy-exported UKV cloud CSV import and combination
    ukv_aws.py          direct Met Office UKV cloud retrieval from AWS Open Data
    wicklow_forecast.py Met Office UKV forecast pipeline; generalised to any
                        Ireland location, with backward-compatible Wicklow
                        Head wrappers
    ireland.py          shared Ireland region bounding box and validation
    astronomy_details.py
                        Moon and planet rise, set, meridian, phase and
                        topocentric position calculations
    geocoding.py        server-side Open-Meteo Geocoding API proxy, filtered
                        to Ireland
    server.py           local HTTP server (UI and API)
    ui.py               loads the packaged browser UI HTML asset
    assets/ireland_ui.html
                        the dark-theme browser UI (map, search, table, cards)
    cli.py              command line interface
tests/                  unittest test suite
data/
    sample_input.json             example forecast input (synthetic)
    sample_calibration.csv        example calibration dataset (synthetic)
    sample_meteoblue_page.html    fixture for the HTML table parser (synthetic)
```

## Installation

Requires Python 3.11 or later. Astronomy Engine supplies the topocentric
Moon and planetary ephemerides.

Astronomy Engine is used for refraction-aware rise and set searches,
meridian transit, topocentric altitude and azimuth, visual magnitude,
illumination and Moon phase calculations:

```
https://github.com/cosinekitty/astronomy
```

The locally bundled planet thumbnails are cropped and optimised from NASA
Scientific Visualization Studio animation 30710, which identifies the
mission or instrument source for each planet image. The Moon thumbnail is
derived from NASA's Lunar Reconnaissance Orbiter Moon mosaic. The Saturn
thumbnail is derived from user-supplied astrophotography and replaces the
NASA Saturn image in both the planet card and seeing simulator.
When the Moon is selected, the seeing simulator uses the user's Clavius
capture from 3 October 2022 rather than the full-disc Moon thumbnail.

```
https://svs.gsfc.nasa.gov/30710/
https://science.nasa.gov/resource/moon-mosaic/
```

The seeing comparison is a qualitative browser simulation. It follows the
target selected in the planetary imaging planner and applies increasing
image motion and blur for lower scores. It is not an optical propagation
model and does not account for a particular telescope aperture,
magnification or wavelength.

The hourly seeing score uses an approximate conversion from calculated
stellar-image FWHM to the familiar amateur Pickering 1 to 10 scale:

| Seeing FWHM | Pickering description | Score |
|---|---|---:|
| Below 0.5 arcsec | Perfect | 10 |
| 0.5 to below 0.7 arcsec | Excellent | 9 |
| 0.7 to 1.0 arcsec | Very good | 8 |
| Over 1.0 to 1.5 arcsec | Good | 7 |
| Over 1.5 to 2.0 arcsec | Good | 6 |
| Over 2.0 to 2.5 arcsec | Average | 5 |
| Over 2.5 to 3.0 arcsec | Poor | 4 |
| Over 3.0 to 4.0 arcsec | Poor | 3 |
| Over 4.0 to 5.0 arcsec | Terrible | 2 |
| Over 5.0 arcsec | Terrible | 1 |

This is deliberately labelled approximate. Pickering measures the visual
appearance of a diffraction pattern through a telescope, while arcseconds
measure stellar-image FWHM, so they are related but not interchangeable.

This replaces the earlier coarse conversion that could only produce
scores 1, 3, 6, 8 and 10.

```
pip install -e .
```

Or run directly without installing, from the project root:

```
python -m meteoblue_seeing forecast data/sample_input.json
```

## CLI usage

### `forecast`

Run a full seeing reconstruction on a JSON input file.

```
python -m meteoblue_seeing forecast data/sample_input.json
python -m meteoblue_seeing forecast data/sample_input.json --config my_config.json
python -m meteoblue_seeing forecast data/sample_input.json --use-inline-jet-threshold
python -m meteoblue_seeing forecast data/sample_input.json --output result.json
```

Input JSON shape (see `data/sample_input.json` for a full example):

```
{
  "site_elevation_m_asl": 500,
  "wavelength_nm": 500,
  "location_name": "optional label",
  "levels": [
    {
      "altitude_m_asl": 500,
      "pressure_hpa": 950,
      "temperature_c": 18.0,
      "relative_humidity_pct": 55,
      "wind_u_ms": 2,
      "wind_v_ms": 1,
      "cloud_cover_pct": 20
    },
    ...
  ]
}
```

Levels must be ordered with strictly increasing altitude and strictly
decreasing pressure, must include at least two levels, and every numeric
field must be finite and within plausible physical bounds. Validation
failures are reported explicitly with the offending level index and field.

### `wicklow-forecast`

Generate a rolling, four-day (96 hour by default) cloud and seeing forecast
for Wicklow Head from live UK Met Office data through Open-Meteo's
`ukmo_seamless` model. It uses UKV 2 km in the near term and UKMO Global
10 km for the extended period, providing complete upper-air profiles for
the full four days. Requires internet access.

```
python -m meteoblue_seeing wicklow-forecast --hours 96 --output-directory reports
```

This writes a timestamped JSON report and a self-contained dark-theme HTML
report to `reports/`, and prints the best planetary imaging conditions found. The
report includes `forecast_hours`, `requested_forecast_hours` and
`skipped_hours_no_upper_air_data`. Under normal seamless-model operation,
all requested hours are complete and the skipped count is zero.

### `ireland-forecast`

The generalised, Ireland-wide equivalent of `wicklow-forecast`: run the
same UKV pipeline for any selected latitude, longitude and name within the
Ireland region (Republic of Ireland and Northern Ireland, plus a margin of
nearby coastal waters).

```
python -m meteoblue_seeing ireland-forecast \
  --latitude 53.0925 --longitude -7.9107 \
  --name "Birr, County Offaly, Ireland" \
  --hours 96 --output-directory reports
```

Coordinates are validated against a generous Ireland region bounding box
and `--hours` is validated to the range 1 to 120; invalid values are
rejected explicitly rather than silently accepted. The site elevation used
for the vertical profile is the UKV model-grid elevation returned by
Open-Meteo for the requested point, not a fixed constant, so different
locations use their own correct grid elevation.

### `serve`

Start a local HTTP server exposing a polished dark-theme browser UI: an
OpenStreetMap-tiled Leaflet map centred on and bounded to Ireland, click to
place a marker, a place search box backed by a server-side Open-Meteo
Geocoding API proxy filtered to Ireland, a Generate Forecast button, an
hourly forecast table with ascending and descending column sorting,
combined filters for light condition, maximum cloud, minimum seeing and
minimum imaging score, and a target-specific planetary imaging planner.
The planner uses a three-step flow: choose a target, compare the forecast
nights, then review the strongest session across those nights. Every
available night is selected by default, with checkbox controls for narrowing
the search and optional nightly start and end hours. It evaluates one-hour
and two-hour sessions, presents the top option and three alternatives, then
plots target elevation, seeing and cloud on separate labelled scales for the
best-ranked night. The top session is highlighted directly on the timeline.
Imaging cards include crescent and cloud
pictograms for at-a-glance cloud cover. Rise, meridian, set, culmination
altitude, magnitude, illumination and Moon phase remain available under the
collapsed all-target comparison. The seeing simulator and complete hourly
table are also collapsed by default so the recommendation remains the
primary decision surface.

Clicking or dragging the map marker fills the search field with the
selected `latitude, longitude`. The search field also accepts a coordinate
pair directly, for example `53.27, -9.06`.

```
python -m meteoblue_seeing serve
```

By default this binds only to `127.0.0.1:8765` (local machine only). Then
open `http://127.0.0.1:8765/` in a browser, or run
`Run-Ireland-Forecast.ps1` from the project root, which starts the server
attached to the current console (so closing the window or pressing
Ctrl+C stops it; it never launches a detached background process) and
opens your default browser automatically:

```
./Run-Ireland-Forecast.ps1
```

For the simplest Windows launch, double-click:

```
Open-Ireland-Forecast.cmd
```

The launcher waits until the local server returns HTTP 200 before opening
the browser. The server continues running after the launcher window closes,
so map clicks and location changes continue to work. When finished,
double-click:

```
Stop-Ireland-Forecast.cmd
```

## GitHub Pages frontend

The `docs` directory contains a static, project-page-safe frontend for
GitHub Pages. Build it from the application source with:

```powershell
python scripts\build_pages.py
```

Until a hosted Python API is available, the Pages build displays the map and
interface but blocks place search and forecast generation with a clear
configuration message.

After deploying the API, rebuild with its HTTPS origin:

```powershell
python scripts\build_pages.py `
  --api-base "https://your-forecast-api.example"
```

Then commit the regenerated `docs` directory and configure GitHub Pages to
publish from the `main` branch and `/docs` folder. The build uses relative
asset paths so it works below a project URL such as
`https://enkelly-pac.github.io/ireland-astro-seeing-forecast/`.

The server exposes two JSON API endpoints used by the browser UI:

```
GET /api/geocode?q=<search text>[&limit=8]
GET /api/forecast?lat=<latitude>&lon=<longitude>&name=<display name>&hours=96
```

Both endpoints validate their input explicitly (numeric, in-range
coordinates; whole-number hours from 1 to 120; a non-empty search string)
and return a JSON `{"error": "..."}` body with an HTTP 4xx status on
invalid input, rather than silently accepting bad values.

This site requires an active internet connection for three things: the
live UK Met Office forecast data, the Open-Meteo place search results,
and the OpenStreetMap map tiles. Map tiles are provided under the
OpenStreetMap copyright and attribution requirements; weather data
attribution is "Weather data by Open-Meteo.com and the UK Met Office."

#### Score semantics

Every hourly forecast entry carries separate scores on a 1 to 10 scale
where **10 is always best and 1 is always worst**:

- `seeing_score_1_10`: atmospheric seeing only, derived from the
  calculated FWHM arcseconds using an approximate Pickering-style
  conversion. Cloud cover is never folded into this score; it is reported
  and displayed separately.
- `imaging_score_1_10`: an explicitly **experimental** planetary imaging
  conditions score combining seeing and cloud without a darkness penalty.
  The browser's target-specific score additionally includes the selected
  Moon or planet's elevation and excludes full daylight.
- `observing_score_1_10`: retained in JSON for compatibility with earlier
  versions, but no longer drives the imaging-focused browser interface.

### `parse-html`

Extract table rows from a page you have saved locally (never fetched over
the network by this tool) using only `html.parser`.

```
python -m meteoblue_seeing parse-html data/sample_meteoblue_page.html --as-records
python -m meteoblue_seeing parse-html data/sample_meteoblue_page.html --table-index 1
```

### `calibrate`

Fit the INFERRED Cn2 and blend coefficients against a CSV of permitted
black box observations (see `data/sample_calibration.csv`), using a
deterministic, bounded coordinate-wise grid search.

```
python -m meteoblue_seeing calibrate data/sample_calibration.csv --output-config calibrated_config.json --passes 2
```

CSV columns: `case_id`, `site_elevation_m_asl`, `altitude_m_asl`,
`pressure_hpa`, `temperature_c`, `relative_humidity_pct`, `wind_u_ms`,
`wind_v_ms`, `cloud_cover_pct`, optional `wavelength_nm`, and
`observed_seeing1_arcsec` / `observed_seeing2_arcsec` / `observed_arcsec`
(only required once per case, on any one row).

## Running the tests

```
python -m unittest discover -s tests -v

```

## Output document

`forecast` produces a JSON document with, among other fields: independent
cloud cover bands (0 to 4 km, 4 to 8 km, 8 to 15 km ASL, never folded into
seeing), Model 1 and Model 2 Cn2 vertical integrals, Fried parameter and
arcsecond seeing per model, a 1 to 5 seeing index per model, a single
blended and bad-layer-penalised display arcsecond estimate and index, the
200 hPa jet stream speed and rating, the strongest qualifying bad layer
(bottom, top, potential temperature jump, mean gradient), the count of CAT
flagged interfaces, and a `meta.method_labels` block mapping every field to
its PUBLICLY DOCUMENTED / STANDARD PHYSICS / INFERRED-CALIBRATABLE
confidence label plus an `assumptions` list.

## UKV cloud combination

The preferred automated source is the Met Office UK Deterministic 2 km
dataset on AWS Open Data. It is based on UKV, is distributed as NetCDF,
contains low, medium, high and total cloud amount, and can be accessed
anonymously. The archive is free and unsupported, normally arrives about
3 to 6 hours after model run time, and is licensed under CC BY-SA 4.0.

```
https://registry.opendata.aws/met-office-uk-deterministic/
```

Install the optional NetCDF and projection dependencies:

```
pip install -e ".[ukv]"
```

Add `valid_time_utc` on an exact UTC hour to the seeing profile, then run:

```
python -m meteoblue_seeing combine-ukv-aws data/sample_input.json \
  --latitude 53.35 --longitude -6.26
```

The command finds the newest available UKV run containing that valid time,
downloads the four cloud files, projects the requested longitude and
latitude onto the UKV grid, extracts the nearest cell, and combines the
clouds with the unchanged atmospheric seeing result.

### Windy compatibility import

Windy displays UKV on its website and app, but as checked on 27 September
2026, UKV is not listed among the official Point Forecast API models.
This project therefore does not call an undocumented Windy endpoint.

```
https://api.windy.com/point-forecast/docs
```

```
https://community.windy.com/topic/24400/the-ukv-met-office-model-is-now-available-on-windy
```

Cloud values copied or exported from Windy can instead be supplied in CSV:

```
valid_time_utc,low_cloud_pct,mid_cloud_pct,high_cloud_pct,total_cloud_pct
2026-09-27T22:00:00Z,8,5,12,21
```

Run:

```
python -m meteoblue_seeing combine-ukv data/sample_input.json data/sample_windy_ukv_clouds.csv
```

For either source, the combined result preserves the original profile
cloud fields under `profile_cloud_bands`, places UKV values in
`cloud_bands`, records source provenance, and calculates a separate
observability score. It never changes Seeing Index 1 or Seeing Index 2.
UKV's low, medium and high cloud categories are retained under their own
names. They are not relabelled as meteoblue's 0 to 4, 4 to 8 and 8 to
15 km bands because those vertical definitions are not guaranteed to be
identical.

If total cloud is available it is used directly. Otherwise cloud
obstruction is estimated from independent layer overlap:

```
obstruction = 1 - (1 - low) * (1 - middle) * (1 - high)
```

The planetary imaging conditions score is explicitly
INFERRED/CALIBRATABLE:

```
score = seeing_quality * (0.2 + 0.8 * clear_sky_fraction)
```

## Licence and data use

This code is provided for research and educational reconstruction purposes.
It does not embed or redistribute any meteoblue data, forecasts, or
proprietary logic. If you calibrate this project against meteoblue (or any
other) website content, you are solely responsible for complying with that
website's terms of service and data licence; this project never performs
network scraping and the `parse-html` command only ever reads a file you
have already saved yourself.
