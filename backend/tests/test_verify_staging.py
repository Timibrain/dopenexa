"""Verifier unit tests; live drift tests require a disposable migrated database."""
import asyncio
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
from botocore.exceptions import ClientError
import httpx
from pglast import parse_sql

from scripts import verify_staging as verify


class MigrationTests(unittest.TestCase):
    def test_discovers_every_repo_migration_and_later_alters(self):
        schema = verify.load_schema()
        self.assertEqual(schema.files, sorted(p.name for p in verify.MIGRATIONS.glob('*.sql')))
        self.assertIn('reconciliation_runs', schema.tables)
        self.assertFalse(schema.tables['payment_events'].columns['processed_at'][1])
        self.assertIn('client_idempotency_key', schema.tables['payments'].columns)
        self.assertEqual(schema.extensions, {'vector', 'pgcrypto'})
        self.assertIn(('ledger_entries', 'ledger_entries_balanced'), schema.triggers)
        self.assertTrue(any(n == 'payments_currency_check' for n, _ in schema.tables['payments'].constraints))

    def test_new_files_are_discovered_and_unknown_ddl_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '001_first.sql').write_text('CREATE TABLE a(id int PRIMARY KEY);')
            (root / '002_next.sql').write_text('ALTER TABLE a ADD COLUMN x text;')
            self.assertIn('x', verify.load_schema(root).tables['a'].columns)
            (root / '003_unknown.sql').write_text('CREATE VIEW v AS SELECT * FROM a;')
            with self.assertRaisesRegex(verify.VerificationError, 'unsupported migration statement'):
                verify.load_schema(root)

    def test_do_block_dynamic_sql_rejected(self):
        schema = verify.Schema()
        with self.assertRaises(verify.VerificationError):
            schema.apply(parse_sql("DO $$ BEGIN EXECUTE 'CREATE TABLE sneaky(id int)'; END $$")[0].stmt)

    def test_expression_catalog_rewrites_preserve_semantics(self):
        pairs = [
            ("status IN ('pending','paid')", "status::text = ANY (ARRAY['pending'::varchar,'paid'::varchar]::text[])"),
            ('rating BETWEEN 1 AND 5', 'rating >= 1 AND rating <= 5'),
            ("'NGN'", "'NGN'::bpchar"),
        ]
        for left, right in pairs:
            self.assertEqual(verify.expression(verify.parsed_expression(left)),
                             verify.expression(verify.parsed_expression(right)))
        self.assertNotEqual(verify.expression(verify.parsed_expression("currency='NGN'")),
                            verify.expression(verify.parsed_expression("currency='ngn'")))

    def test_index_definition_includes_uniqueness_predicate_and_order(self):
        def signature(sql):
            return verify.index_signature(parse_sql(sql)[0].stmt)
        original = signature('CREATE UNIQUE INDEX i ON a(x, y DESC) WHERE x IS NOT NULL')
        for statement in [
            'CREATE INDEX i ON a(x, y DESC) WHERE x IS NOT NULL',
            'CREATE UNIQUE INDEX i ON a(x, y DESC)',
            'CREATE UNIQUE INDEX i ON a(x, y) WHERE x IS NOT NULL',
            'CREATE UNIQUE INDEX i ON a(y DESC, x) WHERE x IS NOT NULL',
        ]:
            self.assertNotEqual(original, signature(statement))


