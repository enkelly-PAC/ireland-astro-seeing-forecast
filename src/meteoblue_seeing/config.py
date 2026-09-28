"""Configuration for the meteoblue style seeing reconstruction.

Every threshold below is labelled with its confidence tier:

  PUBLICLY DOCUMENTED  - stated in meteoblue help text or equivalent public
                          source, reproduced here as closely as the public
                          wording allows.
  STANDARD PHYSICS     - a constant from standard atmospheric optics or
                          thermodynamics (not meteoblue specific).
  INFERRED/CALIBRATABLE - a value we could not find publicly documented. It
                          is a reasonable placeholder that can be refined
                          with the ``calibrate`` CLI command against a
                          permitted black box dataset.

See README.md, section "Reverse engineering confidence table", for the full
picture and citations.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ModelCoefficients:
    """Coefficients for the two transparent empirical Cn2 models.

    All values in this class are INFERRED/CALIBRATABLE: the functional form
    is grounded in standard turbulence optics (see physics.py docstrings),
    but the scaling constants are not published anywhere we could find and
    must be tuned with real data using the ``calibrate`` command.
    """

    # Model 1: stability + wind shear/CAT + pressure/temperature refractivity.
    # model1_refractivity_weight also doubles as Model 1's overall scale
    # factor (it multiplies the whole stability x shear product), chosen so
    # that a moderately disturbed profile lands in a physically plausible
    # arcsecond range instead of the raw, un-scaled product of the
    # individual physical terms below.
    model1_theta_gradient_weight: float = 2.8e-3
    model1_shear_weight: float = 1.6e-4
    model1_cat_boost: float = 1.8
    model1_refractivity_weight: float = 5.6e-9

    # Model 2: density/refractivity fluctuations + humidity gradients.
    # model2_overall_scale is applied to the whole additive sum of terms,
    # for the same reason as model1_refractivity_weight above.
    model2_theta_gradient_weight: float = 1.6e-3
    model2_humidity_gradient_weight: float = 2.2e-3
    model2_density_weight: float = 1.3
    model2_cross_term_weight: float = 4.0e-4
    model2_overall_scale: float = 3.4e-9

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelCoefficients":
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)


@dataclass
class SeeingIndexThresholds:
    """Arcsecond boundaries mapping a seeing estimate to a 1 to 5 index.

    INFERRED/CALIBRATABLE. meteoblue does not publish the exact arcsecond
    cut points for its 1 (poor) to 5 (excellent) seeing index. The values
    below are a plausible, monotonically increasing scale inspired by
    common amateur/professional seeing classifications (for example the
    Pickering and Antoniadi scales) and are meant to be refined with the
    ``calibrate`` command.
    """

    excellent_max: float = 0.75   # index 5: seeing <= this value
    good_max: float = 1.25        # index 4
    average_max: float = 1.75     # index 3
    poor_max: float = 2.5         # index 2
    # anything above poor_max is index 1 (very poor)

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SeeingIndexThresholds":
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)


@dataclass
class SeeingScoreThresholds:
    """Approximate FWHM boundaries for an informal Pickering-style score."""

    score_10_max_exclusive: float = 0.5
    score_9_max_exclusive: float = 0.7
    score_8_max: float = 1.0
    score_7_max: float = 1.5
    score_6_max: float = 2.0
    score_5_max: float = 2.5
    score_4_max: float = 3.0
    score_3_max: float = 4.0
    score_2_max: float = 5.0

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SeeingScoreThresholds":
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)


@dataclass
class SeeingConfig:
    """Top level configuration bundle for a forecast run."""

    # --- PUBLICLY DOCUMENTED thresholds -----------------------------------
    # meteoblue detailed help: a "bad layer" needs an adjacent potential
    # temperature gradient of at least 0.5 K per 100 m (0.005 K/m).
    bad_layer_gradient_threshold_k_per_m: float = 0.005
    # The linked Meteosurf method also requires the layer to span at least
    # 2 K of potential temperature rise, top minus bottom.
    bad_layer_theta_jump_threshold_k: float = 2.0

    # Gradient Richardson number CAT flag threshold, standard aviation
    # meteorology convention, referenced by meteoblue documentation.
    ri_cat_threshold: float = 0.25

    # Jet stream sample level.
    jet_pressure_hpa: float = 200.0
    # meteoblue's own two public pages disagree: the detailed help article
    # states the jet is "too weak" below 5 m/s and "disruptive"/poor above
    # 35 m/s, while the shorter inline tooltip on the same site says poor
    # above 20 m/s. We default to the more detailed, and presumably more
    # carefully edited, 35 m/s figure and expose the 20 m/s figure as a
    # configurable alternative. See README "Jet stream threshold
    # discrepancy" section.
    jet_high_threshold_detailed_ms: float = 35.0
    jet_high_threshold_inline_ms: float = 20.0
    jet_low_threshold_ms: float = 5.0
    use_inline_jet_threshold: bool = False

    # Cloud layer bands, above sea level, independent of seeing.
    cloud_band_low_m: tuple[float, float] = (0.0, 4000.0)
    cloud_band_mid_m: tuple[float, float] = (4000.0, 8000.0)
    cloud_band_high_m: tuple[float, float] = (8000.0, 15000.0)

    # --- STANDARD PHYSICS constants ---------------------------------------
    gravity_m_s2: float = 9.80665
    r_specific_dry_air_j_kgk: float = 287.05
    c_p_dry_air_j_kgk: float = 1004.68
    reference_pressure_hpa: float = 1000.0
    wavelength_nm: float = 500.0
    # Minimum resolvable shear squared, used to avoid division by zero when
    # computing the gradient Richardson number for a perfectly uniform wind
    # layer (standard numerical safeguard, not a physical constant).
    min_shear_sq_s2: float = 1.0e-8

    # --- INFERRED/CALIBRATABLE ---------------------------------------------
    model_coefficients: ModelCoefficients = field(default_factory=ModelCoefficients)
    seeing_index_thresholds: SeeingIndexThresholds = field(
        default_factory=SeeingIndexThresholds
    )
    seeing_score_thresholds: SeeingScoreThresholds = field(
        default_factory=SeeingScoreThresholds
    )
    # Multiplier applied to the blended arcsecond estimate when a bad layer
    # is present, to reflect the additional degradation. INFERRED.
    bad_layer_penalty_factor: float = 1.15
    # Weights used to blend model 1 and model 2 arcsecond results into the
    # single "display" estimate. INFERRED.
    display_blend_weight_model1: float = 0.5
    display_blend_weight_model2: float = 0.5

    def jet_high_threshold_ms(self) -> float:
        if self.use_inline_jet_threshold:
            return self.jet_high_threshold_inline_ms
        return self.jet_high_threshold_detailed_ms

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["model_coefficients"] = self.model_coefficients.to_dict()
        data["seeing_index_thresholds"] = self.seeing_index_thresholds.to_dict()
        data["seeing_score_thresholds"] = self.seeing_score_thresholds.to_dict()
        # tuples become lists through asdict already; keep as-is for JSON.
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SeeingConfig":
        data = dict(data)
        mc = data.pop("model_coefficients", None)
        sit = data.pop("seeing_index_thresholds", None)
        sst = data.pop("seeing_score_thresholds", None)
        for band_key in ("cloud_band_low_m", "cloud_band_mid_m", "cloud_band_high_m"):
            if band_key in data and data[band_key] is not None:
                data[band_key] = tuple(data[band_key])
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        cfg = cls(**known)
        if mc:
            cfg.model_coefficients = ModelCoefficients.from_dict(mc)
        if sit:
            cfg.seeing_index_thresholds = SeeingIndexThresholds.from_dict(sit)
        if sst:
            cfg.seeing_score_thresholds = SeeingScoreThresholds.from_dict(sst)
        return cfg

    @classmethod
    def load(cls, path: str | Path) -> "SeeingConfig":
        with open(path, "r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    def save(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, sort_keys=True)
