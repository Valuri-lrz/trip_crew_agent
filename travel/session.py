"""会话：状态机 + 存储。

阶段：
  0 刚打开
  1 已出画像和候选，等用户说"就这个"或"换"
  2 已出行程，之后每句话都是调整或提问

没有点位库了：目的地和点位都靠模型现生成。会话里存一份点位池，
下雨换点、换一个，都从这份池子里取。
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from travel import adjust as adjust_mod
from travel import agents, engine, live, pipeline
from travel.config import get_settings
from travel.schemas import DestinationCard, Reply, Session
from travel.storage import writable_dir

GREETING = ("你好，我是你的旅行搭子。一句话就行：几个人、想去哪、玩几天？"
            "有喜欢的图也可以直接拖进来。")

AGREE_WORDS = ("行", "可以", "好啊", "好", "嗯", "就这", "听你", "你定", "都行", "随便", "第一个", "1")
OTHER_WORDS = ("换", "别的", "别的地方", "不要", "再看看", "不喜欢", "换一个")


class Store:
    """会话存 SQLite，进程重启也不丢。目录不可写时自动退到临时目录。"""

    def __init__(self, path: Path):
        self.dir = writable_dir(path.parent)
        self.path = self.dir / path.name
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS sessions ("
                      "id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT)")

    def _conn(self):
        return sqlite3.connect(self.path)

    def save(self, s: Session) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO sessions (id, data, updated_at) VALUES (?,?,datetime('now')) "
                      "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                      (s.id, s.model_dump_json()))

    def get(self, sid: str) -> Session | None:
        with self._conn() as c:
            row = c.execute("SELECT data FROM sessions WHERE id=?", (sid,)).fetchone()
        return Session.model_validate(json.loads(row[0])) if row else None


_store: Store | None = None


def store() -> Store:
    global _store
    if _store is None:
        _store = Store(get_settings().db_path)
    return _store


def _mode() -> str:
    return "llm" if get_settings().llm_ready else "demo"


def new_session() -> tuple[Session, Reply]:
    s = Session(id=uuid.uuid4().hex[:12])
    store().save(s)
    return s, Reply(session_id=s.id, stage=0, text=GREETING, mode=_mode())


# ------------------------------------------------------------------ 入口
def handle_text(sid: str, text: str, images: list[str]) -> Reply:
    s = store().get(sid)
    if s is None:
        return new_session()[1]

    text = (text or "").strip()
    s.text_input = (s.text_input + " " + text).strip()
    s.images = images or s.images

    if s.stage == 1:
        return _handle_choice(s, text)

    if s.stage >= 2 and s.itinerary:
        kind = _adjust_kind(text)
        if kind:
            return apply_adjust(sid, kind, _day_number(text))
        if _is_question(text):
            answer = _lookup(s, text)
            if answer:
                return answer
        return Reply(session_id=s.id, stage=s.stage,
                     text="这句我先记下。想改直接说：\n"
                          "· 「第 2 天太赶」·「下雨了」·「好累，少排一个」",
                     itinerary=s.itinerary, mode=_mode())

    return _intake(s)


# ------------------------------------------------------------------ 第一轮
def _intake(s: Session) -> Reply:
    brief = engine.extract_brief(s.text_input)
    s.people, s.days, s.month = brief["people"], brief["days"], brief["month"]

    # 读人 和 写点位 并行：它们互不依赖，串着跑要多等一倍
    got, plan = pipeline.intake_parallel(s.text_input, s.images, s.days)
    s.profiles, s.stage = got.profiles, 1
    p0 = got.profiles[0] if got.profiles else None

    # 1) 已经认出城市并把点位写好了 → 直接出行程
    if plan:
        city = plan[0].dest.name
        return _finish_plan(s, plan, got.opening, f"行，{city}。", got.clarify)

    # 1b) 认出了城市但点位没出来 → 补一次
    if got.city_hint:
        plan = pipeline.build_plan_for(got.city_hint, got.profiles, s.days)
        if plan:
            return _finish_plan(s, plan, got.opening, f"行，{got.city_hint}。", got.clarify)

    # 2) 图里是远地方，先问一句
    if p0 and p0.far and not s.domestic_forced:
        s.cards = []
        store().save(s)
        where = p0.place_guess or "这种地方"
        seen = "、".join(p0.tags[:3])
        text = (f"这是**{where}**吧——{seen}。\n\n"
                f"两条路：\n"
                f"① **在国内找这个感觉**：我给你几个像的\n"
                f"② **就排这里**：我按记忆现写点位直接排，但全都没核实\n\n"
                f"想走哪条？")
        return Reply(session_id=s.id, stage=1, text=text, cards=[],
                     profiles=got.profiles, mode=got.mode)

    # 3) 正常推荐
    s.cards = got.cards
    store().save(s)
    head = got.opening or (p0.summary if p0 else "")
    if not s.cards:
        return Reply(session_id=s.id, stage=1, mode=got.mode,
                     text=(head + "\n\n我这会儿推不出地方（模型没配或调用失败）。"
                           "你直接说个城市名，我照样能排。").strip(),
                     profiles=got.profiles)
    names = "、".join(c.name for c in s.cards)
    text = (f"{head}\n\n像这几个：**{names}**。\n"
            f"说个名字就行，或者「换一个」。")
    return Reply(session_id=s.id, stage=1, text=text, cards=s.cards,
                 profiles=got.profiles, mode=got.mode)


def _finish_plan(s: Session, plan, opening: str, lead: str, clarify: str = "") -> Reply:
    it, pois, question = plan
    s.itinerary, s.pois = it, pois
    s.dest_name = it.dest.name
    s.stage = 2
    store().save(s)
    text = f"{lead}\n\n{opening}".strip() if opening else lead
    ask = clarify or question
    if ask:
        text += f"\n\n{ask}"
    return Reply(session_id=s.id, stage=2, text=text, itinerary=it, ledger=it.ledger,
                 profiles=s.profiles, questions=[question] if question else [],
                 mode=_mode())


def _handle_choice(s: Session, text: str) -> Reply:
    if not s.cards:
        return _far_choice(s, text)
    if _wants_other(text):
        return _reroll(s)

    picked = _match_card(text, s.cards)
    if picked is None and _is_agree(text):
        picked = s.cards[0]
    if picked is not None:
        return choose(s.id, picked.id)

    if engine.extract_brief(text)["tags"]:
        return _intake(s)

    names = "、".join(c.name for c in s.cards)
    return Reply(session_id=s.id, stage=1, mode=_mode(),
                 text=f"我问的是：{names}，哪个？（或者说「你定」）",
                 cards=s.cards, profiles=s.profiles)


def _far_choice(s: Session, text: str) -> Reply:
    """库外那一轮：转国内近似，或者直接按记忆排。"""
    t = text or ""
    if any(k in t for k in ("国内", "境内", "像的", "近似", "差不多", "①")):
        s.domestic_forced = True
        cards = agents.suggest_destinations(s.profiles, "只推荐中国境内的，氛围尽量接近图片")
        s.cards = cards
        store().save(s)
        if not cards:
            return Reply(session_id=s.id, stage=1, mode=_mode(),
                         text="我这会儿推不出来（模型没调通）。你直接说个城市。")
        names = "、".join(c.name for c in cards)
        return Reply(session_id=s.id, stage=1, mode=_mode(),
                     text=f"国内的话，这仨比较像：**{names}**。哪个？",
                     cards=cards, profiles=s.profiles)

    if any(k in t for k in ("真去", "就排", "②", "就去", "境外", "国外")):
        where = (s.profiles[0].place_guess if s.profiles else "") or ""
        if not where:
            return Reply(session_id=s.id, stage=1, mode=_mode(),
                         text="哪个地方？给我个地名我就排。")
        plan = pipeline.build_plan_for(where, s.profiles, s.days)
        if plan is None:
            return Reply(session_id=s.id, stage=1, mode=_mode(),
                         text=f"「{where}」我这边生成不出来（模型没调通）。"
                              f"先说说季节和预算，我把方向捋清楚。")
        return _finish_plan(s, plan, "", f"行，按「{where}」排了 {s.days} 天。")

    return Reply(session_id=s.id, stage=1, mode=_mode(),
                 text="想走哪条：① 我在国内给你找像的　② 就排这里（没核实）")


def _wants_other(text: str) -> bool:
    t = text.replace(" ", "")
    return any(w in t for w in OTHER_WORDS) and not _match_card(t, [])


def _is_agree(text: str) -> bool:
    t = text.replace(" ", "")
    return len(t) <= 4 and any(t.startswith(w) or w in t for w in AGREE_WORDS)


def _match_card(text: str, cards: list[DestinationCard]) -> DestinationCard | None:
    for c in cards:
        if c.name and c.name in text:
            return c
    return None


def _reroll(s: Session) -> Reply:
    """换一批：让模型重新推。"""
    cards = agents.suggest_destinations(s.profiles, "换一批，不要和之前重样")
    if not cards:
        return Reply(session_id=s.id, stage=1, mode=_mode(), text="我这会儿推不出来了。")
    s.cards = cards
    store().save(s)
    names = "、".join(c.name for c in cards)
    return Reply(session_id=s.id, stage=1, mode=_mode(),
                 text=f"换这几个：**{names}**。哪个？", cards=cards, profiles=s.profiles)


# ------------------------------------------------------------------ 第二轮
def choose(sid: str, dest_id: str) -> Reply:
    s = store().get(sid)
    if s is None or not s.cards:
        return Reply(session_id=sid, stage=0, text="页面刷新了，再说一次想去哪？", mode=_mode())

    card = next((c for c in s.cards if c.id == dest_id), None)
    if card is None:
        return Reply(session_id=s.id, stage=1, text="这个刚才没推荐过，说个名字？",
                     cards=s.cards, mode=_mode())

    days = card.days or s.days or 3
    plan = pipeline.build_plan_for(card.name, s.profiles, days)
    if plan is None:
        return Reply(session_id=s.id, stage=1, mode=_mode(),
                     text=f"「{card.name}」我这边生成不出来（模型没调通）。换个地方试试？",
                     cards=s.cards)
    return _finish_plan(s, plan, "", f"好，{card.name}，{days} 天。")


# ------------------------------------------------------------------ 第三轮
def apply_adjust(sid: str, kind: str, day: int | None = None) -> Reply:
    s = store().get(sid)
    if s is None or s.itinerary is None:
        return Reply(session_id=sid, stage=0, text="还没有行程可以改，先说说想怎么玩？", mode=_mode())

    new_it, msg = adjust_mod.adjust(s.itinerary, kind, s.profiles, s.pois, day)
    s.itinerary = new_it
    s.answers.append(kind)
    store().save(s)
    return Reply(session_id=s.id, stage=3, text=msg, itinerary=new_it,
                 profiles=s.profiles, mode=_mode())


def swap(sid: str, day: int, poi_id: str) -> Reply:
    """换掉某一天的一个点位，别的不动。"""
    s = store().get(sid)
    if s is None or s.itinerary is None:
        return Reply(session_id=sid, stage=0, text="还没有行程可以换。", mode=_mode())
    new_it, msg = engine.swap_item(s.itinerary, day, poi_id, s.pois, s.profiles)
    s.itinerary = new_it
    store().save(s)
    return Reply(session_id=s.id, stage=s.stage, text=msg, itinerary=new_it,
                 profiles=s.profiles, mode=_mode())


def polish(sid: str) -> Reply:
    """后台补攻略文案：只改文字，不改点位。"""
    s = store().get(sid)
    if s is None or s.itinerary is None:
        return Reply(session_id=sid, stage=0, text="", mode=_mode())
    s.itinerary = pipeline.polish(s.itinerary, s.profiles)
    store().save(s)
    return Reply(session_id=s.id, stage=s.stage, text="", itinerary=s.itinerary, mode=_mode())


def _adjust_kind(text: str) -> str:
    t = text or ""
    if any(k in t for k in ("雨", "下雪", "台风")):
        return "rain"
    if any(k in t for k in ("累", "不想动", "歇", "困", "走不动")):
        return "tired"
    if any(k in t for k in ("赶", "满", "紧", "松", "少排")):
        return "loosen"
    return ""


def _is_question(text: str) -> bool:
    t = text or ""
    return any(k in t for k in ("?", "？", "吗", "怎么", "几点", "多少钱", "预约",
                                "门票", "多久", "能不能", "是不是", "好吃", "闭馆", "开放"))


def _day_number(text: str) -> int | None:
    import re

    m = re.search(r"第\s*([一二三四五六七1-7])\s*天", text or "")
    if not m:
        return None
    raw = m.group(1)
    return int(raw) if raw.isdigit() else "一二三四五六七".index(raw) + 1


# ------------------------------------------------------------------ 问事实
def _lookup(s: Session, text: str) -> Reply | None:
    """联网查一句。查不到就说查不到。"""
    if len(text) < 4 or not s.itinerary:
        return None
    results = live.web_search(f"{s.dest_name} {text}")
    if not results:
        return Reply(session_id=s.id, stage=s.stage, mode=_mode(),
                     text="这句我查不到：现在没有可用的搜索源（key 没配）。"
                          "行程里标了「未核实」的，出发前自己核一遍。",
                     itinerary=s.itinerary)
    lines = [f"· {r['title']}：{r['content'][:70]}…" for r in results[:3]]
    srcs = "\n".join(f"  {r['url']}" for r in results[:3] if r.get("url"))
    return Reply(session_id=s.id, stage=s.stage, mode=_mode(),
                 text="我查了一下：\n" + "\n".join(lines) + ("\n来源：\n" + srcs if srcs else ""),
                 itinerary=s.itinerary)
