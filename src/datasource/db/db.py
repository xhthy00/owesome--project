"""Database connection testing and execution."""

from typing import Any, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def test_db_connection(db_type: str, config: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
    """
    Test database connection.

    Returns:
        (success, message, version)
    """
    if db_type == "pg":
        return test_postgresql_connection(config)
    elif db_type == "mysql":
        return test_mysql_connection(config)
    else:
        return False, f"Unsupported database type: {db_type}", None


def test_postgresql_connection(config: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
    """Test PostgreSQL connection."""
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=config.get("host", "localhost"),
            port=config.get("port", 5432),
            user=config.get("username", "postgres"),
            password=config.get("password", ""),
            database=config.get("database", "postgres"),
            connect_timeout=config.get("timeout", 30),
        )

        cursor = conn.cursor()
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return True, "Connection successful", version
    except ImportError:
        return False, "psycopg2 not installed", None
    except Exception as e:
        return False, f"Connection failed: {str(e)}", None


def test_mysql_connection(config: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
    """Test MySQL connection."""
    try:
        import pymysql

        conn = pymysql.connect(
            host=config.get("host", "localhost"),
            port=config.get("port", 3306),
            user=config.get("username", "root"),
            password=config.get("password", ""),
            database=config.get("database", ""),
            connect_timeout=config.get("timeout", 30),
        )

        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return True, "Connection successful", version
    except ImportError:
        return False, "pymysql not installed", None
    except Exception as e:
        return False, f"Connection failed: {str(e)}", None


def execute_sql(db_type: str, config: Dict[str, Any], sql: str) -> Tuple[bool, str, Any]:
    """
    Execute SQL on database.

    Returns:
        (success, message, result)
    """
    if db_type == "pg":
        return execute_postgresql_sql(config, sql)
    elif db_type == "mysql":
        return execute_mysql_sql(config, sql)
    else:
        return False, f"Unsupported database type: {db_type}", None


def execute_postgresql_sql(config: Dict[str, Any], sql: str) -> Tuple[bool, str, Any]:
    """Execute SQL on PostgreSQL."""
    try:
        import psycopg2
        import json

        conn = psycopg2.connect(
            host=config.get("host", "localhost"),
            port=config.get("port", 5432),
            user=config.get("username", "postgres"),
            password=config.get("password", ""),
            database=config.get("database", "postgres"),
            connect_timeout=config.get("timeout", 30),
        )

        cursor = conn.cursor()
        cursor.execute(sql)

        # Check if it's a SELECT query
        if cursor.description:
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            result = {
                "columns": columns,
                "rows": [list(row) for row in rows],
                "row_count": len(rows),
            }
        else:
            conn.commit()
            result = {"row_count": cursor.rowcount}

        cursor.close()
        conn.close()

        return True, "Success", result
    except Exception as e:
        return False, f"SQL execution failed: {str(e)}", None


def execute_mysql_sql(config: Dict[str, Any], sql: str) -> Tuple[bool, str, Any]:
    """Execute SQL on MySQL."""
    try:
        import pymysql

        conn = pymysql.connect(
            host=config.get("host", "localhost"),
            port=config.get("port", 3306),
            user=config.get("username", "root"),
            password=config.get("password", ""),
            database=config.get("database", ""),
            connect_timeout=config.get("timeout", 30),
        )

        cursor = conn.cursor()
        cursor.execute(sql)

        # Check if it's a SELECT query
        if cursor.description:
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            result = {
                "columns": columns,
                "rows": [list(row) for row in rows],
                "row_count": len(rows),
            }
        else:
            conn.commit()
            result = {"row_count": cursor.rowcount}

        cursor.close()
        conn.close()

        return True, "Success", result
    except Exception as e:
        return False, f"SQL execution failed: {str(e)}", None


def get_schema_info(db_type: str, config: Dict[str, Any]) -> list:
    """
    Get database schema (tables and columns).

    Returns:
        List of table info dicts:
        [
            {
                "name": "users",
                "comment": "User table",
                "fields": [
                    {"name": "id", "type": "bigint", "comment": "Primary key"},
                    {"name": "name", "type": "varchar(255)", "comment": "Name"},
                ]
            },
            ...
        ]
    """
    if db_type == "pg":
        return get_postgresql_schema(config)
    elif db_type == "mysql":
        return get_mysql_schema(config)
    else:
        return []


def get_postgresql_schema(config: Dict[str, Any]) -> list:
    """Get PostgreSQL schema."""
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=config.get("host", "localhost"),
            port=config.get("port", 5432),
            user=config.get("username", "postgres"),
            password=config.get("password", ""),
            database=config.get("database", "postgres"),
            connect_timeout=config.get("timeout", 30),
        )

        cursor = conn.cursor()

        # Get tables
        cursor.execute("""
            SELECT c.relname AS table_name,
                   COALESCE(d.description, '') AS table_comment
            FROM pg_catalog.pg_class c
            LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_catalog.pg_description d ON d.objoid = c.oid AND d.objsubid = 0
            WHERE n.nspname = 'public'
              AND c.relkind IN ('r', 'v', 'p', 'm')
              AND c.relname NOT LIKE 'pg_%'
              AND c.relname NOT LIKE 'sql_%'
            ORDER BY c.relname
        """)

        tables = []
        for row in cursor.fetchall():
            table_name, table_comment = row
            table_info = {
                "name": table_name,
                "comment": table_comment,
                "fields": []
            }

            # Get columns for this table
            cursor.execute("""
                SELECT a.attname AS column_name,
                       pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
                       COALESCE(col_description(c.oid, a.attnum), '') AS column_comment
                FROM pg_catalog.pg_attribute a
                JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
                JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname = %s
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                ORDER BY a.attnum
            """, (table_name,))

            for col_row in cursor.fetchall():
                col_name, data_type, col_comment = col_row
                table_info["fields"].append({
                    "name": col_name,
                    "type": data_type,
                    "comment": col_comment
                })

            tables.append(table_info)

        cursor.close()
        conn.close()
        return tables

    except Exception as e:
        logger.error(f"Failed to get PostgreSQL schema: {e}")
        return []


def get_mysql_schema(config: Dict[str, Any]) -> list:
    """Get MySQL schema."""
    try:
        import pymysql

        conn = pymysql.connect(
            host=config.get("host", "localhost"),
            port=config.get("port", 3306),
            user=config.get("username", "root"),
            password=config.get("password", ""),
            database=config.get("database", ""),
            connect_timeout=config.get("timeout", 30),
        )

        cursor = conn.cursor()

        # Get tables
        cursor.execute("SHOW TABLES")
        table_names = [row[0] for row in cursor.fetchall()]

        tables = []
        for table_name in table_names:
            # Get table comment
            cursor.execute(f"SELECT TABLE_COMMENT FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s", (table_name,))
            result = cursor.fetchone()
            table_comment = result[0] if result else ""

            table_info = {
                "name": table_name,
                "comment": table_comment,
                "fields": []
            }

            # Get columns
            cursor.execute(f"DESCRIBE `{table_name}`")
            for col_row in cursor.fetchall():
                col_name, data_type, nullable, key, default, extra = col_row
                table_info["fields"].append({
                    "name": col_name,
                    "type": data_type,
                    "comment": ""
                })

            tables.append(table_info)

        cursor.close()
        conn.close()
        return tables

    except Exception as e:
        logger.error(f"Failed to get MySQL schema: {e}")
        return []
