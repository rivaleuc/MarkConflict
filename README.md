# MarkConflict

> Checks whether a proposed trademark conflicts with existing marks by validator consensus.

![GenLayer](https://img.shields.io/badge/GenLayer-Bradbury-6C46FF)
![chainId](https://img.shields.io/badge/chainId-4221-informational)
![contract](https://img.shields.io/badge/contract-Python%20GenVM-3776AB)
![tests](https://img.shields.io/badge/tests-7%2F7%20passing-brightgreen)
![license](https://img.shields.io/badge/license-MIT-blue)

MarkConflict is a contract-only GenLayer intelligent contract. A submitter proposes a
new trademark, the Nice class it would register under, and the list of existing marks
already living in that class. The contract then asks GenLayer's validators to
independently decide whether the proposed mark is *confusingly similar* to any existing
one — and only accepts the answer when the validators **agree on the yes/no verdict**.

## Why GenLayer is essential

Trademark conflict screening is not a string match. Two marks collide when an ordinary
consumer would confuse them, which turns on **phonetic** similarity ("Kwik-E-Mart" vs.
"Quick E Mart" sound identical) and **semantic** similarity ("Mountain Summit" vs. "Peak
Crest" mean the same thing) — *within the same Nice class*. That judgement is inherently
nondeterministic natural-language reasoning: it needs an LLM, and a single LLM's answer is
neither trustworthy nor verifiable on-chain.

A deterministic EVM contract cannot make this call at all — there is no opcode for "do these
sound alike?" and no way for other nodes to agree on a free-form model output. GenLayer solves
exactly this: every validator runs the reasoning independently, and the network reaches
**consensus on the decisive field** (`conflict`) before the result is written to state. The
LLM does the judging; the validators make the judgement *trustworthy*.

## Workflow

| Method | What happens |
| --- | --- |
| `submit_mark(proposed, nice_class, existing)` | Stores the proposed mark, its Nice class, and the existing marks to screen against. State `open`. Returns the mark id. |
| `check(mark_id)` | Runs the consensus judgement. Every validator decides `conflict` (bool) from phonetic/semantic similarity within the class; the network agrees on that boolean, then state becomes `checked`. Returns `{mark, conflict, offending}`. |
| `get_mark(mark_id)` | Returns the full record (`exists: False` if unknown). |
| `stats()` | Returns `{total_marks, checked, conflicts}`. |

## Correctness check

The decisive field is **`conflict` (bool)** — does the proposed mark collide with an existing
one? `check` wraps a local `do_check()` in
`gl.eq_principle.prompt_comparative(do_check, principle="The boolean 'conflict' must be identical
across validators; the offending mark named and the reasoning wording may differ.")`.

This is comparative equivalence on the **decision**, not on the JSON shape. Validators may name
different "closest" marks or word their reasoning differently, but the network only finalizes a
verdict when they **agree on the boolean collision call**. If one validator's model returned a
WRONG `conflict` value, it would diverge from the others on the exact field that matters and the
result would fail equivalence — so a single hallucinated yes/no cannot be written to chain. The
module-level `normalize_check` clamps any malformed payload to the conservative default
`{"conflict": False, "offending": "none", "reasoning": "no reasoning"}` (it never raises), and
`validate_check` enforces the strict-bool / non-empty-string invariants.

## Architecture

Contract-only — **no frontend**, no `app/` directory.

```
MarkConflict/
├── contracts/
│   └── mark_conflict.py     # the GenLayer intelligent contract (class MarkConflict)
└── tests/
    ├── conftest.py          # in-memory GenLayer shim (mocks exec_prompt + prompt_comparative)
    └── test_contract.py     # unit + full-flow integration tests
```

## Tests

```
/tmp/glvenv/bin/python -m pytest tests -q
```

All 7 tests pass: `normalize_check`/`validate_check` on good and adversarial inputs (non-dict,
`conflict` coercion, non-string `offending` → `none`), plus a full `submit_mark → check` flow
asserting the state transition to `checked` and that the finalized `conflict` is a strict bool.

## Deploy

The contract address is `0x4685EF1Bc775b53c356c8732f956eE79b31415B2` until deployed. Copy `.env.example` to `.env`, fill in
`ACCOUNT_PRIVATE_KEY`, then:

```
genlayer deploy --contract contracts/mark_conflict.py
```

After deployment, set `CONTRACT_ADDRESS` in `.env` (currently `0x4685EF1Bc775b53c356c8732f956eE79b31415B2`) to the returned
address.
