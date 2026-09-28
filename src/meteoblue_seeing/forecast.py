"""Top level forecast orchestration: wires validation, physics and models
together and produces the final JSON-serialisable result document.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import SeeingConfig
from .models import (
    combine_cn2_profiles,
    fried_parameter_m,
    integrate_cn2,
    seeing_arcsec,
    seeing_index,
)
from .physics import (
    build_layer_interfaces,
    compute_cloud_bands,
    find_strongest_bad_layer,
    sample_jet_stream,
)
from .validation import ForecastInput
from .ukv_clouds import format_utc_datetime


@dataclass
class ModelResult:
    cn2_integral_m_onethird: float
    r0_m: float
    seeing_arcsec: float
    seeing_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "cn2_integral_m_onethird": self.cn2_integral_m_onethird,
            "r0_m": None if self.r0_m == float("inf") else self.r0_m,
            "seeing_arcsec": self.seeing_arcsec,
            "seeing_index": self.seeing_index,
        }


def run_forecast(payload: dict, cfg: SeeingConfig | None = None) -> dict[str, Any]:
    """Validate ``payload`` and compute the full reconstructed forecast.

    Raises ``meteoblue_seeing.validation.InputValidationError`` on bad input.
    """

    cfg = cfg or SeeingConfig()
    forecast_input = ForecastInput.from_dict(payload)
    wavelength_nm = forecast_input.wavelength_nm or cfg.wavelength_nm

    levels = forecast_input.levels
    interfaces = build_layer_interfaces(levels, cfg)
    cn2_interfaces = combine_cn2_profiles(levels, interfaces, cfg)

    model1_integral = integrate_cn2(cn2_interfaces, "cn2_model1_m_negtwothirds")
    model2_integral = integrate_cn2(cn2_interfaces, "cn2_model2_m_negtwothirds")

    r0_1 = fried_parameter_m(model1_integral, wavelength_nm)
    r0_2 = fried_parameter_m(model2_integral, wavelength_nm)

    arcsec_1 = seeing_arcsec(r0_1, wavelength_nm)
    arcsec_2 = seeing_arcsec(r0_2, wavelength_nm)

    model1 = ModelResult(
        cn2_integral_m_onethird=model1_integral,
        r0_m=r0_1,
        seeing_arcsec=arcsec_1,
        seeing_index=seeing_index(arcsec_1, cfg),
    )
    model2 = ModelResult(
        cn2_integral_m_onethird=model2_integral,
        r0_m=r0_2,
        seeing_arcsec=arcsec_2,
        seeing_index=seeing_index(arcsec_2, cfg),
    )

    bad_layer = find_strongest_bad_layer(interfaces, cfg)
    cat_layer_count = sum(1 for interface in interfaces if interface.cat_flag)
    jet = sample_jet_stream(levels, cfg)
    cloud_bands = compute_cloud_bands(levels, cfg)

    # INFERRED/CALIBRATABLE: blend the two model arcsecond estimates using
    # configurable weights, then apply a bad-layer penalty multiplier. This
    # single "display" figure is our own construction, not a documented
    # meteoblue output, intended to mimic the single headline number shown
    # on the public page while remaining transparent about its derivation.
    weight_sum = (
        cfg.display_blend_weight_model1 + cfg.display_blend_weight_model2
    )
    if weight_sum <= 0:
        blended = 0.5 * (arcsec_1 + arcsec_2)
    else:
        blended = (
            cfg.display_blend_weight_model1 * arcsec_1
            + cfg.display_blend_weight_model2 * arcsec_2
        ) / weight_sum

    penalty_applied = bad_layer is not None
    display_arcsec = blended * cfg.bad_layer_penalty_factor if penalty_applied else blended
    display_index = seeing_index(display_arcsec, cfg)

    result: dict[str, Any] = {
        "meta": {
            "site_elevation_m_asl": forecast_input.site_elevation_m_asl,
            "location_name": forecast_input.location_name,
            "valid_time_utc": (
                format_utc_datetime(forecast_input.valid_time_utc)
                if forecast_input.valid_time_utc is not None
                else None
            ),
            "wavelength_nm": wavelength_nm,
            "level_count": len(levels),
            "method_labels": {
                "potential_temperature": "PUBLICLY_DOCUMENTED_AND_STANDARD_PHYSICS",
                "bad_layer_gradient_rule": "PUBLICLY_DOCUMENTED",
                "bad_layer_accumulation_rule": "PUBLICLY_DOCUMENTED",
                "richardson_number": "STANDARD_PHYSICS",
                "cat_flag": "PUBLICLY_DOCUMENTED_THRESHOLD",
                "jet_stream_sampling": "PUBLICLY_DOCUMENTED",
                "jet_stream_threshold": (
                    "PUBLICLY_DOCUMENTED_INLINE_20MS"
                    if cfg.use_inline_jet_threshold
                    else "PUBLICLY_DOCUMENTED_DETAILED_35MS"
                ),
                "cloud_bands": "PUBLICLY_DOCUMENTED",
                "cn2_model1": "STANDARD_PHYSICS_FORM_INFERRED_COEFFICIENTS",
                "cn2_model2": "STANDARD_PHYSICS_FORM_INFERRED_COEFFICIENTS",
                "fried_parameter": "STANDARD_PHYSICS",
                "seeing_arcsec": "STANDARD_PHYSICS",
                "seeing_index": "INFERRED_CALIBRATABLE",
                "display_arcsec_blend": "INFERRED_CALIBRATABLE",
            },
            "assumptions": [
                "Cn2 model coefficients and seeing index thresholds are "
                "inferred placeholders; use the calibrate command to refine "
                "them against permitted black box observation data.",
                "When several bad layers satisfy the published gradient and "
                "2 K potential-temperature difference criteria, this "
                "implementation reports the layer with the largest jump.",
                "Cloud cover bands are reported independently of the "
                "seeing indices, per the public documentation, and are not "
                "folded into any Cn2 or seeing computation.",
            ],
        },
        "cloud_bands": {
            "low_0_4km_pct": cloud_bands.low_0_4km_pct,
            "mid_4_8km_pct": cloud_bands.mid_4_8km_pct,
            "high_8_15km_pct": cloud_bands.high_8_15km_pct,
        },
        "jet_stream": (
            {
                "pressure_hpa": jet.pressure_hpa,
                "speed_ms": jet.speed_ms,
                "u_ms": jet.u_ms,
                "v_ms": jet.v_ms,
                "rating": jet.rating,
                "threshold_high_ms": jet.threshold_high_ms,
                "threshold_low_ms": jet.threshold_low_ms,
                "interpolated": jet.interpolated,
            }
            if jet is not None
            else None
        ),
        "bad_layer": (
            {
                "bottom_m": bad_layer.bottom_m,
                "top_m": bad_layer.top_m,
                "theta_jump_k": bad_layer.theta_jump_k,
                "mean_gradient_k_per_m": bad_layer.mean_gradient_k_per_m,
                "interface_count": bad_layer.interface_count,
            }
            if bad_layer is not None
            else None
        ),
        "cat_layer_count": cat_layer_count,
        "model1": model1.to_dict(),
        "model2": model2.to_dict(),
        "display": {
            "arcsec": display_arcsec,
            "index": display_index,
            "bad_layer_penalty_applied": penalty_applied,
        },
    }
    return result
