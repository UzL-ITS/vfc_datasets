import pytest

from vfc_datasets.utils.git.url import GitURL, normalize_commit_id


class TestGitURL:
    """Test GitURL parsing and conversion."""

    def test_github_https_url(self):
        url = "https://github.com/owner/repo"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.scheme == "https"
        assert git_url.host == "github.com"
        assert git_url.owner == "owner"
        assert git_url.repo == "repo"
        assert git_url.to_https_url() == "https://github.com/owner/repo"

    def test_github_url_with_commit(self):
        url = "https://github.com/owner/repo/commit/abc123def456"
        git_url = GitURL.parse(url)

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
    def test_github_url_variations(self, input_url, expected):
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    def test_gitlab_url(self):
        url = "https://gitlab.com/group/subgroup/project"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.host == "gitlab.com"
        assert git_url.owner == "group/subgroup"
        assert git_url.repo == "project"
        assert git_url.to_https_url() == "https://gitlab.com/group/subgroup/project"

    def test_gitlab_url_with_path(self):
        url = "https://gitlab.com/group/project/-/tree/main/src"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.owner == "group"
        assert git_url.repo == "project"
        assert git_url.to_https_url() == "https://gitlab.com/group/project"

    def test_gitlab_url_with_commit(self):
        url = "https://gitlab.com/group/project/-/commit/1234567890abcdef"
        git_url = GitURL.parse(url)

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
    def test_gitlab_url_variations(self, input_url, expected):
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    def test_bitbucket_url(self):
        url = "https://bitbucket.org/owner/repo"
        git_url = GitURL.parse(url)

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
    def test_bitbucket_url_variations(self, input_url, expected):
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
    def test_case_insensitive_host_normalization(self, input_url, expected):
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    def test_googlesource_url(self):
        url = "https://android.googlesource.com/platform/frameworks/base"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.host == "android.googlesource.com"
        assert git_url.repo == "platform/frameworks/base"
        assert git_url.to_https_url() == "https://android.googlesource.com/platform/frameworks/base"

    def test_googlesource_url_with_commit(self):
        url = "https://android.googlesource.com/platform/frameworks/base/+/abc123"
        git_url = GitURL.parse(url)

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
    def test_googlesource_url_variations(self, input_url, expected):
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    def test_git_protocol_url(self):
        url = "git://github.com/owner/repo.git"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.scheme == "https"  # Converted by default
        assert git_url.to_https_url() == "https://github.com/owner/repo"

    def test_ssh_url_format(self):
        url = "ssh://git@bitbucket.org/owner/repo.git"
        git_url = GitURL.parse(url)

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
    def test_ssh_url_variations(self, input_url, expected):
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    def test_cgit_style_url(self):
        url = "https://git.kernel.org/cgit/linux/kernel/git/torvalds/linux.git"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.repo == "linux/kernel/git/torvalds/linux"
        assert (
            git_url.to_https_url()
            == "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"
        )

    def test_kernel_org_pub_scm_url(self):
        url = "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux-stable.git"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.host == "git.kernel.org"
        assert git_url.repo == "linux/kernel/git/stable/linux-stable"
        assert (
            git_url.to_https_url()
            == "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux-stable.git"
        )

    def test_kernel_org_pub_scm_with_commit_path(self):
        url = "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux-stable.git/commit/"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.repo == "linux/kernel/git/stable/linux-stable"
        assert (
            git_url.to_https_url()
            == "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux-stable.git"
        )

    def test_kernel_org_pub_scm_with_commit_id(self):
        url = "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=abc123def456"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.repo == "linux/kernel/git/torvalds/linux"
        assert git_url.commit_id == "abc123def456"
        assert (
            git_url.to_https_url()
            == "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"
        )

    def test_kernel_org_gitweb_url(self):
        url = "https://git.kernel.org/?p=linux/kernel/git/torvalds/linux.git"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.host == "git.kernel.org"
        assert git_url.repo == "linux/kernel/git/torvalds/linux"
        assert (
            git_url.to_https_url()
            == "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"
        )

    def test_kernel_org_gitweb_url_with_params(self):
        url = (
            "https://git.kernel.org/?p=linux/kernel/git/torvalds/linux.git;a=commit;h=abc123def456"
        )
        git_url = GitURL.parse(url)

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
            # gitweb-style URLs
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
    def test_kernel_org_url_variations(self, input_url, expected):
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    def test_url_with_www_prefix(self):
        url = "https://www.github.com/owner/repo"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.host == "github.com"  # www removed
        assert git_url.to_https_url() == "https://github.com/owner/repo"

    def test_url_with_trailing_git(self):
        url = "https://github.com/owner/repo.git"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.repo == "repo"  # .git removed
        assert git_url.to_https_url() == "https://github.com/owner/repo"

    @pytest.mark.parametrize(
        "input_url",
        [
            "",
            None,
            "not-a-url",
            "ftp://example.com/repo",
            "https://",
            "git@",
        ],
    )
    def test_invalid_urls(self, input_url):
        assert GitURL.parse(input_url) is None

    @pytest.mark.parametrize(
        "input_url",
        [
            "https://github.com",
            "https://github.com/",
        ],
    )
    def test_incomplete_urls(self, input_url):
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.owner is None
        assert git_url.repo is None

    def test_github_lowercase_conversion(self):
        url = "https://github.com/Owner/REPO"
        git_url = GitURL.parse(url)
        assert git_url is not None

        # Original case is preserved in the GitURL object
        assert git_url.owner == "Owner"
        assert git_url.repo == "REPO"
        # But lowercased in the output URL
        assert git_url.to_https_url() == "https://github.com/owner/repo"

    def test_generic_git_hosting(self):
        url = "https://git.example.com/project/repo/commit/abc123"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.host == "git.example.com"
        assert git_url.commit_id == "abc123"

    def test_gitweb_style_url(self):
        url = "https://git.example.com/?p=project.git;a=commit;h=abc123"
        git_url = GitURL.parse(url)

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
    def test_gitweb_url_variations(self, input_url, expected):
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    def test_savannah_cgit_url(self):
        url = "https://git.savannah.gnu.org/cgit/bash.git"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.host == "git.savannah.gnu.org"
        assert git_url.repo == "bash"
        assert git_url.to_https_url() == "https://git.savannah.gnu.org/git/bash.git"

    def test_savannah_gitweb_url(self):
        url = "https://git.savannah.gnu.org/gitweb/?p=bash.git"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.repo == "bash"
        assert git_url.to_https_url() == "https://git.savannah.gnu.org/git/bash.git"

    def test_savannah_git_url(self):
        url = "https://git.savannah.gnu.org/git/bash.git"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.repo == "bash"
        assert git_url.to_https_url() == "https://git.savannah.gnu.org/git/bash.git"

    def test_savannah_cgit_with_commit(self):
        url = "https://git.savannah.gnu.org/cgit/bash.git/commit/?id=abc123def456"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.repo == "bash"
        assert git_url.to_https_url() == "https://git.savannah.gnu.org/git/bash.git"

    def test_savannah_nested_repo(self):
        url = "https://git.savannah.gnu.org/cgit/freetype/freetype2.git"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.repo == "freetype/freetype2"
        assert git_url.to_https_url() == "https://git.savannah.gnu.org/git/freetype/freetype2.git"

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
    def test_savannah_url_variations(self, input_url, expected):
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected

    def test_generic_browse_prefix_url(self):
        url = "https://git.example.com/browse/repo"
        git_url = GitURL.parse(url)

        assert git_url is not None
        assert git_url.to_https_url() == "https://git.example.com/browse/repo"

    @pytest.mark.parametrize(
        "input_url,expected",
        [
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
    def test_self_hosted_git_urls(self, input_url, expected):
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
    def test_edge_cases(self, input_url, expected):
        git_url = GitURL.parse(input_url)
        assert git_url is not None
        assert git_url.to_https_url() == expected


class TestNormalizeCommitId:
    """Test normalize_commit_id function."""

    def test_github_url(self):
        url = "https://github.com/owner/repo/commit/1234567890abcdef"
        assert normalize_commit_id(url) == "1234567890abcdef"

    def test_gitlab_url(self):
        url = "https://gitlab.com/group/project/-/commit/abcdef123456"
        assert normalize_commit_id(url) == "abcdef123456"

    def test_googlesource_url(self):
        url = "https://android.googlesource.com/platform/frameworks/base/+/abc123/file.java"
        assert normalize_commit_id(url) == "abc123"

    def test_no_commit_in_url(self):
        assert normalize_commit_id("https://github.com/owner/repo") is None

    def test_short_commit(self):
        url = "https://github.com/owner/repo/commit/abc12"
        assert normalize_commit_id(url) == "abc12"

    def test_full_commit(self):
        full_hash = "1234567890abcdef1234567890abcdef12345678"
        url = f"https://github.com/owner/repo/commit/{full_hash}"
        assert normalize_commit_id(url) == full_hash

    def test_invalid_input(self):
        assert normalize_commit_id(None) is None
        assert normalize_commit_id("") is None
        assert normalize_commit_id("abc") is None  # too short