class ReadinessTests(unittest.TestCase):
    def test_readiness_requires_all_three_conditions(self):
        for status, data, success in [
            (200, {'status': 'ready', 'environment': 'staging'}, True),
            (503, {'status': 'ready', 'environment': 'staging'}, False),
            (200, {'status': 'ok', 'environment': 'staging'}, False),
            (200, {'status': 'ready', 'environment': 'production'}, False),
            (200, [], False),
        ]:
            with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status, json=data))) as client:
                if success:
                    verify.verify_readiness(client, 'https://staging.example/')
                else:
                    with self.assertRaises(verify.VerificationError):
                        verify.verify_readiness(client, 'https://staging.example/')

    def test_exceptions_do_not_print_secrets(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = verify.run_check('R2', lambda: (_ for _ in ()).throw(RuntimeError('SECRET_ACCESS_KEY')))
        self.assertFalse(result)
        self.assertNotIn('SECRET_ACCESS_KEY', output.getvalue())

    def test_main_summarizes_every_check_and_gates_storage_on_staging(self):
        output = io.StringIO()
        with patch.dict(os.environ, {'ENVIRONMENT': 'staging'}), \
             patch.object(verify, 'verify_readiness', side_effect=verify.VerificationError('not staging')), \
             patch.object(verify, 'verify_database', new=AsyncMock(return_value='schema OK')), \
             patch.object(verify, 'configured_storage') as storage, redirect_stdout(output):
            self.assertEqual(verify.main([]), 1)
        storage.assert_not_called()
        self.assertIn('FAIL readiness', output.getvalue())
        self.assertIn('PASS database/migrations', output.getvalue())
        self.assertIn('FAIL R2', output.getvalue())


class FakeS3:
    def __init__(self, failure=None):
        self.failure = failure
        self.content = None
        self.keys = []
        self.deleted = False
        self.body = None

    def put_object(self, **kwargs):
        self.keys.append(kwargs['Key'])
        self.content = kwargs['Body']
        if self.failure == 'put':
            raise TimeoutError('upload may have succeeded')

    def get_object(self, **kwargs):
        if self.failure == 'get':
            raise RuntimeError('get failed')
        self.body = io.BytesIO(b'wrong' if self.failure == 'content' else self.content)
        return {'Body': self.body}

    def generate_presigned_url(self, *args, **kwargs):
        if self.failure == 'sign':
            raise RuntimeError('sign failed')
        return 'https://objects.example/presigned?signature=SECRET'

    def delete_object(self, **kwargs):
        self.deleted = True
        if self.failure == 'delete':
            raise RuntimeError('delete failed')

    def head_object(self, **kwargs):
        if self.failure == 'still_exists':
            return {}
        forbidden = self.failure == 'head_forbidden'
        raise ClientError({'Error': {'Code': 'AccessDenied' if forbidden else '404'},
                           'ResponseMetadata': {'HTTPStatusCode': 403 if forbidden else 404}}, 'HeadObject')


class StorageTests(unittest.TestCase):
    def exercise(self, failure=None):
        client = FakeS3(failure)
        def handler(request):
            if failure == 'http':
                return httpx.Response(403, content=b'denied')
            return httpx.Response(200, content=b'wrong' if failure == 'http_content' else client.content)
        try:
            with httpx.Client(transport=httpx.MockTransport(handler)) as http:
                verify.verify_storage(client, http, 'bucket')
        finally:
            self.assertTrue(client.deleted)
            if client.body:
                self.assertTrue(client.body.closed)
        return client

    def test_round_trip_uses_unique_keys_and_deletes(self):
        first, second = self.exercise(), self.exercise()
        self.assertNotEqual(first.keys, second.keys)
        self.assertTrue(first.keys[0].startswith('staging-verification/'))

    def test_all_failures_fail_and_attempt_cleanup(self):
        for failure in ['put', 'get', 'content', 'sign', 'http', 'http_content',
                        'delete', 'still_exists', 'head_forbidden']:
            with self.subTest(failure=failure), self.assertRaises(Exception):
                self.exercise(failure)


class DatabaseConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_enforces_read_only_transaction_and_closes_on_failure(self):
        connection = MagicMock()
        connection.close = AsyncMock()
        connection.transaction.return_value.__aenter__ = AsyncMock()
        connection.transaction.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch.object(verify.asyncpg, 'connect', new=AsyncMock(return_value=connection)) as connect, \
             patch.object(verify, 'inspect_database', new=AsyncMock(side_effect=RuntimeError('failure'))):
            with self.assertRaises(RuntimeError):
                await verify.verify_database({'DATABASE_URL': 'postgresql+asyncpg://user:password@localhost/db'})
        self.assertEqual(connect.call_args.args[0], 'postgresql://user:password@localhost/db')
        self.assertEqual(connect.call_args.kwargs['server_settings']['default_transaction_read_only'], 'on')
        connection.transaction.assert_called_once_with(readonly=True, isolation='repeatable_read')
        connection.close.assert_awaited_once()


@unittest.skipUnless(os.environ.get('VERIFIER_TEST_DATABASE_URL'), 'requires disposable migrated PostgreSQL')
class LiveSchemaTests(unittest.IsolatedAsyncioTestCase):
    """Never point VERIFIER_TEST_DATABASE_URL at staging: these tests inject drift.

    Every change is rolled back; the verification script itself never runs DDL.
    """
    async def test_fully_migrated_database_passes(self):
        result = await verify.verify_database({'DATABASE_URL': os.environ['VERIFIER_TEST_DATABASE_URL']})
        self.assertIn(verify.load_schema().files[-1], result)

    async def test_drift_is_detected(self):
        connection = await asyncpg.connect(os.environ['VERIFIER_TEST_DATABASE_URL'],
                                          server_settings={'search_path': 'pg_catalog, public'})
        mutations = [
            ('ALTER TABLE reconciliation_runs RENAME TO missing_table', 'table reconciliation_runs'),
            ('ALTER TABLE payouts DROP COLUMN dopenexa_reference', 'column payouts.dopenexa_reference'),
            ('ALTER TABLE users ALTER COLUMN email TYPE varchar(319)', 'column users.email'),
            ('ALTER TABLE users ALTER COLUMN email DROP NOT NULL', 'column users.email'),
            ("ALTER TABLE users ALTER COLUMN is_active SET DEFAULT false", 'column users.is_active'),
            ('DROP INDEX refunds_provider_reference_idx', 'index refunds_provider_reference_idx'),
            ('DROP INDEX refunds_provider_reference_idx; CREATE INDEX refunds_provider_reference_idx ON public.refunds(provider_reference)',
             'index refunds_provider_reference_idx'),
            ('ALTER TABLE payments DROP CONSTRAINT payments_status_check; ALTER TABLE payments ADD CONSTRAINT payments_status_check CHECK (status IS NOT NULL)',
             'constraint payments.payments_status_check'),
            ('ALTER TABLE payments DROP CONSTRAINT payments_currency_check; ALTER TABLE payments ADD CONSTRAINT payments_currency_check CHECK (currency=\'NGN\') NOT VALID',
             'constraint payments.payments_currency_check'),
            ('ALTER TABLE messages DROP CONSTRAINT messages_sender_id_fkey', 'constraint messages.CONSTR_FOREIGN'),
            ('DROP EXTENSION vector CASCADE', 'extension vector'),
            ('ALTER TYPE user_role ADD VALUE \'unexpected\'', 'enum user_role'),
            ('ALTER TABLE ledger_entries DISABLE TRIGGER ledger_entries_balanced', 'trigger ledger_entries.ledger_entries_balanced'),
            ("CREATE OR REPLACE FUNCTION public.dopenexa_ledger_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$", 'function dopenexa_ledger_immutable'),
        ]
        try:
            for statement, message in mutations:
                with self.subTest(statement=statement):
                    transaction = connection.transaction()
                    await transaction.start()
                    try:
                        await connection.execute(statement)
                        with self.assertRaises(verify.VerificationError) as caught:
                            await verify.inspect_database(connection, verify.load_schema(), 'public')
                        self.assertIn(message, str(caught.exception))
                    finally:
                        await transaction.rollback()
        finally:
            await connection.close()
