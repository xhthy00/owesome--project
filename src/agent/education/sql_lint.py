"""教育 SQL 护栏：致命项拦截，其余告警。"""

from __future__ import annotations

import re
from typing import Sequence

_AVG_REACH = re.compile(r"\bAVG\s*\(\s*reach_rate\s*\)", re.IGNORECASE)
_MONTH_DISTRICT = re.compile(r"'月[\u4e00-\u9fff]{1,6}区'")
_SUBJECT_COLS = (
    "ywzw", "sxkg", "yyzw", "hxzh", "swzh", "zzzh", "dlzh",
    "yw", "sx", "yy", "wl", "hx", "sw", "ls", "zz", "dl",
)
_SUBJECT_COL_ALT = "|".join(_SUBJECT_COLS)
_SUBJECT_STAT = re.compile(
    r"\b(?:AVG|MEDIAN|MIN|MAX|SUM|STDDEV(?:_SAMP|_POP)?|STDEV(?:_SAMP|_POP)?|"
    r"VAR(?:_SAMP|_POP)?|VARIANCE)\s*\(\s*(?:[\w]+\.)?(?P<col>"
    + _SUBJECT_COL_ALT
    + r")\s*\)",
    re.IGNORECASE,
)
_PERCENTILE_SUBJECT = re.compile(
    r"PERCENTILE_\w+\s*\([^)]*\)\s*WITHIN\s+GROUP\s*\(\s*ORDER\s+BY\s+"
    r"(?:[\w]+\.)?(?P<col>" + _SUBJECT_COL_ALT + r")\b",
    re.IGNORECASE,
)


def _subject_stat_excludes_zero(sql: str, col: str, match_end: int) -> bool:
    """聚合后有 FILTER (WHERE col>0)，或整句有 AND/WHERE col>0。"""
    tail = sql[match_end : match_end + 180]
    col_re = re.escape(col)
    if re.search(rf"FILTER\s*\(\s*WHERE\s+[\w.]*{col_re}\s*>\s*0", tail, re.I):
        return True
    if re.search(rf"\b(?:AND|WHERE)\s+[\w.]*{col_re}\s*>\s*0", sql, re.I):
        return True
    return False


_EQ_LIT = re.compile(
    r"(?:exam_name|district|dq|school_name|s_name|xx|bj|class_name)\s*=\s*'([^']+)'",
    re.IGNORECASE,
)
#: 化/生/政/地必须用转换分；AVG(hx) 会命中 hx 而不会误伤 hxzh。
_RAW_ELECTIVE_STAT = re.compile(
    r"\b(?:AVG|MEDIAN|MIN|MAX|SUM|STDDEV(?:_SAMP|_POP)?|STDEV(?:_SAMP|_POP)?|"
    r"VAR(?:_SAMP|_POP)?|VARIANCE)\s*\(\s*(?:[\w]+\.)?(?P<col>hx|sw|zz|dl)\s*\)",
    re.IGNORECASE,
)
_RANK_PARTITION_BY_BJ = re.compile(
    r"\b(?:RANK|DENSE_RANK|ROW_NUMBER)\s*\(\s*\)\s*OVER\s*\("
    r"[^)]*PARTITION\s+BY\s+[^)]*\bbj\b",
    re.IGNORECASE | re.DOTALL,
)
_COUNT_DISTINCT_BJ = re.compile(
    r"COUNT\s*\(\s*DISTINCT\s+(?:[\w]+\.)?bj\s*\)",
    re.IGNORECASE,
)


def _unbound_literals(sql: str, bound: Sequence[str] | None) -> list[str]:
    allowed = [str(x).strip() for x in (bound or []) if str(x).strip()]
    if not allowed:
        return []
    bad: list[str] = []
    for lit in _EQ_LIT.findall(sql or ""):
        val = str(lit).strip()
        if not val:
            continue
        if any(val == a or val in a or a in val for a in allowed):
            continue
        if val not in bad:
            bad.append(val)
    return bad


