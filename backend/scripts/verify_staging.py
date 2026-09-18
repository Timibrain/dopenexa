#!/usr/bin/env python3
"""Read-only schema audit plus a disposable object-storage round trip.

Run inside the staging backend: python scripts/verify_staging.py
SQL is parsed, never executed. Unknown migration DDL fails closed so a new
migration cannot silently escape verification. No application modules are imported.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

import asyncpg
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import httpx
from pglast import ast, parse_plpgsql, parse_sql
from pglast.stream import RawStream

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
TIMEOUT = 15


class VerificationError(Exception):
    """Only locally authored, secret-free messages may be printed."""


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def sql(node):
    return RawStream()(node)


def relation(node):
    require(node.schemaname is None, "schema-qualified migration DDL needs verifier support")
    return node.relname


def strings(nodes):
    return tuple(n.sval for n in (nodes or ()))


def expression(node):
    """Normalize PostgreSQL's harmless catalog rewrites, retaining literal case."""
    if node is None:
        return None
    if isinstance(node, (tuple, list)):
        return tuple(expression(n) for n in node)
    if not isinstance(node, ast.Node):
        return node
    if isinstance(node, ast.TypeCast):
        # The catalog adds casts to typed constants and varchar/char comparisons.
        names = strings(node.typeName.names)
        if isinstance(node.arg, ast.A_Const) or names[-1] in {"text", "varchar", "bpchar"}:
            return expression(node.arg)
    if isinstance(node, ast.A_Expr):
        kind = node.kind.name
        if kind == "AEXPR_IN" and strings(node.name) == ("=",):
            return ("in", expression(node.lexpr), expression(node.rexpr))
        if kind == "AEXPR_OP_ANY" and strings(node.name) == ("=",):
            array = node.rexpr
            if isinstance(array, ast.TypeCast) and strings(array.typeName.names)[-1] == "text":
                array = array.arg
            if isinstance(array, ast.A_ArrayExpr):
                return ("in", expression(node.lexpr), expression(array.elements))
        if kind == "AEXPR_BETWEEN":
            low, high = node.rexpr
            return ("and", (("op", (">=",), expression(node.lexpr), expression(low)),
                            ("op", ("<=",), expression(node.lexpr), expression(high))))
        if kind == "AEXPR_OP":
            return ("op", strings(node.name), expression(node.lexpr), expression(node.rexpr))
    if isinstance(node, ast.BoolExpr) and node.boolop.name == "AND_EXPR":
        return ("and", expression(node.args))
    return (type(node).__name__, tuple(
        (key, expression(getattr(node, key))) for key in node
        if key not in {"location", "stmt_location", "stmt_len"}
        and getattr(node, key) is not None
    ))


def type_signature(node):
    names = strings(node.names)
    if names[0] == "pg_catalog":
        names = names[1:]
    return (names, expression(node.typmods), expression(node.arrayBounds))


def parsed_expression(value):
    return parse_sql("SELECT " + value)[0].stmt.targetList[0].val if value is not None else None


def constraint_signature(node, column=None):
    kind = node.contype.name
    keys = strings(node.keys) or ((column,) if column else ())
    flags = (bool(node.deferrable), bool(node.initdeferred))
    if kind in {"CONSTR_PRIMARY", "CONSTR_UNIQUE"}:
        return (kind, keys, bool(node.nulls_not_distinct), flags)
    if kind == "CONSTR_FOREIGN":
        return (kind, strings(node.fk_attrs) or keys, relation(node.pktable),
                strings(node.pk_attrs), node.fk_matchtype, node.fk_upd_action,
                node.fk_del_action, flags)
    if kind == "CONSTR_CHECK":
        return (kind, expression(node.raw_expr), bool(node.is_no_inherit))
    raise VerificationError("unsupported migration constraint: " + kind)


