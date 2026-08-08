"""Tests for commit-data format parsers."""

from datetime import UTC, datetime

from vfc_datasets.commit_data import (
    files_changed_from_diff,
    from_git_show,
    from_unified_diff,
)

DIFF = (
    "diff --git a/src/app.c b/src/app.c\n"
    "index 1111111..2222222 100644\n"
    "--- a/src/app.c\n"
    "+++ b/src/app.c\n"
    "@@ -1,3 +1,3 @@\n"
    "-old\n"
    "+new\n"
)


class TestFilesChangedFromDiff:
    def test_extracts_paths(self):
        assert files_changed_from_diff(DIFF) == {"src/app.c"}

    def test_crlf_diff_does_not_leak_carriage_return(self):
        assert files_changed_from_diff(DIFF.replace("\n", "\r\n")) == {"src/app.c"}

    def test_multiple_files(self):
        diff = DIFF + DIFF.replace("src/app.c", "src/other.c")
        assert files_changed_from_diff(diff) == {"src/app.c", "src/other.c"}

    def test_quoted_path(self):
        diff = 'diff --git "a/src/a b.c" "b/src/a b.c"\n--- "a/src/a b.c"\n'
        assert files_changed_from_diff(diff) == {"src/a b.c"}

    def test_deleted_file_falls_back_to_old_path(self):
        diff = "diff --git a/gone.c b/dev/null\n--- a/gone.c\n+++ /dev/null\n"
        assert files_changed_from_diff(diff) == {"gone.c"}

    def test_non_string_input(self):
        assert files_changed_from_diff(None) == frozenset()
        assert files_changed_from_diff(123) == frozenset()


class TestFromUnifiedDiff:
    def test_keeps_diff_and_derives_files(self):
        data = from_unified_diff(DIFF)
        assert data.diff == DIFF
        assert data.files_changed == {"src/app.c"}
        assert data.message is None

    def test_blank_input_is_empty(self):
        assert from_unified_diff("   ").diff is None
        assert from_unified_diff(None).diff is None


class TestFromGitShow:
    def test_splits_message_and_diff(self):
        text = (
            "commit 1234567890abcdef1234567890abcdef12345678\n"
            "Author: A B <a@b.c>\n"
            "Date:   Fri Aug 4 15:26:15 2023 +0200\n"
            "\n"
            "    Fix the overflow\n"
            "    \n"
            "    Longer body explaining why.\n"
            "\n" + DIFF
        )
        data = from_git_show(text)

        assert data.message == "Fix the overflow\n\nLonger body explaining why."
        assert data.diff == DIFF
        assert data.files_changed == {"src/app.c"}
        # `git show` prints the author date, normalized to UTC from +0200.
        assert data.authored_at == datetime(2023, 8, 4, 13, 26, 15, tzinfo=UTC)
        assert data.committed_at is None

    def test_unparseable_date_is_dropped_not_guessed(self):
        text = (
            "commit 1234567890abcdef1234567890abcdef12345678\n"
            "Author: A B <a@b.c>\n"
            "Date:   not a date\n"
            "\n"
            "    Subject\n"
        )
        assert from_git_show(text).authored_at is None

    def test_merge_commit_header(self):
        text = (
            "commit 1234567890abcdef1234567890abcdef12345678\n"
            "Merge: aaaaaaa bbbbbbb\n"
            "Author: A B <a@b.c>\n"
            "Date:   Fri Aug 4 15:26:15 2023 +0200\n"
            "\n"
            "    Merge pull request #1\n"
            "\n" + DIFF
        )
        assert from_git_show(text).message == "Merge pull request #1"

    def test_indented_block_in_message_is_preserved(self):
        text = (
            "commit 1234567890abcdef1234567890abcdef12345678\n"
            "Author: A B <a@b.c>\n"
            "Date:   Fri Aug 4 15:26:15 2023 +0200\n"
            "\n"
            "    Subject\n"
            "\n"
            "        indented code\n"
            "\n" + DIFF
        )
        assert from_git_show(text).message == "Subject\n\n    indented code"

    def test_without_diff(self):
        text = (
            "commit 1234567890abcdef1234567890abcdef12345678\n"
            "Author: A B <a@b.c>\n"
            "Date:   Fri Aug 4 15:26:15 2023 +0200\n"
            "\n"
            "    Only a message\n"
        )
        data = from_git_show(text)

        assert data.message == "Only a message"
        assert data.diff is None
        assert data.files_changed == frozenset()

    def test_blank_input_is_empty(self):
        assert from_git_show("").message is None
        assert from_git_show(None).message is None
