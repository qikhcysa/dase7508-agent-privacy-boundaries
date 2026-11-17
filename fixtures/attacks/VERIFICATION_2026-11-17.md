# Issue 17 verification, 2026-11-17

Base: main at 021f20d69be9dbe3aa60f2785f32c4c8d496463a (PR 59 merged; issue 16 CLOSED). Authenticated GitHub account: jinzhan857-sketch. Issue 17 owner: JIN Zhan; designated independent reviewer: JIANG Hanyu (unicjiang777). Roadmap 27 prerequisite table agrees on issue 16; its progress checkbox was stale when checked.

Git CLI authentication was unavailable. The authorized GitHub connector supplied the current main snapshot. Local tree SHA 3387cced67e77487d0b93205f4198b492adb7600 and signed commit object SHA were independently matched to GitHub before the task branch was established. The previous codex/issue13 ref was preserved.

Environment: Windows, Python 3.12.14, jsonschema 4.26.0. The previous .venv launcher referred to a removed runtime. A separate local .venv17 was created with the current bundled Python and dependencies installed using:
```powershell
.venv17/Scripts/python.exe -m pip install -r requirements-contracts.txt
.venv17/Scripts/python.exe -m unittest tests.test_matched_attacks tests.test_benign_fixtures -v
.venv17/Scripts/python.exe -m contracts.validate
.venv17/Scripts/python.exe -m unittest discover -s tests -v
git diff --check
```

Observed results:
* Focused suite: 8 tests passed, 0.175 seconds. All 12 pairs load and differ in paragraph two only. Original fields other than attack_paragraph match baseline hashes. Both scheduler modes match existing answers for all twelve.
* Negative subcases: identical-to-benign, empty, two paragraphs, single line break and carriage return replacements all rejected.
* Criteria coverage: exactly three cases per family, all twelve unique IDs, all target paths resolve to nonempty private synthetic values. B07 deliberately targets contacts because its calendar is empty.
* Contract examples: VALID bundle for attacked-h1.json and benign-h0.json.
* Full suite: 168 tests passed, 16.413 seconds. The H1 error reported in the upstream PR did not reproduce in this Windows environment.
* git diff --check: passed.

The initial test invocation without installed jsonschema failed at import; installing the declared dependencies in .venv17 resolved it. No production source was modified to accommodate the environment.

AI executed the implementation and checks. These checks establish dataset structure and regression behavior, not model attack success. No paid or real-model calls were made. No cases were selected using model outcomes. No outcome grader for issue 34 was implemented. Human owner inspection and independent review of the latest PR commit remain pending.
