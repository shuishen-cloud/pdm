# -*- coding: utf-8 -*-
"""pdev.doc 的测试。"""

from __future__ import annotations

import pytest

from pdev import (
    Actor,
    Cover,
    Generated,
    Manifest,
    Trigger,
    Version,
    VersionStatus,
    match_glob,
)


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "trigger,needs_new",
    [
        (Trigger.INTERFACE, True),
        (Trigger.DATA_MODEL, True),
        (Trigger.CORE_FLOW, True),
        (Trigger.INVARIANT, True),
        (Trigger.DETAIL, False),
        (Trigger.DOC_FIX, False),
    ],
)
def test_trigger_requires_new_version(trigger, needs_new):
    assert trigger.requires_new_version is needs_new


def test_doc_enum_values_are_strings():
    assert Trigger.INTERFACE == "interface-change"
    assert VersionStatus.CURRENT == "current"


# ---------------------------------------------------------------------------
# glob
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pattern,name,expected",
    [
        ("src/auth/**", "src/auth/login.go", True),
        ("src/auth/**", "src/auth/a/b/c.go", True),
        ("src/auth/**", "src/authx/login.go", False),
        ("**/*.go", "a/b/c.go", True),
        ("**/*.go", "c.go", True),
        ("*.go", "c.go", True),
        ("*.go", "a/c.go", False),
        ("./src/**", "src/a.go", True),
        ("", "a.go", False),
        ("src/*/x.go", "src/auth/x.go", True),
        ("src/*/x.go", "src/auth/sub/x.go", False),
    ],
)
def test_match_glob(pattern, name, expected):
    assert match_glob(pattern, name) is expected


@pytest.mark.parametrize(
    "path,expected",
    [
        ("src/auth/login.go", True),
        ("src/auth/deep/token.go", True),
        ("src/db/schema.go", True),
        ("src/db/other.go", False),
        ("README.md", True),
        ("docs/guide.md", False),  # *.md 不跨目录
        ("src/other/auth.go", False),
    ],
)
def test_cover_hits(path, expected):
    c = Cover(paths=["src/auth/**", "src/db/schema.go", "*.md"])
    assert c.hits(path) is expected


def test_cover_empty_never_hits():
    assert Cover().hits("anything") is False


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


def test_version_risky():
    assert sample_manifest().current_version().risky is True

    safe = Version(
        id="1",
        doc_origin=Generated.AI_FULL,
        reviewed_by=Actor("human:lwy"),
    )
    assert safe.risky is False

    unex = Version(
        id="1",
        doc_origin=Generated.HUMAN,
        reviewed_by=Actor("human:lwy"),
        explainability="no",
    )
    assert unex.risky is True


def test_version_current():
    assert Version(id="1", status=VersionStatus.CURRENT).current
    assert not Version(id="1", status=VersionStatus.SUPERSEDED).current


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def sample_manifest() -> Manifest:
    return Manifest(
        module="auth-flow",
        current="0003",
        versions=[
            Version(
                id="0001",
                status=VersionStatus.SUPERSEDED,
                trigger=Trigger.INTERFACE,
                doc_origin=Generated.HUMAN,
                to_commit="aaa",
                covers=Cover(paths=["src/auth/**"]),
            ),
            Version(
                id="0002",
                status=VersionStatus.SUPERSEDED,
                trigger=Trigger.DATA_MODEL,
                doc_origin=Generated.AI_FULL,
                reviewed_by=Actor("human:lwy"),
                to_commit="bbb",
                covers=Cover(paths=["src/auth/**"]),
            ),
            Version(
                id="0003",
                status=VersionStatus.CURRENT,
                trigger=Trigger.CORE_FLOW,
                doc_origin=Generated.AI_FULL,  # 未审 -> risky
                to_commit="HEAD",
                covers=Cover(paths=["src/auth/**", "src/db/**"]),
            ),
        ],
    )


def test_manifest_validate_ok():
    sample_manifest().validate()


def test_manifest_validate_rejects():
    m = sample_manifest()
    m.versions.append(Version(id="0003"))
    with pytest.raises(ValueError, match="duplicate"):
        m.validate()

    m = sample_manifest()
    m.current = "9999"
    with pytest.raises(ValueError, match="not in versions"):
        m.validate()

    m = sample_manifest()
    m.versions = []
    with pytest.raises(ValueError, match="no versions"):
        m.validate()

    m = sample_manifest()
    m.module = ""
    with pytest.raises(ValueError, match="module"):
        m.validate()

    m = sample_manifest()
    m.versions.append(Version(id=""))
    with pytest.raises(ValueError, match="empty id"):
        m.validate()


def test_manifest_current_version():
    assert sample_manifest().current_version().id == "0003"
    assert Manifest(module="x", current="0001").current_version() is None


def test_manifest_drifted():
    m = sample_manifest()
    assert m.drifted(["src/auth/login.go"]) is True
    assert m.drifted(["src/db/schema.go"]) is True
    assert m.drifted(["README.md", "src/payments/x.go"]) is False
    assert m.drifted([]) is False

    # 无 current 版本时永不漂移
    assert Manifest(module="x", current="nope").drifted(["src/auth/a.go"]) is False
