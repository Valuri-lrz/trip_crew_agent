"""FastAPI 入口。页面只有一张，接口不多。"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel

from travel import photos
from travel import session as session_mod
from travel.config import ROOT, get_settings
from travel.storage import writable_dir

WEB = ROOT / "web"
UPLOADS = writable_dir(ROOT / "data" / "uploads")
MAX_BYTES = 8 * 1024 * 1024

app = FastAPI(title="travel-agent", docs_url="/api/docs")


class MsgIn(BaseModel):
    session_id: str
    text: str = ""
    images: list[str] = []


class ChooseIn(BaseModel):
    session_id: str
    dest_id: str


class AdjustIn(BaseModel):
    session_id: str
    kind: str
    day: int | None = None


class SessionIn(BaseModel):
    session_id: str


class SwapIn(BaseModel):
    session_id: str
    day: int
    poi_id: str


@app.get("/api/guides")
def guides_api(name: str, city: str = ""):
    """网上攻略抽成事实。带来源编号和冲突，不选边。"""
    try:
        from travel import guides

        from travel.resolve import TAIL, resolve

        bundle, note = guides.collect(name, city)
        if bundle is None:
            return {"latest": [], "old": [], "conflicts": [], "note": note, "tail": TAIL}
        got = resolve(bundle)
        got["note"] = note
        return got
    except Exception as exc:
        return {"facts": [], "conflicts": [], "note": f"{type(exc).__name__}"}


@app.get("/api/facts")
def facts(name: str, city: str = ""):
    """点位事实：评分/人均/营业时间/地址。查不到返回 {}，前端标"未核实"。"""
    try:
        from travel.live import place_facts

        return place_facts(name, city) or {}
    except Exception:
        return {}


@app.get("/api/photo")
def photo(q: str, city: str = ""):
    """配图：能查到就 302 到实景图，查不到当场画一张。永不返回 404。"""
    url = photos.photo_for(q, city)
    if url:
        return RedirectResponse(url, headers={"Cache-Control": "public, max-age=86400"})
    return Response(photos.placeholder(q), media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/health")
def health():
    s = get_settings()
    return {"ok": True, "demo_mode": s.demo_mode, "llm": s.llm_ready, "amap": s.amap_ready}


@app.post("/api/session")
def create_session():
    _, reply = session_mod.new_session()
    return reply


@app.post("/api/message")
def message(body: MsgIn):
    if not body.text.strip() and not body.images:
        raise HTTPException(400, "说点什么")
    try:
        return session_mod.handle_text(body.session_id, body.text.strip(), body.images)
    except Exception as exc:  # 兜底：不让一个异常把页面卡死
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc


SITUATION = {
    0: "用户刚打开页面",
    1: "你已经看完他说的和发的图，给出了画像和几个候选",
    2: "行程已经排好了，用户马上能看到",
    3: "用户刚提了一个调整，你已经改完了",
}


@app.post("/api/stream")
def stream(body: MsgIn):
    """结构先到，文字再一个字一个字流出来。"""
    from travel.stream import stream_reply

    if not body.text.strip() and not body.images:
        raise HTTPException(400, "说点什么")
    def evt(payload: dict) -> str:
        return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"

    def gen():
        yield evt({"type": "status", "text": "在看你说的话…"})
        try:
            reply = session_mod.handle_text(body.session_id, body.text.strip(), body.images)
        except Exception as exc:
            yield evt({"type": "error", "text": f"{type(exc).__name__}: {exc}"})
            return
        meta = reply.model_dump()
        draft = meta.pop("text", "") or ""
        yield evt({"type": "meta", **meta})
        for tok in stream_reply(SITUATION.get(reply.stage, ""), draft):
            yield evt({"type": "delta", "text": tok})
        yield 'data: {"type":"done"}\n\n'

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.post("/api/choose")
def choose(body: ChooseIn):
    try:
        return session_mod.choose(body.session_id, body.dest_id)
    except Exception as exc:
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc


@app.post("/api/adjust")
def adjust(body: AdjustIn):
    try:
        return session_mod.apply_adjust(body.session_id, body.kind, body.day)
    except Exception as exc:
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc


@app.post("/api/polish")
def polish(body: SessionIn):
    try:
        return session_mod.polish(body.session_id)
    except Exception as exc:
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc


@app.post("/api/swap")
def swap(body: SwapIn):
    """换掉某一天的某一个点位，其他都不动。"""
    try:
        return session_mod.swap(body.session_id, body.day, body.poi_id)
    except Exception as exc:
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc


@app.get("/img")
def img(p: str):
    """只允许读 uploads 目录下的图，防止路径穿越。"""
    path = Path(p).resolve()
    root = UPLOADS.resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "没有这张图")
    return FileResponse(path)


@app.post("/api/upload")
async def upload(files: list[UploadFile] = File(...)):
    UPLOADS.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for f in files[:3]:
        suffix = Path(f.filename or "img.jpg").suffix.lower() or ".jpg"
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        data = await f.read()
        if len(data) > MAX_BYTES:
            continue
        target = UPLOADS / f"{uuid.uuid4().hex[:10]}{suffix}"
        target.write_bytes(data)
        paths.append(str(target))
    return {"paths": paths}
