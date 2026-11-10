"""Request the reviewer recorded on the single issue linked to a ready PR."""

import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen


LINK_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      closingIssuesReferences(first: 2) {
        nodes { number repository { nameWithOwner } }
        pageInfo { hasNextPage }
      }
    }
  }
}
"""

LOGIN = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"


def prose_lines(body):
    """Skip HTML comments and fenced examples before reading metadata lines."""
    fence = None
    for line in re.sub(r"<!--.*?(?:-->|$)", "", body or "", flags=re.S).splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        elif marker:
            fence = marker[1]
        else:
            yield line


def assigned_reviewer(body):
    entries = [m[1].strip() for line in prose_lines(body)
               if (m := re.fullmatch(r"Reviewer:[ \t]*(.+)", line, re.I))]
    if len(entries) != 1:
        return None
    match = re.fullmatch(rf"@?({LOGIN})", entries[0])
    if match is None:
        match = re.fullmatch(rf"[^()]+\(@?({LOGIN})\)", entries[0])
    return match[1] if match else None


def linked_issue(closing, body, repository):
    nodes = closing["nodes"]
    if closing["pageInfo"]["hasNextPage"] or any(
        node["repository"]["nameWithOwner"].lower() != repository.lower() for node in nodes
    ):
        return None
    numbers = {node["number"] for node in nodes}
    numbers.update(int(m[1]) for line in prose_lines(body)
                   if (m := re.fullmatch(r"Refs[ \t]+#([1-9][0-9]*)[ \t]*", line, re.I)))
    return next(iter(numbers)) if len(numbers) == 1 else None


def github(method, path, data=None):
    request = Request(
        f"{os.environ['GITHUB_API_URL'].rstrip('/')}/{path}", method=method,
        data=json.dumps(data).encode("utf-8") if data is not None else None,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"GitHub {method} {path} returned HTTP {error.code}.") from None


def request_review(api, repository, number):
    path = f"repos/{repository}/pulls/{number}"
    pr = api("GET", path)
    if (pr["state"] != "open" or pr["draft"] or pr["base"]["ref"] != "main"
            or (pr["head"]["repo"] or {}).get("full_name", "").lower() != repository.lower()):
        return "Skip: PR is not a ready same-repository PR to main."
    if pr["requested_reviewers"] or pr["requested_teams"]:
        return "Skip: a review is already requested."

    owner, repo = repository.split("/", 1)
    response = api("POST", "graphql", {
        "query": LINK_QUERY, "variables": {"owner": owner, "repo": repo, "number": number},
    })
    if response.get("errors"):
        raise RuntimeError("GitHub could not read the PR's linked issues.")
    closing = response["data"]["repository"]["pullRequest"]["closingIssuesReferences"]
    issue_number = linked_issue(closing, pr["body"], repository)
    if issue_number is None:
        return "Skip: exactly one same-repository Issue is required."

    issue = api("GET", f"repos/{repository}/issues/{issue_number}")
    author = pr["user"]["login"].lower()
    if "pull_request" in issue or issue["state"] != "open" or not any(
        assignee["login"].lower() == author for assignee in issue["assignees"]
    ):
        return "Skip: the PR author must be assigned to the open Issue."
    reviewer = assigned_reviewer(issue["body"])
    if reviewer is None or reviewer.lower() == author:
        return "Skip: the Issue needs one reviewer other than the PR author."

    page = 1
    while True:
        reviews = api("GET", f"{path}/reviews?per_page=100&page={page}")
        if any(r.get("submitted_at") and (r.get("user") or {}).get("login", "").lower() == reviewer.lower()
               for r in reviews):
            return "Skip: the designated reviewer already submitted a review."
        if len(reviews) < 100:
            break
        page += 1

    # Check the latest state again before sending a notification.
    current = api("GET", path)
    if (any(current[key] != pr[key] for key in ("state", "draft", "body"))
            or current["base"]["ref"] != pr["base"]["ref"] or current["head"]["sha"] != pr["head"]["sha"]):
        return "Skip: the PR changed while reading the assignment."
    if current["requested_reviewers"] or current["requested_teams"]:
        return "Skip: a review is already requested."
    api("POST", f"{path}/requested_reviewers", {"reviewers": [reviewer]})
    return f"Requested {reviewer} on PR #{number} from Issue #{issue_number}."


if __name__ == "__main__":
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    print(request_review(github, os.environ["GITHUB_REPOSITORY"], event["number"]))
