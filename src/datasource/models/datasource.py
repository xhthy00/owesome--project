# Author: GreenHornet
# Date: 2026/4/19
# Description: 数据源模型定义

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Column, Text, BigInteger, DateTime, Identity
from sqlmodel import SQLModel, Field

"""
 数据源主表
"""
class CoreDatasource(SQLModel, table=True):
    __tablename__ = "core_datasource"
    id: int = Field(sa_column=Column(BigInteger, Identity(always=True), nullable=False, primary_key=True))
    name: str = Field(max_length=128, nullable=False)
    description: str = Field(max_length=512, nullable=True)
    type: str = Field(max_length=64) # 数据库类型
    type_name: str = Field(max_length=64, nullable=True) # 类型显示名
    configuration: str = Field(sa_column=Column(Text)) # 连接配置（AES加密）
    create_time: datetime = Field(sa_column=Column(DateTime(timezone=False), nullable=True))
    create_by: int = Field(sa_column=Column(BigInteger()))
    status: str = Field(max_length=64, nullable=True)
    num: str = Field(max_length=256, nullable=True)
    oid: int = Field(sa_column=Column(BigInteger()))
    table_relation: List = Field(sa_column=Column(JSONB, nullable=True)) # 表关系
    embedding: str = Field(sa_column=Column(Text, nullable=True)) # 向量表示
    recommended_config: int = Field(sa_column=Column(BigInteger())) # 推荐问题配置

"""
数据源下的表
"""
class CoreTable(SQLModel, table=True):
    __tablename__ = "core_table"
    id: int = Field(sa_column=Column(BigInteger, Identity(always=True), nullable=False, primary_key=True))
    ds_id: int = Field(sa_column=Column(BigInteger()))
    checked: bool = Field(default=True)
    table_name: str = Field(sa_column=Column(Text))
    table_comment: str = Field(sa_column=Column(Text))
    custom_comment: str = Field(sa_column=Column(Text))
    embedding: str = Field(sa_column=Column(Text, nullable=True))

"""
表字段
"""
class CoreField(SQLModel, table=True):
    __tablename__ = "core_field"
    id: int = Field(sa_column=Column(BigInteger, Identity(always=True), nullable=False, primary_key=True))
    ds_id: int = Field(sa_column=Column(BigInteger()))
    table_id: int = Field(sa_column=Column(BigInteger()))
    checked: bool = Field(default=True)
    field_name: str = Field(sa_column=Column(Text))
    field_type: str = Field(max_length=128, nullable=True)
    field_comment: str = Field(sa_column=Column(Text))
    custom_comment: str = Field(sa_column=Column(Text))
    field_index: int = Field(sa_column=Column(BigInteger()))

"""
推荐问题
"""
class DsRecommendedProblem(SQLModel, table=True):
    __tablename__ = "ds_recommended_problem"
    id: int = Field(sa_column=Column(BigInteger, Identity(always=True), nullable=False, primary_key=True))
    datasource_id: int = Field(sa_column=Column(BigInteger()))
    question: str = Field(sa_column=Column(Text))
    remark: str = Field(sa_column=Column(Text))
    sort: int = Field(sa_column=Column(BigInteger()))
    create_time: datetime = Field(sa_column=Column(DateTime(timezone=False), nullable=True))
    create_by: int = Field(sa_column=Column(BigInteger()))

# 创建数据源请求体
class CreateDatasource(BaseModel):
    id: int = None
    name: str = ''
    description: str = ''
    type: str = ''
    configuration: str = ''
    create_time: Optional[datetime] = None
    create_by: int = 0
    status: str = ''
    num: str = ''
    oid: int = 1
    tables: List[CoreTable] = []
    recommended_config: int = 1

# 数据源连接配置
class DatasourceConf(BaseModel):
    host: str = ''
    port: int = 0
    username: str = ''
    password: str = ''
    database: str = ''
    driver: str = ''
    extraJdbc: str = ''
    dbSchema: str = ''
    filename: str = ''
    sheets: List = ''
    mode: str = ''
    timeout: int = 30
    lowVersion: bool = False
    ssl: bool = False

    def to_dict(self):
        return {
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "database": self.database,
            "driver": self.driver,
            "extraJdbc": self.extraJdbc,
            "dbSchema": self.dbSchema,
            "filename": self.filename,
            "sheets": self.sheets,
            "mode": self.mode,
            "timeout": self.timeout,
            "lowVersion": self.lowVersion,
            "ssl": self.ssl
        }