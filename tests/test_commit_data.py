"""Tests for the CommitData value object and the commit-data format parsers."""

from dataclasses import fields as dc_fields
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

from vfc_datasets.commit_data import (
    CommitData,
    files_changed_from_diff,
    from_git_show,
    from_unified_diff,
    normalize_commit_timestamp,
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


FULL = CommitData(
    message="m",
    diff="d",
    files_changed=frozenset({"a"}),
    authored_at=datetime(2024, 1, 1, tzinfo=UTC),
    committed_at=datetime(2024, 1, 2, tzinfo=UTC),
)

PLUS5 = timezone(timedelta(hours=5))


class TestDefaults:
    def test_everything_empty(self):
        data = CommitData()
        assert data.message is None
        assert data.diff is None
        assert data.files_changed == frozenset()
        assert data.authored_at is None
        assert data.committed_at is None


class TestTimestampNormalization:
    """`__post_init__` coerces both timestamps to tz-aware UTC."""

    def test_none_stays_none(self):
        assert CommitData(committed_at=None).committed_at is None

    def test_naive_datetime_gets_utc(self):
        data = CommitData(committed_at=datetime(2024, 1, 1, 12, 0, 0))
        assert data.committed_at is not None
        assert data.committed_at.tzinfo == UTC

    def test_non_utc_tz_converted_to_utc(self):
        data = CommitData(authored_at=datetime(2024, 1, 1, 15, 0, 0, tzinfo=PLUS5))
        assert data.authored_at is not None
        assert data.authored_at.tzinfo == UTC
        assert data.authored_at.hour == 10


class TestNormalizeCommitTimestamp:
    def test_none(self):
        assert normalize_commit_timestamp(None) is None

    def test_iso_string_parsed(self):
        result = normalize_commit_timestamp("2024-01-15T10:30:00+00:00")
        assert result is not None
        assert result.year == 2024
        assert result.tzinfo == UTC

    def test_naive_datetime_gets_utc(self):
        result = normalize_commit_timestamp(datetime(2024, 1, 1, 12, 0, 0))
        assert result is not None
        assert result.tzinfo == UTC

    def test_non_utc_tz_converted_to_utc(self):
        result = normalize_commit_timestamp(datetime(2024, 1, 1, 15, 0, 0, tzinfo=PLUS5))
        assert result is not None
        assert result.tzinfo == UTC
        assert result.hour == 10


class TestMerge:
    def test_merge_covers_all_fields(self):
        """Every CommitData field must be handled by CommitData.merge."""
        empty = CommitData()
        # Without this, a field added but left at its default would make the merges below vacuous.
        assert all(getattr(FULL, f.name) != getattr(empty, f.name) for f in dc_fields(CommitData))

        assert empty.merge(FULL) == FULL, "merge must fill every field from the other side"
        assert FULL.merge(empty) == FULL, "merge must keep every field already set"

    def test_values_already_set_win(self):
        other = CommitData(message="theirs", diff="theirs")
        assert CommitData(message="mine").merge(other).message == "mine"
        assert CommitData(message="mine").merge(other).diff == "theirs"


class TestIsComplete:
    def test_empty_is_incomplete(self):
        assert not CommitData().is_complete()

    def test_full_is_complete(self):
        assert FULL.is_complete()

    def test_any_single_field_missing_is_incomplete(self):
        """Exhaustive, so a field added later cannot silently drop out of the check."""
        default = CommitData()
        for f in dc_fields(CommitData):
            degraded = replace(FULL, **{f.name: getattr(default, f.name)})
            assert not degraded.is_complete(), f"missing {f.name} must not count as complete"


class TestRoundTrip:
    def test_to_dict_from_dict(self):
        assert CommitData.from_dict(FULL.to_dict()) == FULL

    def test_files_changed_serialized_sorted(self):
        assert CommitData(files_changed=frozenset({"b", "a"})).to_dict()["files_changed"] == [
            "a",
            "b",
        ]

    def test_timestamps_serialized_as_iso_z(self):
        assert FULL.to_dict()["authored_at"] == "2024-01-01T00:00:00Z"

    def test_from_dict_missing_input_is_empty(self):
        assert CommitData.from_dict(None) == CommitData()
        assert CommitData.from_dict({}) == CommitData()


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
