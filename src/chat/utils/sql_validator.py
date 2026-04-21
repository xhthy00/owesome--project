"""SQL syntax validator."""

import re
from typing import Tuple


def validate_sql(sql: str) -> Tuple[bool, str]:
    """
    Validate SQL syntax for security and correctness.

    Returns:
        (is_valid, error_message)
    """
    if not sql or not sql.strip():
        return False, "SQL is empty"

    sql_upper = sql.upper().strip()

    # Check for dangerous operations
    dangerous_patterns = [
        (r'\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE)\b', "Only SELECT queries are allowed"),
        (r';\s*\w', "Multiple statements not allowed"),
        (r'--', "SQL comments not allowed"),
        (r'/\*', "SQL comments not allowed"),
        (r'\b(EXEC|EXECUTE|xp_|sp_)\b', "Stored procedures not allowed"),
    ]

    for pattern, message in dangerous_patterns:
        if re.search(pattern, sql_upper, re.IGNORECASE):
            return False, message

    # Basic syntax check for SELECT
    if not sql_upper.startswith('SELECT'):
        return False, "Query must start with SELECT"

    # Check if SQL is too short (e.g., just "SELECT")
    if len(sql_upper) < 10:
        return False, "SQL query is too short or incomplete"

    # Check for balanced parentheses
    if sql.count('(') != sql.count(')'):
        return False, "Unbalanced parentheses"

    return True, ""


def extract_sql(response: str) -> str:
    """
    Extract SQL query from LLM response.

    Handles cases where LLM returns:
    - Just SQL: "SELECT * FROM users"
    - SQL with explanation: "Here is the query: SELECT * FROM users"
    - SQL in markdown: "```sql\nSELECT * FROM users\n```"
    - Multi-line SQL
    """
    if not response:
        return ""

    result = response.strip()

    # Remove markdown code blocks first
    code_block_pattern = r'```(?:\w+)?\s*([\s\S]*?)\s*```'
    match = re.search(code_block_pattern, result, re.IGNORECASE)
    if match:
        result = match.group(1).strip()

    # Remove common prefixes
    prefixes_to_remove = [
        r'^sql\s*:?\s*',
        r'^以下是SQL\s*:?\s*',
        r'^查询\s*:?\s*',
        r'^SQL\s*:?\s*',
    ]

    for prefix in prefixes_to_remove:
        result = re.sub(prefix, '', result, flags=re.IGNORECASE).strip()

    # Try to find SQL starting with SELECT (case insensitive)
    select_match = re.search(r'(SELECT\s+[\s\S]+)', result, re.IGNORECASE)
    if select_match:
        sql = select_match.group(1).strip()
        return sql

    # If no SELECT found, return the cleaned result
    # Remove newlines and extra spaces
    result = re.sub(r'\s+', ' ', result).strip()
    return result


def format_sql(sql: str, database_type: str = "pg") -> str:
    """
    Format SQL for specific database type.

    Args:
        sql: Raw SQL string
        database_type: "pg" or "mysql"

    Returns:
        Formatted SQL string
    """
    sql = sql.strip()

    # Basic formatting
    keywords = ['SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'ORDER BY', 'GROUP BY', 'HAVING', 'LIMIT', 'OFFSET', 'JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN', 'ON', 'AS', 'DISTINCT']

    for keyword in keywords:
        # Replace multiple spaces with single space before keyword
        pattern = r'\s+' + keyword
        sql = re.sub(pattern, ' ' + keyword, sql, flags=re.IGNORECASE)

    # Add newline before major clauses
    clauses = ['SELECT', 'FROM', 'WHERE', 'GROUP BY', 'HAVING', 'ORDER BY', 'LIMIT']
    for clause in clauses:
        sql = re.sub(r'\s+' + clause + r'\s+', r'\n' + clause.upper() + r' ', sql, flags=re.IGNORECASE)

    return sql.strip()
