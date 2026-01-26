"""Tests for C/C++ comment stripping functionality in add_no_comment module."""

import pytest

from dataset_entry import DatasetEntry
from transformations.enrichment.add_no_comment import (
    _strip_comments,
    add_commit_diff_no_comment,
)


class TestCppRealCommitIntegration:
    """Integration tests using real curl repository commits."""

    CURL_PROJECT_URL = "https://github.com/curl/curl"
    # This commit only touched comments (and one markdown doc THANKS)
    # https://github.com/curl/curl/pull/18803/commits/8900fed33ff99aeff6c5edff551213fc08e6acf0
    COMMENT_ONLY_COMMIT = "8900fed33ff99aeff6c5edff551213fc08e6acf0"

    @pytest.fixture
    def entry_with_diff(self):
        """Create entry and fetch original diff."""
        from transformations.enrichment.add_commit_data_local import (
            add_commit_information_local,
        )

        entry = DatasetEntry(
            project_url=self.CURL_PROJECT_URL,
            commit_id=self.COMMENT_ONLY_COMMIT,
            src_datasets={"test"},
        )
        entries = add_commit_information_local([entry])
        assert len(entries) == 1
        assert entries[0].commit_diff is not None
        return entries[0]

    @pytest.mark.integration
    @pytest.mark.slow
    def test_include_unsupported_true(self, entry_with_diff):
        """
        Test include_unsupported=True (default) includes unsupported files as-is.

        Files changed:
        - docs/THANKS (unsupported markdown)
        - lib/cf-socket.c, lib/curlx/inet_ntop.c, lib/if2ip.h, lib/md4.c,
          lib/md5.c, lib/sha256.c, lib/vtls/openssl.c (C files)
        """
        original_diff = entry_with_diff.commit_diff
        assert "THANKS" in original_diff

        result = add_commit_diff_no_comment([entry_with_diff], include_unsupported=True)

        assert len(result) == 1
        assert result[0].commit_diff_no_comment is not None

        # Should include the unsupported markdown file
        assert "THANKS" in result[0].commit_diff_no_comment

        # C file comments should be stripped - the diff should be smaller
        # (this commit mainly touched comments)
        assert len(result[0].commit_diff_no_comment) < len(original_diff)

    @pytest.mark.integration
    @pytest.mark.slow
    def test_include_unsupported_false(self, entry_with_diff):
        """Test include_unsupported=False skips unsupported files entirely."""
        # Reset the no_comment field for fresh test
        entry_with_diff.commit_diff_no_comment = None

        result = add_commit_diff_no_comment([entry_with_diff], include_unsupported=False)

        assert len(result) == 1
        assert result[0].commit_diff_no_comment is not None

        # Should NOT include the unsupported markdown file
        assert "THANKS" not in result[0].commit_diff_no_comment

        # Should still have the C files (but with comments stripped)
        assert "lib/" in result[0].commit_diff_no_comment or ".c" in result[0].commit_diff_no_comment


class TestEdgeCases:
    """Edge case tests for C/C++ comment handling."""

    def test_empty_file(self):
        """Test handling of empty C/C++ files."""
        result_c = _strip_comments("", "c")
        result_cpp = _strip_comments("", "cpp")
        assert result_c == ""
        assert result_cpp == ""

    def test_only_comments(self):
        """Test file containing only comments."""
        source = """// Comment 1
// Comment 2
/* Block comment */"""
        result = _strip_comments(source, "c")
        assert result is not None
        # Should be mostly empty (just newlines)
        assert "// Comment" not in result
        assert "/* Block comment */" not in result

    def test_mixed_whitespace(self):
        """Test handling of various whitespace with comments."""
        source = """int x = 1;
\t// Tab-indented comment
    // Space-indented comment
\t\t// Double-tab comment
int y = 2;"""
        result = _strip_comments(source, "c")
        assert result is not None

        # All comments should be removed regardless of indentation
        comments = ["// Tab-indented comment", "// Space-indented comment", "// Double-tab comment"]
        for comment in comments:
            assert comment not in result

        # Code should be preserved
        assert "int x = 1;" in result
        assert "int y = 2;" in result

    def test_url_in_comment(self):
        """Test that URLs in comments are also removed."""
        source = """// See: https://example.com/docs
int main() {
    return 0;
}"""
        result = _strip_comments(source, "c")
        assert result is not None
        assert "// See: https://example.com/docs" not in result
        assert "https://example.com" not in result

    def test_multi_line_block_comment(self):
        """Test multi-line block comment spanning many lines."""
        source = """/*
 * Copyright (c) 2024
 * All rights reserved.
 *
 * This is a long header comment
 * that spans multiple lines.
 */

int main() {
    return 0;
}"""
        result = _strip_comments(source, "c")
        assert result is not None
        assert "Copyright" not in result
        assert "All rights reserved" not in result
        assert "int main()" in result

    def test_complex_mixed_comments_and_strings(self):
        """Test complex case with comment-like content inside strings and real comments."""
        source = '''#include <stdio.h>

// This is a real comment that should be removed
const char* url = "https://example.com/path"; // inline comment
const char* not_comment = "// this looks like a comment but isn't";
const char* block_like = "/* also not a comment */";

/*
 * Multi-line comment with "quoted text"
 * and // nested comment-like syntax
 */
int main() {
    printf("Hello // world /* test */\\n"); // actual comment
    char* multi = "line1\\n"
                  "// still a string\\n"  // real comment here
                  "line3";
    /* comment with
       url: https://test.com
       inside */
    return 0; /* trailing */
}'''
        result = _strip_comments(source, "c")
        assert result is not None

        # Real comments should be removed
        assert "// This is a real comment" not in result
        assert "// inline comment" not in result
        assert "// actual comment" not in result
        assert "// real comment here" not in result
        assert "Multi-line comment" not in result
        assert "nested comment-like syntax" not in result
        assert "/* trailing */" not in result
        assert "url: https://test.com" not in result

        # String literals should be preserved (including comment-like content)
        assert '"https://example.com/path"' in result
        assert '"// this looks like a comment but isn\'t"' in result
        assert '"/* also not a comment */"' in result
        assert '"Hello // world /* test */\\n"' in result
        assert '"// still a string\\n"' in result

        # Code structure should be preserved
        assert "#include <stdio.h>" in result
        assert "const char* url" in result
        assert "const char* not_comment" in result
        assert "int main()" in result
        assert "printf(" in result
        assert "return 0;" in result
