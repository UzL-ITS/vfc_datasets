import pytest

from vfc_datasets.utils.git.url import GitURL, normalize_commit_id


class TestGitURL:
    """Test GitURL parsing and conversion."""

    def test_github_https_url(self) -> None:
        git_url = GitURL.parse("https://github.com/owner/repo")

        assert git_url is not None
        assert git_url.scheme == "https"
        assert git_url.host == "github.com"
        assert git_url.owner == "owner"
        assert git_url.repo == "repo"
        assert git_url.to_https_url() == "https://github.com/owner/repo"

    def test_github_url_with_commit(self) -> None:
        git_url = GitURL.parse("https://github.com/owner/repo/commit/abc123def456")

        assert git_url is not None
        assert git_url.owner == "owner"
        assert git_url.repo == "repo"
        assert git_url.commit_id == "abc123def456"
        assert git_url.to_https_url() == "https://github.com/owner/repo"

    @pytest.mark.parametrize(
        "input_url,expected",
        [
            ("https://github.com/owner/repo", "https://github.com/owner/repo"),
            ("https://github.com/owner/repo.git", "https://github.com/owner/repo"),
            ("https://github.com/owner/repo/", "https://github.com/owner/repo"),
            ("https://github.com/owner/repo/commit/abc123", "https://github.com/owner/repo"),
            ("https://github.com/owner/repo/tree/main", "https://github.com/owner/repo"),
            ("https://github.com/owner/repo/blob/main/file.txt", "https://github.com/owner/repo"),
            ("https://github.com/owner/repo/pull/123", "https://github.com/owner/repo"),
            ("https://github.com/owner/repo/issues/456", "https://github.com/owner/repo"),
            ("https://www.github.com/owner/repo", "https://github.com/owner/repo"),
            ("http://github.com/owner/repo", "https://github.com/owner/repo"),
        ],
    )
    def test_github_url_variations(self, input_url: str, expected: str) -> None:
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    def test_gitlab_url(self) -> None:
        git_url = GitURL.parse("https://gitlab.com/group/subgroup/project")

        assert git_url is not None
        assert git_url.host == "gitlab.com"
        assert git_url.owner == "group/subgroup"
        assert git_url.repo == "project"
        assert git_url.to_https_url() == "https://gitlab.com/group/subgroup/project"

    def test_gitlab_url_with_commit(self) -> None:
        git_url = GitURL.parse("https://gitlab.com/group/project/-/commit/1234567890abcdef")

        assert git_url is not None
        assert git_url.owner == "group"
        assert git_url.repo == "project"
        assert git_url.commit_id == "1234567890abcdef"

    @pytest.mark.parametrize(
        "input_url,expected",
        [
            ("https://gitlab.com/owner/repo", "https://gitlab.com/owner/repo"),
            ("https://gitlab.com/owner/repo.git", "https://gitlab.com/owner/repo"),
            ("https://gitlab.com/owner/repo/-/commit/abc123", "https://gitlab.com/owner/repo"),
            ("https://gitlab.com/owner/repo/-/tree/main", "https://gitlab.com/owner/repo"),
            (
                "https://gitlab.com/group/subgroup/project",
                "https://gitlab.com/group/subgroup/project",
            ),
            (
                "https://gitlab.com/group/subgroup/project/-/blob/main/file.txt",
                "https://gitlab.com/group/subgroup/project",
            ),
            ("https://gitlab.com/owner/repo/-/merge_requests/123", "https://gitlab.com/owner/repo"),
            ("https://gitlab.example.com/owner/repo", "https://gitlab.example.com/owner/repo"),
        ],
    )
    def test_gitlab_url_variations(self, input_url: str, expected: str) -> None:
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    def test_bitbucket_url(self) -> None:
        git_url = GitURL.parse("https://bitbucket.org/owner/repo")

        assert git_url is not None
        assert git_url.host == "bitbucket.org"
        assert git_url.owner == "owner"
        assert git_url.repo == "repo"
        assert git_url.to_https_url() == "https://bitbucket.org/owner/repo"

    @pytest.mark.parametrize(
        "input_url,expected",
        [
            ("https://bitbucket.org/owner/repo", "https://bitbucket.org/owner/repo"),
            ("https://bitbucket.org/owner/repo.git", "https://bitbucket.org/owner/repo"),
            ("https://bitbucket.org/owner/repo/commits/abc123", "https://bitbucket.org/owner/repo"),
            ("https://bitbucket.org/owner/repo/src/main/", "https://bitbucket.org/owner/repo"),
        ],
    )
    def test_bitbucket_url_variations(self, input_url: str, expected: str) -> None:
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    @pytest.mark.parametrize(
        "input_url,expected",
        [
            ("https://GitHub.com/Foo/Bar", "https://github.com/foo/bar"),
            ("https://GitLab.com/Foo/Bar", "https://gitlab.com/Foo/Bar"),
            ("https://gitlab.freedesktop.org/DRM/Misc", "https://gitlab.freedesktop.org/DRM/Misc"),
            ("https://BitBucket.org/Foo/Bar", "https://bitbucket.org/Foo/Bar"),
            ("https://bitbucket.example.com/Foo/Bar", "https://bitbucket.example.com/Foo/Bar"),
        ],
    )
    def test_case_insensitive_host_normalization(self, input_url: str, expected: str) -> None:
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    def test_googlesource_url(self) -> None:
        git_url = GitURL.parse("https://android.googlesource.com/platform/frameworks/base")

        assert git_url is not None
        assert git_url.host == "android.googlesource.com"
        assert git_url.repo == "platform/frameworks/base"
        assert git_url.to_https_url() == "https://android.googlesource.com/platform/frameworks/base"

    def test_googlesource_url_with_commit(self) -> None:
        git_url = GitURL.parse("https://android.googlesource.com/platform/frameworks/base/+/abc123")

        assert git_url is not None
        assert git_url.repo == "platform/frameworks/base"
        assert git_url.commit_id == "abc123"

    @pytest.mark.parametrize(
        "input_url,expected",
        [
            (
                "https://android.googlesource.com/platform/frameworks/base",
                "https://android.googlesource.com/platform/frameworks/base",
            ),
            (
                "https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main",
                "https://android.googlesource.com/platform/frameworks/base",
            ),
            (
                "https://chromium.googlesource.com/chromium/src/+/main/docs/README.md",
                "https://chromium.googlesource.com/chromium/src",
            ),
        ],
    )
    def test_googlesource_url_variations(self, input_url: str, expected: str) -> None:
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    def test_git_protocol_url(self) -> None:
        git_url = GitURL.parse("git://github.com/owner/repo.git")

        assert git_url is not None
        assert git_url.scheme == "https"  # Converted by default
        assert git_url.to_https_url() == "https://github.com/owner/repo"

    def test_ssh_url_format(self) -> None:
        git_url = GitURL.parse("ssh://git@bitbucket.org/owner/repo.git")

        assert git_url is not None
        assert git_url.scheme == "https"  # Converted by default
        assert git_url.host == "bitbucket.org"
        assert git_url.to_https_url() == "https://bitbucket.org/owner/repo"

    @pytest.mark.parametrize(
        "input_url,expected",
        [
            ("git@github.com:owner/repo.git", "https://github.com/owner/repo"),
            ("git@github.com:owner/repo", "https://github.com/owner/repo"),
            ("git@github.com:OWNER/REPO", "https://github.com/owner/repo"),
            ("git@gitlab.com:owner/repo.git", "https://gitlab.com/owner/repo"),
            ("git@bitbucket.org:owner/repo.git", "https://bitbucket.org/owner/repo"),
            ("ssh://git@github.com/owner/repo.git", "https://github.com/owner/repo"),
            ("ssh://git@github.com/OWNER/REPO.git", "https://github.com/owner/repo"),
            ("ssh://git@gitlab.com/owner/repo", "https://gitlab.com/owner/repo"),
        ],
    )
    def test_ssh_url_variations(self, input_url: str, expected: str) -> None:
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    def test_cgit_style_url(self) -> None:
        git_url = GitURL.parse("https://git.kernel.org/cgit/linux/kernel/git/torvalds/linux.git")

        assert git_url is not None
        assert git_url.repo == "linux/kernel/git/torvalds/linux"
        assert (
            git_url.to_https_url()
            == "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"
        )

    def test_kernel_org_pub_scm_url(self) -> None:
        git_url = GitURL.parse(
            "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux-stable.git"
        )

        assert git_url is not None
        assert git_url.host == "git.kernel.org"
        assert git_url.repo == "linux/kernel/git/stable/linux-stable"

    def test_kernel_org_pub_scm_with_commit_id(self) -> None:
        git_url = GitURL.parse(
            "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=abc123def456"
        )

        assert git_url is not None
        assert git_url.repo == "linux/kernel/git/torvalds/linux"
        assert git_url.commit_id == "abc123def456"

    def test_kernel_org_gitweb_url_with_params(self) -> None:
        git_url = GitURL.parse(
            "https://git.kernel.org/?p=linux/kernel/git/torvalds/linux.git;a=commit;h=abc123def456"
        )

        assert git_url is not None
        assert git_url.repo == "linux/kernel/git/torvalds/linux"
        assert git_url.commit_id == "abc123def456"

    @pytest.mark.parametrize(
        "input_url,expected",
        [
            (
                "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git",
                "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git",
            ),
            (
                "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux-stable.git/commit/",
                "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux-stable.git",
            ),
            (
                "https://git.kernel.org/pub/scm/git/git.git",
                "https://git.kernel.org/pub/scm/git/git.git",
            ),
            (
                "https://git.kernel.org/?p=linux/kernel/git/torvalds/linux.git",
                "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git",
            ),
            (
                "https://git.kernel.org/?p=linux/kernel/git/stable/linux-stable.git",
                "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux-stable.git",
            ),
        ],
    )
    def test_kernel_org_url_variations(self, input_url: str, expected: str) -> None:
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    @pytest.mark.parametrize(
        "input_url",
        [
            "",
            "not-a-url",
            "ftp://example.com/repo",
            "https://",
            "git@",
        ],
    )
    def test_invalid_urls(self, input_url: str) -> None:
        assert GitURL.parse(input_url) is None

    def test_none_url_returns_none(self) -> None:
        assert GitURL.parse(None) is None  # pyright: ignore[reportArgumentType]

    @pytest.mark.parametrize(
        "input_url",
        [
            "https://github.com",
            "https://github.com/",
        ],
    )
    def test_incomplete_urls(self, input_url: str) -> None:
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.owner is None
        assert git_url.repo is None

    def test_github_lowercase_conversion(self) -> None:
        git_url = GitURL.parse("https://github.com/Owner/REPO")
        assert git_url is not None

        # Original case is preserved in the GitURL object
        assert git_url.owner == "Owner"
        assert git_url.repo == "REPO"
        # But lowercased in the output URL
        assert git_url.to_https_url() == "https://github.com/owner/repo"

    def test_generic_git_hosting(self) -> None:
        git_url = GitURL.parse("https://git.example.com/project/repo/commit/abc123")

        assert git_url is not None
        assert git_url.host == "git.example.com"
        assert git_url.commit_id == "abc123"

    def test_gitweb_style_url(self) -> None:
        git_url = GitURL.parse("https://git.example.com/?p=project.git;a=commit;h=abc123")

        assert git_url is not None
        assert git_url.repo == "project"

    @pytest.mark.parametrize(
        "input_url,expected",
        [
            ("https://git.company.com/?p=project.git", "https://git.company.com/?p=project.git"),
            (
                "https://git.company.com/gitweb/?p=project.git;a=summary",
                "https://git.company.com/?p=project.git",
            ),
        ],
    )
    def test_gitweb_url_variations(self, input_url: str, expected: str) -> None:
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    def test_savannah_cgit_url(self) -> None:
        git_url = GitURL.parse("https://git.savannah.gnu.org/cgit/bash.git")

        assert git_url is not None
        assert git_url.host == "git.savannah.gnu.org"
        assert git_url.repo == "bash"

    @pytest.mark.parametrize(
        "input_url,expected",
        [
            # cgit URLs -> clone URLs
            (
                "https://git.savannah.gnu.org/cgit/bash.git",
                "https://git.savannah.gnu.org/git/bash.git",
            ),
            (
                "https://git.savannah.gnu.org/cgit/emacs.git",
                "https://git.savannah.gnu.org/git/emacs.git",
            ),
            (
                "https://git.savannah.gnu.org/cgit/bash.git/commit",
                "https://git.savannah.gnu.org/git/bash.git",
            ),
            # gitweb URLs -> clone URLs
            (
                "https://git.savannah.gnu.org/?p=gnash.git",
                "https://git.savannah.gnu.org/git/gnash.git",
            ),
            (
                "https://git.savannah.gnu.org/gitweb/?p=bash.git",
                "https://git.savannah.gnu.org/git/bash.git",
            ),
            (
                "https://git.savannah.gnu.org/gitweb/?p=bash.git;a=summary",
                "https://git.savannah.gnu.org/git/bash.git",
            ),
            # direct git URLs (already correct)
            (
                "https://git.savannah.gnu.org/git/bash.git",
                "https://git.savannah.gnu.org/git/bash.git",
            ),
            # nested repos
            (
                "https://git.savannah.gnu.org/cgit/freetype/freetype2.git",
                "https://git.savannah.gnu.org/git/freetype/freetype2.git",
            ),
            # nongnu variant
            (
                "https://git.savannah.nongnu.org/cgit/freetype/freetype2.git",
                "https://git.savannah.nongnu.org/git/freetype/freetype2.git",
            ),
        ],
    )
    def test_savannah_url_variations(self, input_url: str, expected: str) -> None:
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    @pytest.mark.parametrize(
        "input_url,expected",
        [
            ("https://git.example.com/browse/repo", "https://git.example.com/browse/repo"),
            ("https://git.company.com/project.git", "https://git.company.com/project"),
            ("https://git.company.com/team/project", "https://git.company.com/team/project"),
            ("https://git.company.com/team/project.git", "https://git.company.com/team/project"),
            ("https://git.company.com/cgit/project.git", "https://git.company.com/cgit/project"),
            (
                "https://git.company.com/team/project/commit/abc123",
                "https://git.company.com/team/project",
            ),
            ("https://git.example.com/repo/tree/main", "https://git.example.com/repo"),
        ],
    )
    def test_self_hosted_git_urls(self, input_url: str, expected: str) -> None:
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    @pytest.mark.parametrize(
        "input_url,expected",
        [
            ("https://github.com/owner/repo-with-dash", "https://github.com/owner/repo-with-dash"),
            (
                "https://github.com/owner/repo_with_underscore",
                "https://github.com/owner/repo_with_underscore",
            ),
            (
                "https://github.com/owner/repo.name.with.dots",
                "https://github.com/owner/repo.name.with.dots",
            ),
            ("https://github.com/OWNER/REPO", "https://github.com/owner/repo"),
        ],
    )
    def test_edge_cases(self, input_url: str, expected: str) -> None:
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected


