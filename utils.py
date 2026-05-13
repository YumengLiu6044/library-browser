from bs4 import BeautifulSoup, Comment
from urllib3.util import parse_url


def clean_page(corpus: str) -> str:
	soup = BeautifulSoup(corpus, "html.parser")
	body = soup.body
	for tag in body([
		"script", "style", "code",
		"svg", "footer", "i", "button", "input"
	]):
		tag.decompose()

	# Remove comments
	comments = body.find_all(
		string=lambda text: isinstance(text, Comment)
	)

	for comment in comments:
		comment.extract()

	return "".join(str(body).split("\n"))


def resolve_href(url, href) -> str:
	href = href.strip()
	parsed = parse_url(url)

	resolved = href
	if href.startswith("/"):
		resolved = f"{parsed.scheme}://{parsed.hostname}{href}"

	return resolved
