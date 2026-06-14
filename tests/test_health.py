from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.health import HealthService, handle_health_text, parse_health_profile_text
from app.services.ledger import LedgerService, handle_ledger_text
from app.storage.db import Database


class HealthParserTest(unittest.TestCase):
    def test_parse_profile(self) -> None:
        draft = parse_health_profile_text("健康档案：男，32岁，175cm，72kg，目标减脂，膝盖偶尔不舒服，每周能练4天，健身房")

        self.assertEqual(draft.sex, "男")
        self.assertEqual(draft.age, 32)
        self.assertEqual(draft.height_cm, 175)
        self.assertEqual(draft.weight_kg, 72)
        self.assertEqual(draft.goal, "减脂")
        self.assertEqual(draft.workout_days_per_week, 4)
        self.assertIn("膝盖", draft.injuries)
        self.assertIn("健身房", draft.equipment)


class HealthServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "jarvis.db")
        self.db.init()
        self.service = HealthService(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_and_query_profile(self) -> None:
        reply = handle_health_text("健康档案：女，168cm，60kg，目标塑形，每周训练3天，哑铃，少糖", self.service)

        assert reply is not None
        self.assertIn("已创建健康档案", reply)
        self.assertIn("目标塑形", reply)
        self.assertIn("每周训练3天", reply)

        query = handle_health_text("查看健康档案", self.service)
        assert query is not None
        self.assertIn("当前健康档案", query)
        self.assertIn("168cm", query)

    def test_generate_workout_and_meal_plans(self) -> None:
        handle_health_text("健康档案：男，175cm，72kg，目标减脂，膝盖不舒服，每周能练4天，健身房", self.service)

        workout = self.service.create_workout_plan_from_text("帮我生成下周训练课表", now=date(2026, 6, 3))
        assert workout is not None
        self.assertIn("已生成训练课表", workout)
        self.assertIn("2026-06-08 至 2026-06-14", workout)
        self.assertIn("注意 膝盖", workout)

        meal = self.service.create_meal_plan_from_text("生成下周饮食搭配", now=date(2026, 6, 3))
        assert meal is not None
        self.assertIn("已生成饮食搭配", meal)
        self.assertIn("每日蛋白建议", meal)

        latest = handle_health_text("查看最近训练课表", self.service)
        assert latest is not None
        self.assertIn("最近的训练课表", latest)

    def test_checkin_and_query(self) -> None:
        reply = self.service.create_checkin_from_text(
            "健康打卡：体重71.8，睡眠7小时，完成上肢训练，早餐燕麦鸡蛋，疲劳3",
            now=date(2026, 6, 4),
        )

        assert reply is not None
        self.assertIn("已记录健康打卡", reply)
        self.assertIn("体重 71.8kg", reply)
        self.assertIn("训练：上肢训练", reply)

        query = self.service.checkins_reply("今天健康打卡记录", now=date(2026, 6, 4))
        assert query is not None
        self.assertIn("今日健康打卡", query)
        self.assertIn("睡眠 7h", query)

    def test_health_module_does_not_swallow_ledger_expense(self) -> None:
        ledger = LedgerService(self.db)

        health_reply = handle_health_text("今天健身课 100", self.service)
        self.assertIsNone(health_reply)

        ledger_reply = handle_ledger_text("今天健身课 100", ledger)
        assert ledger_reply is not None
        self.assertIn("已记录流水", ledger_reply)
        self.assertIn("分类：健康", ledger_reply)


if __name__ == "__main__":
    unittest.main()
