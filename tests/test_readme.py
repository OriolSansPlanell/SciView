"""The README is also the PyPI page, where relative paths do not resolve: every image and link must be a full URL."""
import re
from pathlib import Path

README = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")


def test_readme_uses_full_urls_for_pypi():
    targets = re.findall(r'(?:src|href)="([^"]+)"', README) + re.findall(r"\]\(([^)]+)\)", README)
    assert targets
    relative = [t for t in targets if not re.match(r"https?://|#|mailto:", t)]
    assert relative == [], relative


def test_readme_images_exist_in_the_repository():
    root = Path(__file__).resolve().parents[1]
    for url in re.findall(r'src="https://raw\.githubusercontent\.com/OriolSansPlanell/SciView/main/([^"]+)"', README):
        assert (root / url).exists(), url
