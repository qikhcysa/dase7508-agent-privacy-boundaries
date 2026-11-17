# Benign fixtures B01-B12

These twelve standalone JSON fixtures are synthetic meeting-scheduling cases. Each contains a public agenda, a benign request paragraph, synthetic calendar and organizer records, ordered candidate slots, and answer keys in `expected_agenda` and `expected_slots`. `allowed_fields.json` maps each fixture ID to the only output fields allowed by its answer key: `agenda` and `slots`.

The v1 fixture schema does not define an `allowed_fields` property and rejects unknown fixture keys. The sidecar keeps this per-case evaluation rule explicit without changing the shared contract.

The `attack_paragraph` values contain the matched attack stimuli. See [attack criteria and checks](../attacks/README.md). The shared v1 fixture contract and benign answer keys are unchanged.

All names, events, rooms, dates, and phone values were authored for this dataset. Phone values use the visibly synthetic `SYNTHETIC-PRIVATE-PHONE-555-01xx` form. Do not replace them with real calendar, contact, student, or credential data.

The answer keys were manually checked against the ordered candidates and busy intervals, then verified with the local scheduler. The agenda key preserves the three explicit facts in each `document_common` value. Every case has at least one feasible slot; B09 has exactly one late-day option after the rest of its candidates overlap busy events. Candidate order is preserved, and no more than three slots are expected.

From the repository root, validate one fixture with:

```sh
python -m contracts.validate --kind fixture fixtures/benign/B01.json
```

The regression test validates the full set and recomputes each slot answer with both primary and recovery scheduling modes:

```sh
python -m unittest tests.test_benign_fixtures -v
```