def lint_edu_sql_blocks(
    sql: str,
    bound_literals: Sequence[str] | None = None,
    question: str | None = None,
) -> list[str]:
    """致命项：不得执行。"""
    s = sql or ""
    blocks: list[str] = []
    if _AVG_REACH.search(s):
        blocks.append(
            "检测到 AVG(reach_rate)：区县/全市达线率须 "
            "SUM(reached_count)/SUM(candidates) 重算，禁止对 reach_rate 求平均。"
        )
    if _MONTH_DISTRICT.search(s):
        blocks.append(
            "检测到疑似把「N月」拼进区县的字面量（如 '月广陵区'）："
            "请改为真实区县名或 district LIKE '%广陵%'，并先 peek_edu_filter_values。"
        )
    missing: list[str] = []
    for m in list(_SUBJECT_STAT.finditer(s)) + list(_PERCENTILE_SUBJECT.finditer(s)):
        col = (m.group("col") or "").lower()
        if col and col not in missing and not _subject_stat_excludes_zero(s, col, m.end()):
            missing.append(col)
    if missing:
        cols = "、".join(missing)
        blocks.append(
            f"检测到对 {cols} 的分数统计未排除 0 分：未选考/缺考在宽表为 0，"
            "计入会把选考科均分拉低、标准差/均衡性失真。"
            "凡均分/标准差/方差/中位/最值/分数段，须 AGG(col) FILTER (WHERE col > 0)，"
            "并同时给出 COUNT(*) FILTER (WHERE col > 0) 作为该科参考人数。"
        )
    if _overview_rank_missing_enrolled(s):
        blocks.append(
            "检测到全市班级/学校排名未排除市报生：tb_score_overview 须 "
            "AND xsxz='在籍生'，否则往届/市报虚拟班会挤占名次。"
        )
    if _class_rank_partitioned_by_name(s):
        blocks.append(
            "检测到 RANK() OVER (PARTITION BY bj)：这是各校同名班互比，不是全市班级排名。"
            "必须 GROUP BY xx,bj 后 RANK() OVER (ORDER BY 均分 DESC)，禁止 PARTITION BY bj；"
            "目标校/班只允许在排名完成后再 WHERE 过滤。"
        )
    if _count_distinct_class_name_as_city_n(s):
        blocks.append(
            "检测到 COUNT(DISTINCT bj)：班名（高三(1)班…）全市重复，这是班名种类不是全市班级数。"
            "全市班级数用 COUNT(*) OVER ()（对 xx,bj 分组结果），禁止 COUNT(DISTINCT bj)。"
        )
    raw_electives = _raw_elective_cols(s)
    if raw_electives:
        cols = "、".join(raw_electives)
        blocks.append(
            f"检测到对 {cols} 做分数统计：化学/生物/政治/地理必须用转换分 "
            "hxzh/swzh/zzzh/dlzh，禁止 hx/sw/zz/dl。"
        )
    if _school_column_aliased_as_class(s):
        blocks.append(
            "检测到把 xx（学校）别名为 class_name/班级：班级横向对比必须用 bj。"
            "SELECT bj AS class_name，GROUP BY xx, bj；禁止 SELECT xx AS class_name，禁止只 GROUP BY xx。"
        )
    if _class_alias_grouped_by_school_only(s):
        blocks.append(
            "检测到 SELECT 班级别名却只 GROUP BY xx：会把全校塌成一行学校均分。"
            "各班对比必须 SELECT bj AS class_name，GROUP BY xx, bj。"
        )
    if _dual_class_rank_missing_union(s, question):
        blocks.append(
            "班级全市六门排名须一条 SQL 用 UNION ALL 一次返回两个口径"
            "（按选考方向 + 不区分选考），禁止只查文理混排；"
            "禁止拆两次 execute_sql（查询结果只保留最后一次）。"
        )
    if _class_rank_outer_target_without_neighborhood(s, question):
        blocks.append(
            "班级全市排名查询结果须含对照班：第1名 + 目标班名次前后各3名（标记本班）。"
            "用目标校+班定位窗口（BETWEEN），禁止外层 WHERE 只留下目标班一行。"
        )
    if _class_rank_outer_bj_without_school(s):
        blocks.append(
            "班级全市排名外层必须同时过滤学校（xx/学校）与班级（bj/班级），"
            "禁止只滤班级（同名班会串校）。"
        )
    if _class_rank_pool_unwashed(s, question):
        blocks.append(
            "班级全市排名池须洗掉小班与其他校：xxlb NOT LIKE '%其他%'（中专/职校），"
            "整班参考人数 HAVING COUNT(*) >= 10。"
        )
    if _subject_class_rank_keeps_empty_avg(s, question):
        blocks.append(
            "班级单科全市排名须把该科有效人数为 0 的班排除出池："
            "HAVING COUNT(*) FILTER (WHERE col > 0) >= 3，或 RANK() OVER (ORDER BY 均分 DESC NULLS LAST)；"
            "禁止缺考/无分班排到第1。"
        )
    unbound = _unbound_literals(s, bound_literals)
    if unbound:
        blocks.append(
            "WHERE 字面量不在本轮已绑定集合："
            + "、".join(unbound)
            + "。必须使用已确认的考试/学校/班级/区县。"
        )
    return blocks


