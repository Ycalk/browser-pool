from abc import ABC

import pytest
from browserpool.variant import (
    BrowserConfigurationError,
    BrowserVariant,
    CamoufoxBrowser,
    ChromiumBrowser,
)


def test_concrete_variants_registered_under_their_name() -> None:
    """__init_subclass__ registers each non-abstract variant in _variants."""
    assert BrowserVariant._variants["chromium"] is ChromiumBrowser  # type: ignore[reportPrivateUsage]
    assert BrowserVariant._variants["camoufox"] is CamoufoxBrowser  # type: ignore[reportPrivateUsage]


def test_abstract_subclass_not_registered() -> None:
    """A subclass that stays abstract is not added to the registry."""

    class _StillAbstract(BrowserVariant, ABC, name="abstract-should-not-register"):  # pyright: ignore[reportUnusedClass]
        pass

    assert "abstract-should-not-register" not in BrowserVariant._variants  # type: ignore[reportPrivateUsage]


def test_variants_lists_every_registered_variant() -> None:
    """variants() returns an info dict for every registered variant."""
    infos = {info["name"]: info for info in BrowserVariant.variants()}
    assert "chromium" in infos
    assert "camoufox" in infos
    chromium = infos["chromium"]
    assert chromium["image_name"] == ChromiumBrowser.image_name()
    assert chromium["image_tag"] == ChromiumBrowser.image_tag()


def test_get_variant_returns_instance_with_bound_fields() -> None:
    """get_variant builds an instance carrying name/network/labels."""
    labels = {"browserpool.managed": "true"}
    variant = BrowserVariant.get_variant(
        "chromium",
        container_name="cn",
        network_name="nn",
        labels=labels,
    )
    assert isinstance(variant, ChromiumBrowser)
    assert variant.name == "chromium"
    assert variant.container_config.name == "cn"


def test_get_variant_unknown_name_raises() -> None:
    """An unregistered name raises BrowserConfigurationError."""
    with pytest.raises(BrowserConfigurationError):
        BrowserVariant.get_variant(
            "no-such-variant",
            container_name="cn",
            network_name="nn",
            labels={},
        )
