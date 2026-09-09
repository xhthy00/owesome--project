"""教育 ECharts option 生成单元测试。"""

from __future__ import annotations

import json

from src.agent.education.charts import build_chart_option


def test_knowledge_bar_uses_categories_and_values():
    raw = build_chart_option(
        "knowledge_bar",
        {"categories": ["集合及其运算", "分段函数"], "values": [90.0, 42.35]},
        "知识点得分率",
    )
    opt = json.loads(raw)
    assert opt["title"]["text"] == "知识点得分率"
    assert opt["yAxis"]["data"] == ["集合及其运算", "分段函数"]
    assert opt["series"][0]["data"] == [90.0, 42.35]


def test_bar_alias_with_segments_resolves_score_distribution():
    from src.agent.education.charts import resolve_chart_type

    assert resolve_chart_type("bar", {"segments": [{"label": "A", "count": 1}]}) == "score_distribution"


def test_subject_bar_ignores_categories_shorthand():
    """subject_bar 只认 subjects/metrics，误传 categories 时应为空图。"""
    raw = build_chart_option(
        "subject_bar",
        {"categories": ["A"], "values": [50.0]},
        "错误用法",
    )
    opt = json.loads(raw)
    assert opt["xAxis"]["data"] == []
    assert opt["series"] == []


def test_heatmap_chart():
    raw = build_chart_option(
        "heatmap",
        {"rows": ["一班", "二班"], "cols": ["60-70", "70-80"], "matrix": [[65.0, 75.0], [70.0, 80.0]]},
        "班级分数段",
    )
    opt = json.loads(raw)
    assert opt["series"][0]["type"] == "heatmap"


def test_comprehensive_subject_compare_chart_has_all_subjects():
    """对比柱图必须以考试为系列、科目为类目，否则后部科目会空白。"""
    from src.agent.education.comprehensive import build_comprehensive_data

    records = [
        {
            "exam": "期末",
            "student": "甲",
            "subjects": {
                "物理": 90,
                "数学": 130,
                "化学": 80,
                "生物": 70,
                "英语": 120,
                "语文": 110,
            },
            "total": 600,
        },
        {
            "exam": "2026届高三3月",
            "student": "甲",
            "subjects": {
                "物理": 92,
                "数学": 128,
                "化学": 82,
                "生物": 72,
                "英语": 122,
                "语文": 112,
            },
            "total": 608,
        },
    ]
    data = build_comprehensive_data(records, ["期末", "2026届高三3月"], class_name="高三(1)班")
    opt = json.loads(data["SUBJECT_COMPARE_CHART"])
    assert opt["xAxis"]["data"] == ["物理", "数学", "化学", "生物", "英语", "语文"]
    assert {s["name"] for s in opt["series"]} == {"期末", "2026届高三3月"}
    assert all(len(s["data"]) == 6 for s in opt["series"])
    assert all(s["data"][4] > 0 and s["data"][5] > 0 for s in opt["series"])

