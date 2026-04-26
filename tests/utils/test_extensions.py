"""Tests for file extension mapping."""

from vfc_datasets.utils.extensions import EXTENSION_TO_LANGUAGE, extensions_for


class TestExtensionsFor:
    def test_single_language(self) -> None:
        exts = extensions_for("python")
        assert ".py" in exts
        assert ".pyw" in exts

    def test_multiple_languages(self) -> None:
        exts = extensions_for("c", "cpp")
        assert ".c" in exts
        assert ".cpp" in exts
        assert ".h" in exts

    def test_unknown_language_returns_empty(self) -> None:
        assert extensions_for("fortran") == set()

    def test_all_extensions_map_to_known_language(self) -> None:
        for ext, lang in EXTENSION_TO_LANGUAGE.items():
            assert ext in extensions_for(lang)
