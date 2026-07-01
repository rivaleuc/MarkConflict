"""MarkConflict tests: verdict normalization/validation guards + full submit->check flow."""

A = "0xAAa0000000000000000000000000000000000001"
B = "0xBBb0000000000000000000000000000000000002"


def test_normalize_check_default(contract):
    n = contract.normalize_check
    d = n({})                                  # shim / empty payload -> conservative default
    assert d == {"conflict": False, "offending": "none", "reasoning": "no reasoning"}


def test_normalize_check_non_dict(contract):
    n = contract.normalize_check
    for bad in (None, "oops", 42, [1, 2], True):
        d = n(bad)
        assert d["conflict"] is False
        assert d["offending"] == "none"
        assert d["reasoning"] == "no reasoning"


def test_normalize_check_conflict_coercion(contract):
    n = contract.normalize_check
    # truthy encodings collapse to True
    assert n({"conflict": True, "offending": "ACME", "reasoning": "x"})["conflict"] is True
    assert n({"conflict": "true", "offending": "ACME", "reasoning": "x"})["conflict"] is True
    assert n({"conflict": "YES", "offending": "ACME", "reasoning": "x"})["conflict"] is True
    assert n({"conflict": 1, "offending": "ACME", "reasoning": "x"})["conflict"] is True
    # falsy encodings collapse to False
    assert n({"conflict": False, "offending": "ACME", "reasoning": "x"})["conflict"] is False
    assert n({"conflict": "no", "offending": "ACME", "reasoning": "x"})["conflict"] is False
    assert n({"conflict": 0, "offending": "ACME", "reasoning": "x"})["conflict"] is False
    assert n({"conflict": None, "offending": "ACME", "reasoning": "x"})["conflict"] is False
    # coerced value is always a strict bool, never the raw type
    assert isinstance(n({"conflict": "true", "offending": "A", "reasoning": "x"})["conflict"], bool)


def test_normalize_offending_non_str_to_none(contract):
    n = contract.normalize_check
    assert n({"conflict": True, "offending": 123, "reasoning": "x"})["offending"] == "none"
    assert n({"conflict": True, "offending": None, "reasoning": "x"})["offending"] == "none"
    assert n({"conflict": True, "offending": ["a"], "reasoning": "x"})["offending"] == "none"
    assert n({"conflict": True, "offending": "   ", "reasoning": "x"})["offending"] == "none"
    # a real string is preserved (trimmed)
    assert n({"conflict": True, "offending": "  ACME  ", "reasoning": "x"})["offending"] == "ACME"


def test_validate_check(contract):
    v = contract.validate_check
    assert v({"conflict": True, "offending": "ACME", "reasoning": "sounds alike"})
    assert v({"conflict": False, "offending": "none", "reasoning": "distinct"})
    assert not v({"conflict": "true", "offending": "ACME", "reasoning": "x"})   # not strict bool
    assert not v({"conflict": True, "offending": "", "reasoning": "x"})          # empty offending
    assert not v({"conflict": True, "offending": 5, "reasoning": "x"})           # non-str offending
    assert not v({"conflict": True, "offending": "ACME", "reasoning": "  "})     # empty reasoning
    assert not v("nope")                                                          # non-dict


def _new(contract):
    return contract, contract.MarkConflict()


def test_full_submit_check_flow(contract):
    mod, c = _new(contract)
    mod.gl.message.sender_address = A
    mid = c.submit_mark("Kwik-E-Mart", "35", ["Quick E Mart", "KwikMart", "QuickMart"])

    # freshly submitted -> open, not yet decided
    m = c.get_mark(mid)
    assert m["exists"] is True
    assert m["state"] == "open"
    assert m["submitter"] == A
    assert m["existing"] == ["Quick E Mart", "KwikMart", "QuickMart"]
    assert m["nice_class"] == "35"

    # run consensus check (shim's exec_prompt -> {} -> normalized default conflict False)
    out = c.check(mid)
    assert out["mark"] == mid
    assert isinstance(out["conflict"], bool)
    assert out["conflict"] is False           # conservative default under the shim

    m2 = c.get_mark(mid)
    assert m2["state"] == "checked"
    assert isinstance(m2["conflict"], bool)
    assert m2["offending"] == "none"
    assert m2["reasoning"] == "no reasoning"

    # cannot re-check an already-checked mark
    try:
        c.check(mid); assert False, "should not re-check"
    except Exception:
        pass

    st = c.stats()
    assert st["total_marks"] == 1
    assert st["checked"] == 1
    assert st["conflicts"] == 0               # default verdict was no-conflict
    mod.gl.message.sender_address = A


def test_guards(contract):
    mod, c = _new(contract)
    mod.gl.message.sender_address = A
    # missing proposed / class
    try:
        c.submit_mark("   ", "35", []); assert False, "empty proposed rejected"
    except Exception:
        pass
    try:
        c.submit_mark("Zap", "  ", []); assert False, "empty class rejected"
    except Exception:
        pass
    # existing must be a list
    try:
        c.submit_mark("Zap", "35", "notalist"); assert False, "existing must be list"
    except Exception:
        pass
    # unknown mark
    try:
        c.check("999"); assert False, "unknown mark rejected"
    except Exception:
        pass
    # empty existing list is allowed
    mid = c.submit_mark("Zaphod", "9", [])
    assert c.get_mark(mid)["existing"] == []
    out = c.check(mid)
    assert isinstance(out["conflict"], bool)

    # missing id view
    assert c.get_mark("nope") == {"exists": False}
    mod.gl.message.sender_address = A
