from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.storage.db import Database


@dataclass(frozen=True)
class HealthProfileDraft:
    sex: str | None
    age: int | None
    height_cm: float | None
    weight_kg: float | None
    goal: str
    workout_days_per_week: int | None
    equipment: str
    injuries: str
    diet_preferences: str
    source_text: str


@dataclass(frozen=True)
class HealthProfile:
    sex: str | None
    age: int | None
    height_cm: float | None
    weight_kg: float | None
    goal: str
    workout_days_per_week: int | None
    equipment: str
    injuries: str
    diet_preferences: str


@dataclass(frozen=True)
class HealthPlan:
    id: int
    plan_type: str
    title: str
    start_date: str
    end_date: str
    content: str


class HealthService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def upsert_profile_from_text(self, text: str) -> str | None:
        if "健康档案" not in text or _looks_like_profile_query(text):
            return None

        draft = parse_health_profile_text(text)
        if not _has_any_profile_field(draft):
            return "请补充一些健康档案信息，例如：健康档案：男，175cm，72kg，目标减脂，每周能练4天。"

        with self.db.connect() as conn:
            existing = conn.execute(
                """
                SELECT sex, age, height_cm, weight_kg, goal, workout_days_per_week,
                    equipment, injuries, diet_preferences, source_text
                FROM health_profile
                WHERE id = 1
                """
            ).fetchone()
            conn.execute(
                """
                INSERT INTO health_profile (
                    id, sex, age, height_cm, weight_kg, goal, workout_days_per_week,
                    equipment, injuries, diet_preferences, source_text
                )
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id)
                DO UPDATE SET
                    sex = COALESCE(excluded.sex, health_profile.sex),
                    age = COALESCE(excluded.age, health_profile.age),
                    height_cm = COALESCE(excluded.height_cm, health_profile.height_cm),
                    weight_kg = COALESCE(excluded.weight_kg, health_profile.weight_kg),
                    goal = CASE WHEN excluded.goal != '' THEN excluded.goal ELSE health_profile.goal END,
                    workout_days_per_week = COALESCE(
                        excluded.workout_days_per_week,
                        health_profile.workout_days_per_week
                    ),
                    equipment = CASE
                        WHEN excluded.equipment != '' THEN excluded.equipment
                        ELSE health_profile.equipment
                    END,
                    injuries = CASE
                        WHEN excluded.injuries != '' THEN excluded.injuries
                        ELSE health_profile.injuries
                    END,
                    diet_preferences = CASE
                        WHEN excluded.diet_preferences != '' THEN excluded.diet_preferences
                        ELSE health_profile.diet_preferences
                    END,
                    source_text = excluded.source_text,
                    updated_at = datetime('now')
                """,
                (
                    draft.sex,
                    draft.age,
                    draft.height_cm,
                    draft.weight_kg,
                    draft.goal,
                    draft.workout_days_per_week,
                    draft.equipment,
                    draft.injuries,
                    draft.diet_preferences,
                    draft.source_text,
                ),
            )
        action = "已更新健康档案" if existing else "已创建健康档案"
        profile = self.profile()
        assert profile is not None
        return f"{action}：{_format_profile(profile)}"

    def profile(self) -> HealthProfile | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT sex, age, height_cm, weight_kg, goal, workout_days_per_week,
                    equipment, injuries, diet_preferences
                FROM health_profile
                WHERE id = 1
                """
            ).fetchone()
        if not row:
            return None
        return HealthProfile(
            sex=row["sex"],
            age=int(row["age"]) if row["age"] is not None else None,
            height_cm=float(row["height_cm"]) if row["height_cm"] is not None else None,
            weight_kg=float(row["weight_kg"]) if row["weight_kg"] is not None else None,
            goal=str(row["goal"] or ""),
            workout_days_per_week=int(row["workout_days_per_week"])
            if row["workout_days_per_week"] is not None
            else None,
            equipment=str(row["equipment"] or ""),
            injuries=str(row["injuries"] or ""),
            diet_preferences=str(row["diet_preferences"] or ""),
        )

    def profile_reply(self) -> str | None:
        if not self.profile():
            return "还没有健康档案。你可以说：健康档案：男，175cm，72kg，目标减脂，每周能练4天。"
        return f"当前健康档案：{_format_profile(self.profile())}"

    def create_workout_plan_from_text(self, text: str, now: date | None = None) -> str | None:
        if not _looks_like_workout_plan(text):
            return None
        profile = self.profile()
        if not profile:
            return "我需要先知道你的基础情况。你可以先发：健康档案：身高、体重、目标、每周能练几天、伤病限制。"

        start = _plan_start_date(text, now or date.today())
        end = start + timedelta(days=6)
        content = _build_workout_plan(profile, start)
        plan = self._save_plan(
            plan_type="workout",
            title=f"{start.isoformat()} 训练课表",
            start_date=start,
            end_date=end,
            content=content,
            source_text=text,
        )
        return f"已生成训练课表 #{plan.id}（{plan.start_date} 至 {plan.end_date}）：\n{plan.content}"

    def create_meal_plan_from_text(self, text: str, now: date | None = None) -> str | None:
        if not _looks_like_meal_plan(text):
            return None
        profile = self.profile()
        if not profile:
            return "我需要先知道你的基础情况。你可以先发：健康档案：身高、体重、目标、忌口或饮食偏好。"

        start = _plan_start_date(text, now or date.today())
        end = start + timedelta(days=6)
        content = _build_meal_plan(profile)
        plan = self._save_plan(
            plan_type="meal",
            title=f"{start.isoformat()} 饮食搭配",
            start_date=start,
            end_date=end,
            content=content,
            source_text=text,
        )
        return f"已生成饮食搭配 #{plan.id}（{plan.start_date} 至 {plan.end_date}）：\n{plan.content}"

    def create_checkin_from_text(self, text: str, now: date | None = None) -> str | None:
        if not _looks_like_checkin(text):
            return None

        checkin_date = _detect_checkin_date(text, now or date.today())
        weight = _extract_weight(text)
        sleep = _extract_sleep(text)
        fatigue = _extract_fatigue(text)
        workout = _extract_workout_done(text)
        meals = _extract_meal_notes(text)
        mood = _extract_mood(text)
        if weight is None and sleep is None and not workout and not meals and fatigue is None and not mood:
            return "这条打卡里还缺少可记录的信息。可以写：健康打卡：体重72.1，睡眠7小时，完成上肢训练。"

        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO health_checkins (
                    checkin_date, weight_kg, sleep_hours, workout_done,
                    meal_notes, fatigue_level, mood, source_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkin_date.isoformat(),
                    weight,
                    sleep,
                    workout,
                    meals,
                    fatigue,
                    mood,
                    text.strip(),
                ),
            )
            checkin_id = int(cursor.lastrowid)

        parts = [f"已记录健康打卡 #{checkin_id}：{checkin_date.isoformat()}"]
        if weight is not None:
            parts.append(f"体重 {weight:g}kg")
        if sleep is not None:
            parts.append(f"睡眠 {sleep:g} 小时")
        if workout:
            parts.append(f"训练：{workout}")
        if meals:
            parts.append(f"饮食：{meals}")
        if fatigue is not None:
            parts.append(f"疲劳 {fatigue}/10")
        if mood:
            parts.append(f"状态：{mood}")
        return "，".join(parts) + "。"

    def latest_plan_reply(self, text: str) -> str | None:
        if not _looks_like_plan_query(text):
            return None
        plan_type = "meal" if "饮食" in text or "食谱" in text else "workout"
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, plan_type, title, start_date, end_date, content
                FROM health_plans
                WHERE plan_type = ?
                ORDER BY start_date DESC, id DESC
                LIMIT 1
                """,
                (plan_type,),
            ).fetchone()
        if not row:
            label = "饮食搭配" if plan_type == "meal" else "训练课表"
            return f"还没有{label}。你可以说：生成下周{label}。"
        label = "饮食搭配" if plan_type == "meal" else "训练课表"
        return f"最近的{label} #{row['id']}（{row['start_date']} 至 {row['end_date']}）：\n{row['content']}"

    def checkins_reply(self, text: str, now: date | None = None) -> str | None:
        if not _looks_like_checkin_query(text):
            return None
        now = now or date.today()
        params: list[object] = []
        where = "1 = 1"
        title = "最近健康打卡"
        if "今天" in text or "今日" in text:
            where = "checkin_date = ?"
            params.append(now.isoformat())
            title = "今日健康打卡"
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, checkin_date, weight_kg, sleep_hours, workout_done,
                    meal_notes, fatigue_level, mood
                FROM health_checkins
                WHERE {where}
                ORDER BY checkin_date DESC, id DESC
                LIMIT 7
                """,
                params,
            ).fetchall()
        if not rows:
            return f"{title}为空。"
        lines = [f"{title}："]
        for row in rows:
            details = []
            if row["weight_kg"] is not None:
                details.append(f"体重 {float(row['weight_kg']):g}kg")
            if row["sleep_hours"] is not None:
                details.append(f"睡眠 {float(row['sleep_hours']):g}h")
            if row["workout_done"]:
                details.append(f"训练 {row['workout_done']}")
            if row["meal_notes"]:
                details.append(f"饮食 {row['meal_notes']}")
            if row["fatigue_level"] is not None:
                details.append(f"疲劳 {row['fatigue_level']}/10")
            if row["mood"]:
                details.append(f"状态 {row['mood']}")
            lines.append(f"- #{row['id']} {row['checkin_date']} " + "，".join(details))
        return "\n".join(lines)

    def _save_plan(
        self,
        *,
        plan_type: str,
        title: str,
        start_date: date,
        end_date: date,
        content: str,
        source_text: str,
    ) -> HealthPlan:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO health_plans (plan_type, title, start_date, end_date, content, source_text)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_type,
                    title,
                    start_date.isoformat(),
                    end_date.isoformat(),
                    content,
                    source_text.strip(),
                ),
            )
            plan_id = int(cursor.lastrowid)
        return HealthPlan(
            id=plan_id,
            plan_type=plan_type,
            title=title,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            content=content,
        )


def handle_health_text(text: str, service: HealthService) -> str | None:
    if text.strip() in {"健康帮助", "健康模块帮助"}:
        return (
            "健康模块支持：健康档案、生成训练课表、生成饮食搭配、健康打卡、查询最近健康打卡。"
        )

    if _looks_like_profile_query(text):
        return service.profile_reply()

    profile_reply = service.upsert_profile_from_text(text)
    if profile_reply:
        return profile_reply

    checkins = service.checkins_reply(text)
    if checkins:
        return checkins

    latest_plan = service.latest_plan_reply(text)
    if latest_plan:
        return latest_plan

    checkin = service.create_checkin_from_text(text)
    if checkin:
        return checkin

    workout = service.create_workout_plan_from_text(text)
    if workout:
        return workout

    meal = service.create_meal_plan_from_text(text)
    if meal:
        return meal

    return None


def parse_health_profile_text(text: str) -> HealthProfileDraft:
    stripped = text.strip()
    return HealthProfileDraft(
        sex=_extract_sex(stripped),
        age=_extract_age(stripped),
        height_cm=_extract_height(stripped),
        weight_kg=_extract_weight(stripped),
        goal=_extract_goal(stripped),
        workout_days_per_week=_extract_workout_days(stripped),
        equipment=_extract_equipment(stripped),
        injuries=_extract_injuries(stripped),
        diet_preferences=_extract_diet_preferences(stripped),
        source_text=stripped,
    )


def _looks_like_profile_query(text: str) -> bool:
    return "健康档案" in text and any(token in text for token in ["我的", "查看", "查询", "当前", "是什么"])


def _looks_like_workout_plan(text: str) -> bool:
    return any(token in text for token in ["训练", "运动"]) and any(
        token in text for token in ["课表", "计划", "安排"]
    ) and any(token in text for token in ["生成", "制定", "安排", "帮我", "给我"])


def _looks_like_meal_plan(text: str) -> bool:
    return any(token in text for token in ["饮食", "食谱", "吃饭"]) and any(
        token in text for token in ["搭配", "计划", "安排", "生成", "制定"]
    )


def _looks_like_checkin(text: str) -> bool:
    if any(token in text for token in ["健康打卡", "训练打卡", "饮食打卡"]):
        return True
    return "打卡" in text and any(token in text for token in ["体重", "睡眠", "训练", "早餐", "午餐", "晚餐"])


def _looks_like_checkin_query(text: str) -> bool:
    return any(token in text for token in ["健康打卡", "健康记录", "打卡记录"]) and any(
        token in text for token in ["最近", "今天", "今日", "查询", "查看"]
    )


def _looks_like_plan_query(text: str) -> bool:
    return any(token in text for token in ["最近", "当前", "查看", "查询"]) and any(
        token in text for token in ["训练课表", "训练计划", "运动计划", "饮食搭配", "饮食计划", "食谱"]
    )


def _has_any_profile_field(draft: HealthProfileDraft) -> bool:
    return any(
        [
            draft.sex,
            draft.age is not None,
            draft.height_cm is not None,
            draft.weight_kg is not None,
            draft.goal,
            draft.workout_days_per_week is not None,
            draft.equipment,
            draft.injuries,
            draft.diet_preferences,
        ]
    )


def _extract_sex(text: str) -> str | None:
    if re.search(r"(?<![男女])男(?![男女])|男性", text):
        return "男"
    if re.search(r"(?<![男女])女(?![男女])|女性", text):
        return "女"
    return None


def _extract_age(text: str) -> int | None:
    match = re.search(r"(\d{1,3})\s*岁", text)
    return int(match.group(1)) if match else None


def _extract_height(text: str) -> float | None:
    match = re.search(r"(\d{2,3}(?:\.\d+)?)\s*(?:cm|厘米)", text, flags=re.IGNORECASE)
    return float(match.group(1)) if match else None


def _extract_weight(text: str) -> float | None:
    match = re.search(r"体重\s*(\d{2,3}(?:\.\d+)?)\s*(?:kg|公斤|千克)?", text, flags=re.IGNORECASE)
    if match:
        return float(match.group(1))
    match = re.search(r"(\d{2,3}(?:\.\d+)?)\s*(?:kg|公斤|千克)", text, flags=re.IGNORECASE)
    return float(match.group(1)) if match else None


def _extract_goal(text: str) -> str:
    match = re.search(r"目标\s*([\u4e00-\u9fa5A-Za-z0-9_-]{2,20})", text)
    if match:
        return match.group(1).strip(" ：:，,。")
    for goal in ["减脂", "降体脂", "增肌", "塑形", "维持", "提升体能", "改善体能", "控制血糖"]:
        if goal in text:
            return goal
    return ""


def _extract_workout_days(text: str) -> int | None:
    match = re.search(r"(?:每周|一周|周)\s*(?:能练|训练|运动|练)?\s*(\d)\s*天", text)
    if match:
        return int(match.group(1))
    cn_numbers = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}
    match = re.search(r"(?:每周|一周|周)\s*(?:能练|训练|运动|练)?\s*([一二两三四五六七])\s*天", text)
    return cn_numbers[match.group(1)] if match else None


def _extract_equipment(text: str) -> str:
    matches = []
    for token in ["健身房", "哑铃", "杠铃", "跑步机", "椭圆机", "瑜伽垫", "自重", "家里练", "无器械"]:
        if token in text:
            matches.append(token)
    return "、".join(matches)


def _extract_injuries(text: str) -> str:
    match = re.search(r"(?:伤病|限制|不舒服|疼痛)[:：]?\s*([^，。,.]+)", text)
    if match:
        return match.group(1).strip()
    matches = []
    for token in ["膝盖", "腰", "肩", "脚踝", "手腕"]:
        if token in text and any(word in text for word in ["疼", "痛", "不舒服", "伤"]):
            matches.append(token)
    return "、".join(matches)


def _extract_diet_preferences(text: str) -> str:
    match = re.search(r"(?:忌口|饮食偏好|不吃|少吃)[:：]?\s*([^，。,.]+)", text)
    if match:
        return match.group(1).strip()
    matches = []
    for token in ["素食", "低碳", "高蛋白", "不吃辣", "乳糖不耐", "少油", "少糖"]:
        if token in text:
            matches.append(token)
    return "、".join(matches)


def _extract_sleep(text: str) -> float | None:
    match = re.search(r"睡眠\s*(\d+(?:\.\d+)?)\s*(?:小时|h)?", text, flags=re.IGNORECASE)
    return float(match.group(1)) if match else None


def _extract_fatigue(text: str) -> int | None:
    match = re.search(r"疲劳\s*(\d{1,2})", text)
    if not match:
        return None
    return max(1, min(10, int(match.group(1))))


def _extract_workout_done(text: str) -> str:
    match = re.search(r"(?:完成|做了|练了)\s*([^，。,.]+)", text)
    if match:
        return match.group(1).strip()
    return "未训练" if "没练" in text or "休息" in text else ""


def _extract_meal_notes(text: str) -> str:
    segments = []
    for label in ["早餐", "午餐", "晚餐", "加餐"]:
        match = re.search(label + r"[:：]?\s*([^，。,.]+)", text)
        if match:
            segments.append(f"{label}{match.group(1).strip()}")
    return "；".join(segments)


def _extract_mood(text: str) -> str:
    match = re.search(r"(?:状态|心情|精神)[:：]?\s*([^，。,.]+)", text)
    return match.group(1).strip() if match else ""


def _detect_checkin_date(text: str, today: date) -> date:
    if "昨天" in text:
        return today - timedelta(days=1)
    if "前天" in text:
        return today - timedelta(days=2)
    return today


def _plan_start_date(text: str, today: date) -> date:
    if "下周" in text:
        days_until_next_monday = (7 - today.weekday()) % 7
        days_until_next_monday = 7 if days_until_next_monday == 0 else days_until_next_monday
        return today + timedelta(days=days_until_next_monday)
    if "本周" in text or "这周" in text:
        return today - timedelta(days=today.weekday())
    return today


def _build_workout_plan(profile: HealthProfile, start: date) -> str:
    days = max(2, min(6, profile.workout_days_per_week or 3))
    goal = profile.goal or "提升体能"
    low_impact = any(token in profile.injuries for token in ["膝", "脚踝"])
    cardio = "椭圆机/骑车 25 分钟" if low_impact else "慢跑或快走 30 分钟"
    strength_focus = "力量训练优先，配合温和有氧" if goal in {"减脂", "降体脂", "塑形"} else "力量渐进超负荷优先"
    sessions = [
        ("全身力量 A", "深蹲或腿举 3x8-10，卧推/俯卧撑 3x8-12，划船 3x10，核心 8 分钟"),
        ("有氧与灵活性", f"{cardio}，髋/胸椎活动 10 分钟"),
        ("全身力量 B", "硬拉变式 3x6-8，肩推 3x8-10，下拉 3x10，臀桥 3x12"),
        ("恢复训练", "拉伸 15 分钟，轻松步行 30 分钟"),
        ("力量循环", "弓步或台阶 3x10，哑铃推举 3x10，划船 3x12，平板支撑 3 组"),
        ("低强度有氧", f"{cardio}，结束后拉伸 10 分钟"),
    ]
    lines = [f"原则：{strength_focus}；每次训练前热身 8-10 分钟。"]
    if profile.injuries:
        lines.append(f"限制：注意 {profile.injuries}，疼痛动作降级或跳过。")
    for index in range(days):
        current = start + timedelta(days=index * max(1, 6 // max(1, days - 1)) if days > 1 else 0)
        name, detail = sessions[index]
        lines.append(f"- {current.strftime('%m-%d')} {name}：{detail}")
    lines.append("如果出现胸痛、明显眩晕或持续疼痛，停止训练并寻求专业帮助。")
    return "\n".join(lines)


def _build_meal_plan(profile: HealthProfile) -> str:
    weight = profile.weight_kg or 70
    protein_low = round(weight * 1.4)
    protein_high = round(weight * 1.8)
    goal = profile.goal or "均衡饮食"
    carb_note = "训练日前后保留主食" if goal in {"减脂", "降体脂", "塑形"} else "每餐保留足量主食支持训练"
    preference = f"；避开/偏好：{profile.diet_preferences}" if profile.diet_preferences else ""
    lines = [
        f"目标：{goal}；每日蛋白建议约 {protein_low}-{protein_high}g{preference}。",
        f"早餐：优先蛋白 + 慢碳水，例如鸡蛋/酸奶 + 燕麦/全麦 + 水果。",
        f"午餐：一掌心蛋白、半盘蔬菜、一拳主食；{carb_note}。",
        "晚餐：蛋白和蔬菜优先，主食按当天训练量调整。",
        "加餐：无糖酸奶、蛋白奶、坚果或水果，避免把加餐变成零食补偿。",
        "饮水：全天分散喝水，训练日额外补 500-800ml。",
    ]
    return "\n".join(lines)


def _format_profile(profile: HealthProfile | None) -> str:
    if profile is None:
        return "暂无"
    parts = []
    if profile.sex:
        parts.append(profile.sex)
    if profile.age is not None:
        parts.append(f"{profile.age}岁")
    if profile.height_cm is not None:
        parts.append(f"{profile.height_cm:g}cm")
    if profile.weight_kg is not None:
        parts.append(f"{profile.weight_kg:g}kg")
    if profile.goal:
        parts.append(f"目标{profile.goal}")
    if profile.workout_days_per_week is not None:
        parts.append(f"每周训练{profile.workout_days_per_week}天")
    if profile.equipment:
        parts.append(f"器械：{profile.equipment}")
    if profile.injuries:
        parts.append(f"限制：{profile.injuries}")
    if profile.diet_preferences:
        parts.append(f"饮食：{profile.diet_preferences}")
    return "，".join(parts) if parts else "暂无详细信息"