def lint_edu_sql(
    sql: str,
    bound_literals: Sequence[str] | None = None,
    question: str | None = None,
) -> list[str]:
    """兼容旧接口：返回全部护栏文案（含致命项）。"""
    return lint_edu_sql_blocks(sql, bound_literals, question=question)


def _excludes_shibao(sql: str) -> bool:
    s = sql or ""
    if re.search(r"xsxz\s*=\s*'在籍生'", s, re.I):
        return True
    if re.search(r"xsxz[^\n]{0,60}市报", s):
        return True
    return False


def _overview_rank_missing_enrolled(sql: str) -> bool:
    s = sql or ""
    if "tb_score_overview" not in s.lower():
        return False
    ranked = bool(re.search(r"\b(?:RANK|DENSE_RANK|ROW_NUMBER)\s*\(", s, re.I))
    by_class = bool(re.search(r"GROUP\s+BY\s+[^;]*\bbj\b", s, re.I))
    if not ranked and not by_class:
        return False
    return not _excludes_shibao(s)


def _class_rank_partitioned_by_name(sql: str) -> bool:
    """班级聚合后再按班名分区排名 → 同名班跨校互比。"""
    s = sql or ""
    if "tb_score_overview" not in s.lower():
        return False
    if not re.search(r"GROUP\s+BY\s+[^;]*\bbj\b", s, re.I):
        return False
    return bool(_RANK_PARTITION_BY_BJ.search(s))


def _count_distinct_class_name_as_city_n(sql: str) -> bool:
    s = sql or ""
    if "tb_score_overview" not in s.lower():
        return False
    return bool(_COUNT_DISTINCT_BJ.search(s))


def _raw_elective_cols(sql: str) -> list[str]:
    s = sql or ""
    if "tb_score_overview" not in s.lower():
        return []
    out: list[str] = []
    for m in _RAW_ELECTIVE_STAT.finditer(s):
        col = (m.group("col") or "").lower()
        if col and col not in out:
            out.append(col)
    return out


def _school_column_aliased_as_class(sql: str) -> bool:
    """xx 是校名。别成班级再 GROUP BY xx，各班对比会塌成一行学校均分。"""
    s = sql or ""
    if "tb_score_overview" not in s.lower():
        return False
    return bool(
        re.search(r"\bxx\s+AS\s+(?:class_name|班级|bj)\b", s, re.I)
    )


def _is_zf6m_class_city_rank_sql(sql: str) -> bool:
    s = sql or ""
    if "tb_score_overview" not in s.lower():
        return False
    if not re.search(r"\b(?:RANK|DENSE_RANK|ROW_NUMBER)\s*\(", s, re.I):
        return False
    if not re.search(r"GROUP\s+BY\s+[^;]*\bbj\b", s, re.I):
        return False
    return bool(re.search(r"\bzf6m\b", s, re.I))


_SUBJECT_RANK_COL = re.compile(
    r"\b(?:yw|sx|yy|wl|ls|hxzh|swzh|zzzh|dlzh)\b",
    re.IGNORECASE,
)


def _is_subject_class_city_rank_sql(sql: str) -> bool:
    s = sql or ""
    if "tb_score_overview" not in s.lower():
        return False
    if not re.search(r"\b(?:RANK|DENSE_RANK|ROW_NUMBER)\s*\(", s, re.I):
        return False
    if not re.search(r"GROUP\s+BY\s+[^;]*\bbj\b", s, re.I):
        return False
    return bool(_SUBJECT_RANK_COL.search(s))


def _subject_class_rank_keeps_empty_avg(sql: str, question: str | None) -> bool:
    """单科班级排名未排除无分班，DESC 默认 NULLS FIRST 会把缺考班排第1。"""
    try:
        from src.agent.education.query_parse import is_class_subject_city_rank_query
    except Exception:
        return False
    if not is_class_subject_city_rank_query(question or ""):
        return False
    if not _is_subject_class_city_rank_sql(sql):
        return False
    s = sql or ""
    if re.search(r"NULLS\s+LAST", s, re.I):
        return False
    if re.search(
        r"HAVING[\s\S]{0,280}(?:IS\s+NOT\s+NULL|FILTER[\s\S]{0,80}>\s*0[\s\S]{0,40}>=\s*[1-9])",
        s,
        re.I,
    ):
        return False
    return True