def index_signature(node, catalog_schema=None):
    if catalog_schema is not None:
        require(node.relation.schemaname == catalog_schema, "index is in the wrong schema")
        node.relation.schemaname = None
    require(not node.indexIncludingParams and not node.excludeOpNames,
            "index INCLUDE/exclusion needs verifier support")
    elements = []
    for item in node.indexParams:
        order = item.ordering.name
        descending = order == "SORTBY_DESC"
        nulls = item.nulls_ordering.name
        nulls_first = descending if nulls == "SORTBY_NULLS_DEFAULT" else nulls == "SORTBY_NULLS_FIRST"
        elements.append((item.name, expression(item.expr), strings(item.opclass),
                         strings(item.collation), descending, nulls_first))
    options = tuple(sorted((o.defname, sql(o.arg).strip("'")) for o in (node.options or ())))
    return (relation(node.relation), bool(node.unique), bool(node.nulls_not_distinct),
            node.accessMethod or "btree", tuple(elements), expression(node.whereClause), options)


@dataclass
class Table:
    columns: dict = field(default_factory=dict)
    constraints: list = field(default_factory=list)


@dataclass
class Schema:
    files: list = field(default_factory=list)
    tables: dict = field(default_factory=dict)
    extensions: set = field(default_factory=set)
    enums: dict = field(default_factory=dict)
    indexes: dict = field(default_factory=dict)
    functions: dict = field(default_factory=dict)
    triggers: dict = field(default_factory=dict)

    def add_constraint(self, table, node, column=None):
        kind = node.contype.name
        if kind == "CONSTR_NOTNULL":
            table.columns[column][1] = True
        elif kind == "CONSTR_DEFAULT":
            table.columns[column][2] = expression(node.raw_expr)
        else:
            signature = constraint_signature(node, column)
            table.constraints.append((node.conname, signature))
            if kind == "CONSTR_PRIMARY":
                for key in signature[1]:
                    table.columns[key][1] = True

    def add_column(self, table, node):
        require(node.identity in (None, "\x00") and node.generated in (None, "\x00") and not node.collClause,
                "identity/generated/collated columns need verifier support")
        table.columns[node.colname] = [type_signature(node.typeName), False, None]
        for constraint in node.constraints or ():
            self.add_constraint(table, constraint, node.colname)

    def apply(self, node):
        if isinstance(node, ast.CreateExtensionStmt):
            self.extensions.add(node.extname)
        elif isinstance(node, ast.CreateEnumStmt):
            require(len(node.typeName) == 1, "qualified enum needs verifier support")
            self.enums[node.typeName[0].sval] = strings(node.vals)
        elif isinstance(node, ast.CreateStmt):
            require(not node.inhRelations and not node.partspec and not node.ofTypename,
                    "inherited/partitioned/typed tables need verifier support")
            table = self.tables.setdefault(relation(node.relation), Table())
            for item in node.tableElts or ():
                if isinstance(item, ast.ColumnDef):
                    self.add_column(table, item)
                elif isinstance(item, ast.Constraint):
                    self.add_constraint(table, item)
                else:
                    raise VerificationError("unsupported table element")
        elif isinstance(node, ast.AlterTableStmt):
            table = self.tables[relation(node.relation)]
            for command in node.cmds:
                kind = command.subtype.name
                if kind == "AT_AddColumn":
                    self.add_column(table, command.def_)
                elif kind == "AT_AddConstraint":
                    self.add_constraint(table, command.def_)
                elif kind == "AT_DropConstraint":
                    table.constraints = [(n, s) for n, s in table.constraints if n != command.name]
                elif kind in {"AT_DropNotNull", "AT_SetNotNull"}:
                    table.columns[command.name][1] = kind == "AT_SetNotNull"
                elif kind == "AT_ColumnDefault":
                    table.columns[command.name][2] = expression(command.def_)
                else:
                    raise VerificationError("unsupported migration ALTER: " + kind)
        elif isinstance(node, ast.IndexStmt):
            self.indexes[node.idxname] = index_signature(node)
        elif isinstance(node, ast.CreateFunctionStmt):
            require(len(node.funcname) == 1 and not node.parameters,
                    "qualified/parameterized function needs verifier support")
            options = {o.defname: o.arg for o in node.options}
            require(set(options) <= {"as", "language"}, "function options need verifier support")
            self.functions[node.funcname[0].sval] = (
                options["as"][0].sval.strip(), options["language"].sval, sql(node.returnType))
        elif isinstance(node, ast.CreateTrigStmt):
            self.triggers[(relation(node.relation), node.trigname)] = trigger_signature(node)
        elif isinstance(node, ast.DropStmt):
            require(node.removeType.name == "OBJECT_TRIGGER", "unsupported migration DROP")
            for obj in node.objects:
                table, name = strings(obj)
                self.triggers.pop((table, name), None)
        elif isinstance(node, ast.DoStmt):
            # Walk the parsed PL/pgSQL tree, not regex matches inside strings/comments.
            # Only the repo's catalog-guarded IF/ALTER pattern is supported.
            for block in parse_plpgsql(sql(node)):
                self.apply_plpgsql(block)
        elif isinstance(node, (ast.InsertStmt, ast.UpdateStmt)):
            # Seed data/backfills do not define schema. Never execute them.
            return
        else:
            raise VerificationError("unsupported migration statement: " + type(node).__name__)

    def apply_plpgsql(self, value):
        if isinstance(value, list):
            for item in value:
                self.apply_plpgsql(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key == "PLpgSQL_stmt_execsql":
                    for statement in parse_sql(item["sqlstmt"]["PLpgSQL_expr"]["query"]):
                        require(isinstance(statement.stmt, ast.AlterTableStmt),
                                "DO block contains unsupported SQL")
                        self.apply(statement.stmt)
                else:
                    if key.startswith("PLpgSQL_stmt_"):
                        require(key in {"PLpgSQL_stmt_block", "PLpgSQL_stmt_if", "PLpgSQL_stmt_return"},
                                "DO block contains unsupported control flow")
                    if key in {"else_body", "elsif_list"}:
                        require(not item, "DO block alternatives need verifier support")
                    self.apply_plpgsql(item)


def trigger_signature(node):
    return (bool(node.isconstraint), bool(node.row), node.timing, node.events,
            strings(node.columns), strings(node.funcname), strings(node.args),
            bool(node.deferrable), bool(node.initdeferred), expression(node.whenClause))


def load_schema(directory=MIGRATIONS):
    result = Schema()
    paths = sorted(directory.iterdir())
    require(bool(paths), "no migrations found")
    for path in paths:
        require(path.is_file() and re.fullmatch(r"\d+_[\w]+\.sql", path.name),
                "unrecognized migration file; update verifier discovery")
        result.files.append(path.name)
        for statement in parse_sql(path.read_text()):
            result.apply(statement.stmt)
    require(bool(result.tables), "migrations define no tables")
    return result


async def inspect_database(connection, expected, schema):
    """Only SELECTs against pg_catalog; caller enforces a read-only transaction."""
    failures = []

    def check(ok, label):
        if not ok:
            failures.append(label)

    tables = {row["relname"] for row in await connection.fetch("""
        SELECT c.relname FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=$1 AND c.relkind IN ('r','p')
    """, schema)}
    columns = await connection.fetch("""
        SELECT c.relname, a.attname, pg_catalog.format_type(a.atttypid,a.atttypmod) AS type,
               a.attnotnull, pg_catalog.pg_get_expr(d.adbin,d.adrelid) AS default_expr
        FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
        WHERE n.nspname=$1 AND a.attnum>0 AND NOT a.attisdropped
    """, schema)
    actual_columns = {}
    for row in columns:
        type_node = parse_sql("CREATE TABLE x (v " + row["type"] + ")")[0].stmt.tableElts[0].typeName
        actual_columns[(row["relname"], row["attname"])] = [
            type_signature(type_node), row["attnotnull"], expression(parsed_expression(row["default_expr"]))]
    constraints = await connection.fetch("""
        SELECT c.relname, k.conname, k.convalidated,
               pg_catalog.pg_get_constraintdef(k.oid) AS definition
        FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid=k.conrelid
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=$1 AND k.contype IN ('p','u','f','c')
    """, schema)
    actual_constraints = {}
    for row in constraints:
        node = parse_sql("ALTER TABLE x ADD " + row["definition"])[0].stmt.cmds[0].def_
        actual_constraints.setdefault(row["relname"], []).append(
            (row["conname"], constraint_signature(node), row["convalidated"]))
    for name, table in expected.tables.items():
        check(name in tables, "table " + name)
        for column, definition in table.columns.items():
            check(actual_columns.get((name, column)) == definition, "column " + name + "." + column)
        available = list(actual_constraints.get(name, []))
        for constraint_name, signature in table.constraints:
            match = next((item for item in available if item[1] == signature and item[2]
                          and (constraint_name is None or item[0] == constraint_name)), None)
            check(match is not None, "constraint " + name + "." + (constraint_name or str(signature[0])))
            if match:
                available.remove(match)
    indexes = await connection.fetch("""
        SELECT i.relname, x.indisvalid, x.indisready, pg_catalog.pg_get_indexdef(i.oid) AS definition
        FROM pg_catalog.pg_index x JOIN pg_catalog.pg_class i ON i.oid=x.indexrelid
        JOIN pg_catalog.pg_namespace n ON n.oid=i.relnamespace WHERE n.nspname=$1
    """, schema)
    actual_indexes = {row["relname"]: row for row in indexes}
    for name, signature in expected.indexes.items():
        row = actual_indexes.get(name)
        check(row is not None and row["indisvalid"] and row["indisready"]
              and index_signature(parse_sql(row["definition"])[0].stmt, schema) == signature, "index " + name)
    # Constraint-backed indexes must also be usable, not merely present by name.
    check(all(row["indisvalid"] and row["indisready"] for row in indexes), "invalid/unready index")
    extensions = {r["extname"] for r in await connection.fetch("SELECT extname FROM pg_catalog.pg_extension")}
    for name in expected.extensions:
        check(name in extensions, "extension " + name)
    enums = await connection.fetch("""
        SELECT t.typname, e.enumlabel FROM pg_catalog.pg_type t
        JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace
        JOIN pg_catalog.pg_enum e ON e.enumtypid=t.oid
        WHERE n.nspname=$1 ORDER BY e.enumsortorder
    """, schema)
    for name, labels in expected.enums.items():
        check(tuple(r["enumlabel"] for r in enums if r["typname"] == name) == labels, "enum " + name)
    functions = await connection.fetch("""
        SELECT p.proname, p.prosrc, l.lanname, pg_catalog.pg_get_function_result(p.oid) AS result,
               p.prosecdef FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
        JOIN pg_catalog.pg_language l ON l.oid=p.prolang
        WHERE n.nspname=$1 AND p.pronargs=0 AND p.prokind='f'
    """, schema)
    for name, definition in expected.functions.items():
        check(any(r["proname"] == name and not r["prosecdef"] and
                  (r["prosrc"].strip(), r["lanname"], r["result"]) == definition for r in functions),
              "function " + name)
    triggers = await connection.fetch("""
        SELECT c.relname, t.tgname, t.tgenabled::text AS tgenabled, pg_catalog.pg_get_triggerdef(t.oid) AS definition
        FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=$1 AND NOT t.tgisinternal
    """, schema)
    for (table, name), signature in expected.triggers.items():
        check(any(r["relname"] == table and r["tgname"] == name and r["tgenabled"] in {"O", "A"}
                  and trigger_signature(parse_sql(r["definition"])[0].stmt) == signature
                  for r in triggers), "trigger " + table + "." + name)
    # This repository applies numbered SQL files directly (CI and staging runbook).
    # Fail closed if a tracking system appears instead of guessing its semantics.
    check(not tables.intersection({"alembic_version", "schema_migrations", "_prisma_migrations",
                                   "flyway_schema_history", "django_migrations"}),
          "migration tracker detected; add its applied-version check to verifier")
    require(not failures, "schema mismatch: " + ", ".join(failures))
    return f"{len(expected.files)} migrations through {expected.files[-1]}; no repo migration tracker"


async def verify_database(env, schema="public"):
    require(bool(re.fullmatch(r"[a-z_][a-z0-9_]*", schema)), "invalid application schema name")
    expected = load_schema()
    dsn = env.get("DATABASE_URL", "")
    require(bool(dsn), "DATABASE_URL is required")
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
    connection = await asyncpg.connect(dsn, timeout=TIMEOUT, command_timeout=TIMEOUT,
        server_settings={"default_transaction_read_only": "on", "statement_timeout": "15000",
                         "lock_timeout": "3000", "search_path": f'pg_catalog, "{schema}"',
                         "application_name": "dopenexa-staging-verifier"})
    try:
        async with connection.transaction(readonly=True, isolation="repeatable_read"):
            return await inspect_database(connection, expected, schema)
    finally:
        await connection.close(timeout=5)


def verify_readiness(client, base_url):
    response = client.get(base_url.rstrip("/") + "/ready")
    require(response.status_code == 200, "expected HTTP 200")
    data = response.json()
    require(isinstance(data, dict) and data.get("status") == "ready", "status is not ready")
    require(data.get("environment") == "staging", "environment is not staging")
    return "HTTP 200; ready; staging"


def verify_storage(client, http, bucket):
    key = "staging-verification/" + uuid4().hex + ".txt"
    content = ("dopenexa-staging-verification:" + uuid4().hex).encode()
    params = {"Bucket": bucket, "Key": key}
    try:
        client.put_object(**params, Body=content, ContentType="text/plain")
        body = client.get_object(**params)["Body"]
        try:
            require(body.read(len(content) + 1) == content, "object read content mismatch")
        finally:
            body.close()
        url = client.generate_presigned_url("get_object", Params=params, ExpiresIn=60)
        # Do not follow redirects or log the signed URL. Bound the read size.
        with http.stream("GET", url) as response:
            require(response.status_code == 200, "presigned GET did not return HTTP 200")
            actual = b""
            for chunk in response.iter_bytes(chunk_size=len(content) + 1):
                actual += chunk
                require(len(actual) <= len(content), "presigned GET content mismatch")
            require(actual == content, "presigned GET content mismatch")
    finally:
        # Also run after a failed/timed-out PUT, which may have stored the object.
        client.delete_object(**params)
        try:
            client.head_object(**params)
        except ClientError as exc:
            require(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404
                    and exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"},
                    "could not confirm object deletion")
        else:
            raise VerificationError("temporary object still exists after deletion")
    return "upload/read/presigned GET/delete/absence verified"


def configured_storage(env):
    require(env.get("STORAGE_BACKEND", "local") != "local", "external STORAGE_BACKEND is required")
    names = ["OBJECT_STORAGE_" + name for name in ("BUCKET", "ENDPOINT", "ACCESS_KEY", "SECRET_KEY")]
    require(all(env.get(name) for name in names), "OBJECT_STORAGE_* configuration is incomplete")
    require(env[names[1]].startswith("https://"), "object storage endpoint must use HTTPS")
    return boto3.client("s3", endpoint_url=env[names[1]], aws_access_key_id=env[names[2]],
        aws_secret_access_key=env[names[3]], region_name=env.get("OBJECT_STORAGE_REGION") or "auto",
        config=Config(signature_version="s3v4", connect_timeout=TIMEOUT, read_timeout=TIMEOUT,
                      retries={"mode": "standard", "total_max_attempts": 2})), env[names[0]]


def run_check(name, operation):
    try:
        detail = operation()
    except VerificationError as exc:
        print(f"FAIL {name}: {exc}")
        return False
    except Exception:
        # SDK/HTTP/database exceptions can contain credentials, DSNs or signed URLs.
        print(f"FAIL {name}: request, configuration, or parsing failed (details suppressed)")
        return False
    print(f"PASS {name}: {detail}")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("STAGING_BASE_URL", "http://127.0.0.1:8000"),
                        help="API base URL; defaults to the Railway backend's loopback listener")
    parser.add_argument("--schema", default="public", help="application PostgreSQL schema (default: public)")
    args = parser.parse_args(argv)
    # Imported SDKs must never emit credentials or presigned URLs at debug level.
    logging.disable(logging.CRITICAL)
    env = os.environ
    with httpx.Client(timeout=TIMEOUT, follow_redirects=False, trust_env=False) as http:
        ready = run_check("readiness", lambda: verify_readiness(http, args.base_url))
        database = run_check("database/migrations", lambda: asyncio.run(verify_database(env, args.schema)))

        def storage():
            require(ready and env.get("ENVIRONMENT") == "staging",
                    "requires staging ENVIRONMENT and successful staging readiness before uploading")
            client, bucket = configured_storage(env)
            try:
                return verify_storage(client, http, bucket)
            finally:
                client.close()

        r2 = run_check("R2", storage)
    return 0 if ready and database and r2 else 1


if __name__ == "__main__":
    sys.exit(main())
