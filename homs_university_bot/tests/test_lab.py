"""The lab CLI works on its own database and never touches the bot's."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from homs_bot.db import open_store
from homs_bot.lab_cli import main as lab_main
from homs_bot.models import StudentContext


class LabDatabaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = {key: os.environ.get(key) for key in ("HU_DB_PATH", "HU_LAB_DB_PATH")}
        self.tmp = tempfile.TemporaryDirectory()
        self.bot_db = os.path.join(self.tmp.name, "bot.sqlite")
        self.lab_db = os.path.join(self.tmp.name, "lab.sqlite")
        os.environ["HU_DB_PATH"] = self.bot_db
        os.environ["HU_LAB_DB_PATH"] = self.lab_db

    def tearDown(self) -> None:
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, command: str, payload: dict) -> dict:
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), redirect_stdout(out):
            lab_main([command])
        return json.loads(out.getvalue())

    def test_ask_seeds_and_writes_only_the_lab_database(self) -> None:
        bot = open_store(self.bot_db)
        bot.save_context(StudentContext(telegram_user_id=1, faculty_code="medicine"))
        bot.conn.close()

        result = self._run(
            "ask",
            {
                "userId": 1,
                "text": "كيف أوقف تسجيلي",
                "facultyCode": "informatics",
                "academicYear": "2",
                "studySystem": "regular",
                "specializationCode": "software",
                "allowSynthetic": True,
            },
        )
        self.assertEqual(result["outcome"], "answered")
        self.assertTrue(result["synthetic"])

        bot = open_store(self.bot_db)
        self.assertEqual(bot.count_intents(), 0)
        self.assertEqual(bot.list_recent_interactions(), [])
        self.assertEqual(bot.get_context(1).faculty_code, "medicine")
        bot.conn.close()

        lab = open_store(self.lab_db)
        self.assertGreater(lab.count_intents(), 0)
        self.assertEqual(len(lab.list_recent_interactions(1)), 1)
        lab.conn.close()

    def test_delete_does_not_reach_the_bot_database(self) -> None:
        bot = open_store(self.bot_db)
        bot.save_context(StudentContext(telegram_user_id=7, faculty_code="medicine"))
        bot.conn.close()

        self._run("delete", {"userId": 7})

        bot = open_store(self.bot_db)
        self.assertIsNotNone(bot.get_context(7))
        bot.conn.close()

    def test_refuses_to_share_the_bot_database(self) -> None:
        os.environ["HU_LAB_DB_PATH"] = self.bot_db
        with self.assertRaises(SystemExit) as caught, mock.patch("sys.stderr", io.StringIO()):
            self._run("ask", {"userId": 1, "text": "سؤال"})
        self.assertEqual(caught.exception.code, 2)
        self.assertFalse(os.path.exists(self.bot_db))


if __name__ == "__main__":
    unittest.main()