def _dual_class_rank_missing_union(sql: str, question: str | None) -> bool:
    """默认两行口径却只查了混排（无 UNION ALL 或缺两行标签）。"""
    try:
        from src.agent.education.query_parse import class_city_rank_answer_mode
    except Exception:
        return False
    if class_city_rank_answer_mode(question or "") != "dual":
        return False
    if not _is_zf6m_class_city_rank_sql(sql):
        return False
    s = sql or ""
    # 只拦「没有 UNION ALL」的混排单查。口径列名允许「物理类方向」等，
    # 不必一字不差写「按选考方向」（否则正确双行 SQL 会被误拦）。
    return not bool(re.search(r"\bUNION\s+ALL\b", s, re.I))


def _class_rank_pool_unwashed(sql: str, question: str | None) -> bool:
    """班级全市排名未排除其他校/整班不足 10 人。"""
    try:
        from src.agent.education.query_parse import (
            class_city_rank_answer_mode,
            is_class_subject_city_rank_query,
        )
    except Exception:
        return False
    q = question or ""
    if class_city_rank_answer_mode(q):
        if not _is_zf6m_class_city_rank_sql(sql):
            return False
    elif is_class_subject_city_rank_query(q):
        if not _is_subject_class_city_rank_sql(sql):
            return False
    else:
        return False
    s = sql or ""
    has_other = bool(re.search(r"xxlb[^\n;]{0,80}其他", s, re.I))
    has_min10 = bool(re.search(r"HAVING\s+COUNT\s*\([^)]*\)\s*>=\s*10", s, re.I))
    return not (has_other and has_min10)


def _class_rank_outer_target_without_neighborhood(sql: str, question: str | None) -> bool:
    """目标班过滤后没有名次窗口 → 摘要只剩一行，看不到前后对照。"""
    try:
        from src.agent.education.query_parse import (
            class_city_rank_answer_mode,
            is_class_subject_city_rank_query,
        )
    except Exception:
        return False
    q = question or ""
    if class_city_rank_answer_mode(q):
        if not _is_zf6m_class_city_rank_sql(sql):
            return False
    elif is_class_subject_city_rank_query(q):
        if not _is_subject_class_city_rank_sql(sql):
            return False
    else:
        return False
    s = sql or ""
    if re.search(r"\bBETWEEN\b", s, re.I):
        return False
    has_bj = bool(re.search(r"\b(?:bj|班级)\s*(?:=|LIKE)\s*'", s, re.I))
    has_xx = bool(re.search(r"\b(?:xx|学校)\s*(?:=|LIKE)\s*'", s, re.I))
    return has_bj and has_xx


def _class_rank_outer_bj_without_school(sql: str) -> bool:
    """GROUP BY xx,bj 后 RANK，外层只滤班级不滤学校 → 同名班串校。"""
    s = sql or ""
    if "tb_score_overview" not in s.lower():
        return False
    if not re.search(r"\b(?:RANK|DENSE_RANK|ROW_NUMBER)\s*\(", s, re.I):
        return False
    if not re.search(r"GROUP\s+BY\s+[^;]*\bbj\b", s, re.I):
        return False
    has_bj = bool(re.search(r"\b(?:bj|班级)\s*(?:=|LIKE)\s*", s, re.I))
    has_xx = bool(re.search(r"\b(?:xx|学校)\s*(?:=|LIKE)\s*", s, re.I))
    return has_bj and not has_xx


def _class_alias_grouped_by_school_only(sql: str) -> bool:
    """SELECT 了 class_name/班级 却只按学校分组。"""
    s = sql or ""
    if "tb_score_overview" not in s.lower():
        return False
    if not re.search(r"\bAS\s+(?:class_name|班级)\b", s, re.I):
        return False
    if not re.search(r"GROUP\s+BY\s+", s, re.I):
        return False
    grouped_bj = bool(re.search(r"GROUP\s+BY\s+[^;]*\bbj\b", s, re.I))
    grouped_xx = bool(re.search(r"GROUP\s+BY\s+[^;]*\bxx\b", s, re.I))
    return grouped_xx and not grouped_bj


def format_lint_warnings(warnings: list[str]) -> str:
    if not warnings:
        return ""
    lines = ["【SQL lint 警告】请改写后重试："]
    lines.extend(f"- {w}" for w in warnings)
    return "\n".join(lines) + "\n"


def format_lint_blocks(blocks: list[str]) -> str:
    if not blocks:
        return ""
    lines = ["【SQL lint 拦截】禁止执行，请按下列口径改写后再 execute_sql："]
    lines.extend(f"- {w}" for w in blocks)
    return "\n".join(lines) + "\n"


__all__ = [
    "format_lint_blocks",
    "format_lint_warnings",
    "lint_edu_sql",
    "lint_edu_sql_blocks",
]
