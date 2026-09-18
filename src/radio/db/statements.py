"""PostgreSQL 原子 UPSERT 语句构建。

唯一约束下的「插入否则忽略/更新」统一在此处理，业务服务无需关心细节。
"""

from __future__ import annotations

from sqlalchemy import Table
from sqlalchemy.dialects.postgresql import insert as pg_insert


def insert_ignore(
    table: Table,
    values: dict,
    *,
    index_elements: list[str] | None = None,
    constraint: str | None = None,
):
    """插入；唯一键冲突时忽略。"""
    stmt = pg_insert(table).values(**values)
    if constraint:
        return stmt.on_conflict_do_nothing(constraint=constraint)
    return stmt.on_conflict_do_nothing(index_elements=index_elements)


def insert_update(
    table: Table,
    values: dict,
    set_: dict,
    *,
    index_elements: list[str] | None = None,
    constraint: str | None = None,
):
    """插入；唯一键冲突时按 set_ 更新（单条原子语句，无读改写竞态）。"""
    stmt = pg_insert(table).values(**values)
    if constraint:
        return stmt.on_conflict_do_update(constraint=constraint, set_=set_)
    return stmt.on_conflict_do_update(index_elements=index_elements, set_=set_)