class TestNormalizeCommitId:
    """Test normalize_commit_id function."""

    def test_github_url(self) -> None:
        url = "https://github.com/owner/repo/commit/1234567890abcdef"
        assert normalize_commit_id(url) == "1234567890abcdef"

    def test_gitlab_url(self) -> None:
        url = "https://gitlab.com/group/project/-/commit/abcdef123456"
        assert normalize_commit_id(url) == "abcdef123456"

    def test_googlesource_url(self) -> None:
        url = "https://android.googlesource.com/platform/frameworks/base/+/abc123/file.java"
        assert normalize_commit_id(url) == "abc123"

    def test_no_commit_in_url(self) -> None:
        assert normalize_commit_id("https://github.com/owner/repo") is None

    def test_short_commit(self) -> None:
        url = "https://github.com/owner/repo/commit/abc12"
        assert normalize_commit_id(url) == "abc12"

    def test_full_commit(self) -> None:
        full_hash = "1234567890abcdef1234567890abcdef12345678"
        url = f"https://github.com/owner/repo/commit/{full_hash}"
        assert normalize_commit_id(url) == full_hash

    def test_invalid_input(self) -> None:
        assert normalize_commit_id(None) is None
        assert normalize_commit_id("") is None
        assert normalize_commit_id("abc") is None  # too short
