# -*- coding: utf-8 -*-
"""feat_core 的纯函数测试。

**不 import textual**，毫秒级完成，进默认 CI。
用真的 ``Feat`` 对象（纯数据类，不落盘），避免假对象与真对象行为不一致。
"""

from __future__ import annotations

import time

from pdev.feat import Feat  # noqa: E402
from pdev.tui_new_to_fix import core, feat_core  # noqa: E402

_T0 = time.perf_counter()


def _feat(api=("run() -> int",), logs=("启动日志",), slug="demo") -> Feat:
    """构造一个内存中的 Feat（不落盘）。"""
    return Feat(slug=slug, title="演示", api=list(api),
                logs=list(logs))


# --- review_rows ------------------------------------------------------------


def test_review_rows_shape():
    rows = feat_core.review_rows(_feat(api=("a()", "b()"), logs=()))
    assert len(rows) == 2
    key, label, reviewed, tested = rows[0]
    assert key == "api:0"
    assert label == "a()"
    assert reviewed is False and tested is False


def test_review_rows_includes_all_field_kinds():
    """api / logs 等各字段都成为可审项（顺序与 review_items 一致）。"""
    rows = feat_core.review_rows(_feat(api=("a()",), logs=("L",)))
    assert [r[0] for r in rows] == ["api:0", "logs:0"]


def test_review_rows_reflects_state():
    f = _feat()
    f.set_reviewed("api:0", True, by="human:lwy")
    f.set_tested("api:0", True, command="pytest -q", status="passed")
    _key, _label, reviewed, tested = feat_core.review_rows(f)[0]
    assert reviewed is True and tested is True


def test_review_rows_empty_feat():
    """没有任何规格字段的 feat → 空列表，不抛异常。"""
    assert feat_core.review_rows(Feat(slug="empty", title="空")) == []


def test_review_rows_survives_broken_feat():
    """对象没有 review_items() 时也不能抛（app 层会传各种东西）。"""

    class Broken:
        pass

    assert feat_core.review_rows(Broken()) == []


# --- plan_toggle ------------------------------------------------------------


def test_plan_toggle_review_field():
    """首次切换 = 置 True。"""
    plan = feat_core.plan_toggle(_feat(), "api:0", "review")
    assert plan == {"reviewed": True}


def test_plan_toggle_test_field():
    plan = feat_core.plan_toggle(_feat(), "api:0", "test")
    assert plan == {"tested": True}


def test_plan_toggle_is_a_toggle():
    """已勾选 → 再切一次变成 False。"""
    f = _feat()
    f.set_reviewed("api:0", True, by="human:lwy")
    assert feat_core.plan_toggle(f, "api:0", "review") == {"reviewed": False}


def test_plan_toggle_rejects_bad_field():
    for field in ("", "title", "REVIEW", None):
        assert feat_core.plan_toggle(_feat(), "api:0", field) is None


def test_plan_toggle_rejects_unknown_key():
    for key in ("", "api:99", "not-a-key", None):
        assert feat_core.plan_toggle(_feat(), key, "review") is None


def test_plan_toggle_only_touches_one_field():
    """切 [审] 不得顺带改 [测]。"""
    f = _feat()
    f.set_tested("api:0", True, command="x", status="passed")
    plan = feat_core.plan_toggle(f, "api:0", "review")
    assert plan == {"reviewed": True}
    assert "tested" not in plan


# --- feat_line --------------------------------------------------------------


def test_feat_line_parts():
    marker, slug, tail = feat_core.feat_line(_feat())
    assert marker == "● "
    assert slug == "demo"
    assert "draft" in tail and "审 0/2" in tail


def test_feat_line_truncates_long_slug():
    """限宽时 slug 被截断并加省略号（保证列表单行）。"""
    f = Feat(slug="a-very-long-slug-for-testing", title="x", api=["a()"])
    marker, slug, tail = feat_core.feat_line(f, width=20)
    assert slug.endswith("…")
    # 总显示宽度不得超过列表宽度
    assert core.display_width(marker + slug + tail) <= 20


def test_feat_line_unlimited_width_keeps_full_slug():
    long_slug = "tui-new-to-fix-and-feat-review-super-long-slug"
    f = Feat(slug=long_slug, title="x", api=["a()"])
    marker, slug, tail = feat_core.feat_line(f, width=0)
    assert slug == long_slug


def test_feat_line_text_matches_parts():
    f = _feat()
    assert feat_core.feat_line_text(f) == "".join(feat_core.feat_line(f))


def test_feat_line_survives_broken_feat():
    """feat 缺字段/方法时不能抛（面板会传各种东西）。"""
    class Broken:
        slug = "broken"

    marker, slug, tail = feat_core.feat_line(Broken())
    assert marker and slug == "broken"


