from __future__ import annotations

# Canonical mapping from file extension to language name
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    # C
    ".c": "c",
    ".h": "c",
    # C++
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c++": "cpp",
    ".cp": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".hxx": "cpp",
    ".h++": "cpp",
    ".hp": "cpp",
    # Python
    ".py": "python",
    ".pyw": "python",
    ".pyx": "python",
    ".pyi": "python",
    # Java
    ".java": "java",
    # JavaScript
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    # TypeScript
    ".ts": "typescript",
    ".tsx": "typescript",
    # Go
    ".go": "go",
    # Rust
    ".rs": "rust",
}


def extensions_for(*languages: str) -> set[str]:
    """Return the set of file extensions for the given language names."""
    return {ext for ext, lang in EXTENSION_TO_LANGUAGE.items() if lang in languages}
