"""Exercise the reviewer workflow against simulated GitHub responses."""

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "request_issue_review.py"
SPEC = importlib.util.spec_from_file_location("request_issue_review", SCRIPT)
workflow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow)

REPO = "team/project"
PR_PATH = f"repos/{REPO}/pulls/51"


class GitHub:
    def __init__(self):
        self.pr = {
            "state": "open", "draft": False, "base": {"ref": "main"},
            "head": {"repo": {"full_name": REPO}, "sha": "latest"},
            "user": {"login": "fixture-owner"}, "requested_reviewers": [], "requested_teams": [],
            "body": "Closes #6. Update the fixtures.\n\nReviewer: @wrong-user",
        }
        self.issue = {
            "state": "open", "assignees": [{"login": "Fixture-Owner"}],
            "body": "Reviewer: XIA Liyuan (Sherlyn-Xia)",
        }
        self.links = [{"number": 6, "repository": {"nameWithOwner": REPO}}]
        self.reviews = []
        self.notifications = []

    def __call__(self, method, path, data=None):
        if (method, path) == ("GET", PR_PATH):
            return deepcopy(self.pr)
        if (method, path) == ("POST", "graphql"):
            assert data["variables"] == {"owner": "team", "repo": "project", "number": 51}
            return {"data": {"repository": {"pullRequest": {"closingIssuesReferences": {
                "nodes": deepcopy(self.links), "pageInfo": {"hasNextPage": False},
            }}}}}
        if (method, path) == ("GET", f"repos/{REPO}/issues/6"):
            return deepcopy(self.issue)
        if (method, path) == ("GET", f"{PR_PATH}/reviews?per_page=100&page=1"):
            return deepcopy(self.reviews)
        if (method, path) == ("POST", f"{PR_PATH}/requested_reviewers"):
            self.notifications.extend(data["reviewers"])
            self.pr["requested_reviewers"] = [{"login": user} for user in data["reviewers"]]
            return deepcopy(self.pr)
        raise AssertionError(f"Unexpected API request: {method} {path}")

    def run(self):
        return workflow.request_review(self, REPO, 51)


class RequestReviewTests(unittest.TestCase):
    def test_uses_issue_reviewer_for_a_native_link_with_inline_text(self):
        github = GitHub()
        self.assertIn("from Issue #6", github.run())
        self.assertEqual(github.notifications, ["Sherlyn-Xia"])

    def test_draft_waits_and_ready_events_are_idempotent(self):
        github = GitHub()
        github.pr["draft"] = True
        self.assertIn("not a ready", github.run())
        self.assertEqual(github.notifications, [])
        github.pr["draft"] = False
        github.run()
        self.assertIn("already requested", github.run())
        self.assertEqual(github.notifications, ["Sherlyn-Xia"])

    def test_partial_reference_ignores_examples(self):
        github = GitHub()
        github.links = []
        github.pr["body"] = "Refs #6\n\n```text\nRefs #14\n```\n<!--\nRefs #8\n-->"
        github.issue["body"] = "Reviewer: @Sherlyn-Xia\n\n~~~\nReviewer: wrong-user\n~~~"
        github.run()
        self.assertEqual(github.notifications, ["Sherlyn-Xia"])

    def test_ambiguous_external_and_missing_links_do_not_notify(self):
        for links, body in [
            ([{"number": 6, "repository": {"nameWithOwner": "external/project"}}], ""),
            ([], ""),
            (GitHub().links, "Refs #14"),
        ]:
            with self.subTest(links=links, body=body):
                github = GitHub()
                github.links, github.pr["body"] = links, body
                self.assertIn("exactly one", github.run())
                self.assertEqual(github.notifications, [])

    def test_mismatched_owner_self_review_and_duplicate_metadata_do_not_notify(self):
        for patch in (
            {"assignees": [{"login": "someone-else"}]},
            {"body": "Reviewer: fixture-owner"},
            {"body": "Reviewer: user-one\nReviewer: user-two"},
        ):
            with self.subTest(patch=patch):
                github = GitHub()
                github.issue.update(patch)
                self.assertTrue(github.run().startswith("Skip:"))
                self.assertEqual(github.notifications, [])

    def test_manual_and_previously_completed_requests_are_preserved(self):
        github = GitHub()
        github.pr["requested_reviewers"] = [{"login": "manual-reviewer"}]
        self.assertIn("already requested", github.run())
        self.assertEqual(github.pr["requested_reviewers"], [{"login": "manual-reviewer"}])
        github.pr["requested_reviewers"] = []
        github.reviews = [{"user": {"login": "sherlyn-xia"}, "submitted_at": "2026-11-10T00:00:00Z"}]
        self.assertIn("already submitted", github.run())
        self.assertEqual(github.notifications, [])


if __name__ == "__main__":
    unittest.main()
