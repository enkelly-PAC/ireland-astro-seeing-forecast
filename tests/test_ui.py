import unittest

from meteoblue_seeing.ui import load_index_html


class TestIrelandPickerUi(unittest.TestCase):
    def test_page_uses_short_title(self):
        content = load_index_html()
        self.assertIn("<title>Ireland Astro Seeing Forecast</title>", content)
        self.assertIn("<h1>Ireland Astro Seeing Forecast</h1>", content)

    def test_map_click_populates_coordinate_search(self):
        content = load_index_html()
        self.assertIn("function selectMapCoordinate", content)
        self.assertIn("searchInput.value = coordinateText(lat, lon)", content)
        self.assertIn("selectMapCoordinate(event.latlng.lat, event.latlng.lng)", content)

    def test_search_accepts_coordinate_pair(self):
        content = load_index_html()
        self.assertIn("var coordinateMatch = query.match", content)
        self.assertIn("Coordinates selected. Click Generate forecast.", content)

    def test_results_offer_an_obvious_route_back_to_forecast_setup(self):
        content = load_index_html()
        self.assertIn('id="change-forecast-button"', content)
        self.assertIn("Change forecast setup", content)
        self.assertIn('id="max-hours-button"', content)
        self.assertIn("Use maximum: 120", content)
        self.assertIn("function openForecastSetup()", content)
        self.assertIn("locationPanelEl.open = true", content)
        self.assertIn("hoursInput.value = hoursInput.max", content)

    def test_hourly_forecast_columns_are_sortable(self):
        content = load_index_html()
        self.assertEqual(content.count('class="sort-button"'), 11)
        self.assertIn('data-sort-key="local_time"', content)
        self.assertIn('data-sort-key="imaging_score"', content)
        self.assertIn("function sortedForecasts()", content)
        self.assertIn('tableSort.direction === "asc" ? "desc" : "asc"', content)

    def test_hourly_forecast_has_combined_filters(self):
        content = load_index_html()
        self.assertIn('id="filter-light"', content)
        self.assertIn('id="filter-max-cloud"', content)
        self.assertIn('id="filter-min-seeing"', content)
        self.assertIn('id="filter-min-imaging"', content)
        self.assertIn("function filteredForecasts()", content)
        self.assertIn('lightState.indexOf("night") !== -1', content)
        self.assertIn("No hourly forecasts match the selected filters.", content)
        self.assertIn('id="reset-filters"', content)

    def test_planet_panel_has_events_and_time_window(self):
        content = load_index_html()
        self.assertIn("<h2>Planetary imaging planner</h2>", content)
        self.assertIn('id="astro-date-options"', content)
        self.assertIn('id="astro-start-time"', content)
        self.assertIn('id="astro-end-time"', content)
        self.assertIn("function forecastsInAstroWindow", content)
        self.assertIn("function populateAstronomyDates()", content)
        self.assertIn("var availableDays = currentAstronomy.days.filter", content)
        self.assertIn(").length > 0;", content)
        self.assertIn("updateAvailableNights", content)
        self.assertIn("function selectedAstroDates()", content)
        self.assertIn("function forecastEntriesInSelectedAstroWindows()", content)
        self.assertIn("function renderAstronomy(selectedDate)", content)
        self.assertIn("culmination_altitude_degrees", content)
        self.assertIn("phase_name", content)
        self.assertIn('class="astro-grid"', content)
        self.assertIn("function planetVisibilityRating", content)
        self.assertIn("function planetImagePath", content)
        self.assertIn('?v=user-20260925', content)
        self.assertIn("class='body-image'", content)
        self.assertIn("class='altitude-track'", content)
        self.assertIn("selected imaging hour(s) above the horizon", content)
        self.assertIn("<summary>Compare all targets tonight</summary>", content)
        self.assertNotIn('class="astro-table"', content)

    def test_planner_uses_target_specific_imaging_sessions(self):
        content = load_index_html()
        self.assertIn('class="planner-panel"', content)
        self.assertIn("Choose what you want to image", content)
        self.assertIn("Compare the forecast nights", content)
        self.assertIn(
            "Review the best conditions across the selected nights",
            content,
        )
        self.assertIn(
            "The planner searches every selected night and ranks the strongest",
            content,
        )
        self.assertIn("All available nights are selected by default", content)
        self.assertIn('id="select-all-nights"', content)
        self.assertIn('id="clear-nights"', content)
        self.assertIn('id="imaging-target"', content)
        self.assertIn('<option value="moon" selected>Moon</option>', content)
        self.assertIn('id="primary-window"', content)
        self.assertIn("session across selected nights", content)
        self.assertNotIn('"Best available"', content)
        self.assertIn("function targetImagingScore", content)
        self.assertIn("function buildImagingSessions", content)
        self.assertIn("sessionWindows.push([entry])", content)
        self.assertIn("entries.slice(index, index + 2)", content)
        self.assertIn("function renderPrimarySession", content)
        self.assertIn("function renderAlternativeSessions", content)
        self.assertIn("position.altitude_degrees >= 10", content)
        self.assertIn("function seeingRating(score)", content)
        self.assertIn("class='seeing-rating'", content)
        self.assertIn("class='seeing-score'", content)
        self.assertIn("class='seeing-detail'", content)
        self.assertIn("seeingRating(item.scores.seeing_score_1_10)", content)
        self.assertIn("function cloudCoverVisual", content)
        self.assertIn("class='cloud-visual cloud-band-", content)
        self.assertIn("weather-cloud-front", content)
        self.assertIn("var scale = Math.min(1.08, 0.47 + cloud * 0.0061)", content)
        self.assertIn("cloud-band-overcast", content)
        self.assertIn("var overcastCloud = cloud >= 90", content)
        self.assertIn("cloudCoverVisual(session.averageCloud)", content)
        self.assertIn("window-card", content)
        self.assertIn("score-ring", content)
        self.assertIn("window-metrics", content)
        self.assertIn("--window-score", content)
        self.assertIn("--window-progress", content)
        self.assertIn("var recommendationLabel = score >= 4", content)
        self.assertIn("Poor conditions: strongest", content)
        self.assertIn(" alternative ", content)
        self.assertLess(
            content.index("<div class='window-date'>"),
            content.index("<div class='window-time'>"),
        )

    def test_planner_has_timeline_and_collapsed_supporting_sections(self):
        content = load_index_html()
        self.assertIn('id="imaging-timeline"', content)
        self.assertIn("function drawImagingTimeline", content)
        self.assertIn('id="timeline-title"', content)
        self.assertIn("Separate scale for each row", content)
        self.assertIn('label: "Elevation"', content)
        self.assertIn('label: "Seeing"', content)
        self.assertIn('label: "Cloud"', content)
        self.assertIn('unit: "10 is best"', content)
        self.assertIn('unit: "lower is better"', content)
        self.assertIn('var highlightLabel = "Top: " + formatSessionRange', content)
        self.assertIn("var right = width - 58", content)
        self.assertIn('id="compare-details"', content)
        self.assertIn('id="seeing-details"', content)
        self.assertIn("<summary>How the seeing score works</summary>", content)
        self.assertIn("<summary>View full hourly forecast</summary>", content)
        self.assertIn('id="location-panel"', content)
        self.assertIn("locationPanelEl.open = false", content)
        self.assertIn("seeingSimulatorInitialised", content)

    def test_seeing_simulator_follows_selected_imaging_target(self):
        content = load_index_html()
        self.assertIn("<summary>How the seeing score works</summary>", content)
        self.assertIn('id="seeing-target-image"', content)
        self.assertIn('id="seeing-target-name"', content)
        self.assertIn("function seeingImagePath(bodyKey)", content)
        self.assertIn("/assets/seeing-moon-clavius.webp?v=user-20221003", content)
        self.assertIn("seeingImageSize(imagingTargetInput.value)", content)
        self.assertIn("updateSeeingTargetPreview()", content)
        self.assertNotIn('id="seeing-body"', content)
        self.assertIn("function drawSeeingSample", content)
        self.assertIn("var seeingScores = [2, 4, 6, 8, 10]", content)
        self.assertIn("var seeingArcsecLabels", content)
        self.assertIn('2: "4.0 to 5.0 arcsec"', content)
        self.assertIn('10: "under 0.5 arcsec"', content)
        self.assertIn("Full arcsecond score scale", content)
        self.assertIn("<strong>1</strong><span>Over 5.0 arcsec</span>", content)
        self.assertIn("var turbulence = severity * severity", content)
        self.assertIn("var burstCycleMilliseconds = score === 8 ? 320 : 520", content)
        self.assertIn("var intermittentBurst = Math.pow(burstWave, 8)", content)
        self.assertIn("var effectiveTurbulence = score === 8", content)
        self.assertIn("if (score === 8)", content)
        self.assertIn("var stripCount = 10", content)
        self.assertIn("var rippleStrength = 0.15", content)
        self.assertIn("intermittentBurst * 0.45", content)
        self.assertIn("canvas._seeingBuffer", content)
        self.assertIn("var jitter = 0.35 + effectiveTurbulence * 8.5", content)
        self.assertIn("var blur = 0.20 + effectiveTurbulence * 4.0", content)
        self.assertIn("var wobbleDegrees = 0.12 + effectiveTurbulence * 2.2", content)
        self.assertIn("var cycleMilliseconds = 190 - turbulence * 135", content)
        self.assertIn("var copies = score <= 2", content)
        self.assertIn('2: "Very poor"', content)
        self.assertIn("qualitative", content)
        self.assertIn("same approximate Pickering-style", content)


if __name__ == "__main__":
    unittest.main()