# --- plan_comment -----------------------------------------------------------


def test_plan_comment_normalizes():
    assert feat_core.plan_comment("为什么这么定") == "为什么这么定"


def test_plan_comment_empty_means_clear():
    """None / 非 str / 全空白 → 空串（表示清除），与 CLI 的 --clear 一致。"""
    for value in (None, "", "   ", "\n\t ", 123, [], {}):
        assert feat_core.plan_comment(value) == "", repr(value)


def test_plan_comment_keeps_newlines():
    """多行评论必须保留内部换行（这是用 TextArea 的原因）。"""
    text = "第一行\n第二行"
    assert feat_core.plan_comment(text) == text


def test_plan_comment_strips_outer_whitespace_only():
    assert feat_core.plan_comment("  a\nb  ") == "a\nb"


# --- comment_header ---------------------------------------------------------


def test_comment_header_has_item_details():
    """编辑框顶部要能看到正在编辑的条目：feat / 条目 / 内容 / 状态。"""
    f = _feat()
    f.set_reviewed("api:0", True, by="human:lwy")
    head = dict(feat_core.comment_header(f, "api:0"))
    assert head["feat"] == "demo"
    assert head["条目"] == "api:0"
    assert head["内容"] == "run() -> int"       # 条目详细信息
    assert "■" in head["状态"]                  # [审] 已勾
    assert head["状态"].count("□") == 1          # [测] 未勾


def test_comment_header_shows_untested_state():
    head = dict(feat_core.comment_header(_feat(), "api:0"))
    assert head["状态"].count("□") == 2


def test_comment_header_unknown_key_keeps_context():
    """key 不在可审项里也要能显上下文（不报错，不编造内容）。"""
    head = dict(feat_core.comment_header(_feat(), "nope:9"))
    assert head["feat"] == "demo"
    assert head["条目"] == "nope:9"
    assert "内容" not in head


def test_comment_header_survives_broken_feat():
    class Broken:
        slug = "b"

    head = dict(feat_core.comment_header(Broken(), "api:0"))
    assert head["feat"] == "b"


# --- detail_lines（详情渲染，纯函数）------------------------------------

_MARK = {True: "■", False: "□"}


def _plain(lines) -> list:
    """行模型 → 纯文本行（便于断言）。"""
    return ["".join(v for v, _s in line) for line in lines]


def test_detail_lines_no_feat():
    assert _plain(feat_core.detail_lines(None, [], 0, _MARK)) == \
        ["（无 feat，用 pdm feat new 创建）"]


def test_detail_lines_no_rows():
    f = Feat(slug="demo", title="演示")
    out = _plain(feat_core.detail_lines(f, [], 0, _MARK))
    assert out[0] == "demo"
    assert out[1] == "演示"
    assert "（无可审项）" in out[-1]


def test_detail_lines_marks_cursor():
    """当前高亮项用 ▶ 标记，其余用空格对齐。"""
    f = Feat(slug="demo", title="t", api=["a()", "b()"])
    rows = [("api:0", "a()", False, False), ("api:1", "b()", True, True)]
    out = _plain(feat_core.detail_lines(f, rows, 1, _MARK))
    item_lines = [ln for ln in out if "api:0" in ln or "api:1" in ln]
    assert item_lines[0].startswith("  "), "未选中不应有 ▶"
    assert item_lines[1].startswith("▶ ")
    assert "[■][■]" in item_lines[1]      # 已审已测


def test_detail_lines_comment_inline_after_its_row():
    """评论必须紧跟在**自己条目**的下一行（不是堆底部）。"""
    f = Feat(slug="demo", title="t", api=["a()", "b()"])
    f.set_comment("api:0", "第一行\n第二行")
    rows = [("api:0", "a()", False, False), ("api:1", "b()", False, False)]
    out = _plain(feat_core.detail_lines(f, rows, 0, _MARK))
    i = next(n for n, ln in enumerate(out) if "api:0" in ln)
    assert "第一行" in out[i + 1]
    assert "第二行" in out[i + 2]
    assert "api:1" in out[i + 3]


def test_detail_lines_survives_broken_feat():
    class Broken:
        slug = "b"

    out = _plain(feat_core.detail_lines(Broken(), [], 0, _MARK))
    assert out[0] == "b"


# --- 时间预算 ---------------------------------------------------------------


def test_core_suite_is_fast():
    start = time.perf_counter()
    for _ in range(200):
        f = _feat()
        feat_core.review_rows(f)
        feat_core.plan_toggle(f, "api:0", "review")
    assert time.perf_counter() - start < 0.5
