# PR #54 review fixes: 2026-11-12

Base reviewed: `42bb6c6a33793d24659536273bbe97b744afc727`. Scope: the two review findings from qikhcysa on 2026-11-12. The existing development-only benign/H0/F0/S0 scope and default `glm-5.3-flash` / official Zhipu endpoint are unchanged.

## Changes

- Validate the destination before choosing a key. Automatic `ZAI_API_KEY` fallback is restricted to HTTPS `open.bigmodel.cn`, with no explicit port or port 443. Other destinations require an explicit `AGENT_API_KEY` or a key supplied in the dialog. Exact host parsing rejects lookalikes and nonstandard ports for fallback.
- The masked, single-key dialog displays the destination host and explicit port. It never persists keys.
- Reject unsupported recovery scheduling during complete-batch preflight, before recording proposals or executing tools. A primary call followed by recovery now leaves no derived scheduling object.

## Dependency and identity checks

GitHub connector authenticated as `cynic004`, matching Issue #9's assignee and the confirmed roster. Issue #9 and roadmap #27 agree on #3, #6 and #8. All three remain CLOSED/completed; PRs #4, #51 and #46 are merged into main. Their merge commits are ancestors of the reviewed base. Work continued on the existing PR, in an isolated worktree.

## Executed verification

Windows 11, Python 3.13.5. Commands were run from the repository root unless stated otherwise:

| Command | Observed result |
| --- | --- |
| `python -m unittest discover -s tests -p "test_hosted*.py" -v` | 21 passed |
| `python -m unittest discover -s tests -v` | 97 passed |
| `python -m contracts.validate` | Both committed interface examples valid |
| From `member_a/`: `python verify.py` | 59 unit tests and six cross-process scenarios passed; zero paid API calls |
| `git diff --check` | Clean |

Added regressions cover official/default and explicit-443 key fallback, environment and CLI custom endpoints with only a Zhipu key, lookalike hosts, nonstandard ports, loopback, explicit custom credentials, the dialog's selected host and empty fallback, and recovery-only / primary-then-recovery / recovery-then-primary batches. Unsupported batches have zero tool calls, zero recorded proposals and zero derived local-tool objects. Existing successful hosted-loop tests and actual loopback HTTP byte/header checks continue to pass.

## Limits and review

No real hosted API call, paid experiment, new live-model result, or visual desktop-dialog inspection was performed for this revision. Dialog behavior was tested using the existing Tkinter test double. Earlier 2026-11-11 live artifacts remain historical evidence of their original source, not of this revision. No keys or private user data were used in tests. Codex implemented and verified these fixes; this is not an independent human approval. qikhcysa must review the latest commit before merge. No merge, review submission or Issue closure was performed.
