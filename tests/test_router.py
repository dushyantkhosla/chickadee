import pytest

from src.models import ContentType
from src.router import route


class TestUnambiguousDomains:
    def test_youtube_com(self):
        assert route("https://www.youtube.com/watch?v=abc123") == ContentType.talk

    def test_youtu_be(self):
        assert route("https://youtu.be/abc123") == ContentType.talk

    def test_vimeo(self):
        assert route("https://vimeo.com/123456") == ContentType.talk

    def test_arxiv(self):
        assert route("https://arxiv.org/abs/2501.12345") == ContentType.paper

    def test_doi(self):
        assert route("https://doi.org/10.1234/example") == ContentType.paper

    def test_github(self):
        assert route("https://github.com/user/repo") == ContentType.repo

    def test_without_www(self):
        assert route("https://youtube.com/watch?v=abc") == ContentType.talk


class TestMultiTypeDomains:
    def test_anthropic_returns_none(self):
        assert route("https://anthropic.com/research/claude") is None

    def test_simonwillison_returns_none(self):
        assert route("https://simonwillison.net/2025/Jan/01/thing/") is None

    def test_substack_returns_none(self):
        assert route("https://substack.com/@user/post/123") is None


class TestUnknownDomains:
    def test_random_domain_returns_none(self):
        assert route("https://randomdomain.com/article") is None

    def test_medium_returns_none(self):
        assert route("https://medium.com/@user/story") is None
