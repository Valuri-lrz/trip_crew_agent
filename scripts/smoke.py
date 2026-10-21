"""端到端冒烟：在一个进程里起服务、走完整条链路、打印结果。

用法：py -3.13 -m scripts.smoke
不依赖外部 key——没有 key 时走规则兜底（demo 模式），这正是要验证的降级路径。
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request

import uvicorn

from travel.main import app

PORT = 8799
BASE = f"http://127.0.0.1:{PORT}"


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main() -> int:
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    if not server.started:
        print("服务没起来")
        return 1

    with urllib.request.urlopen(BASE + "/api/health", timeout=10) as r:
        print("health:", r.read().decode())

    s = _post("/api/session", {})
    sid = s["session_id"]
    print(f"session {sid} stage={s['stage']}")
    print("bot:", s["text"])

    m = _post("/api/message", {
        "session_id": sid,
        "text": "我们两个五一去大理玩三天，她喜欢拍照，我怕人多想安静点",
        "images": [],
    })
    print(f"stage={m['stage']} mode={m['mode']}")
    print("bot:", m["text"])
    p = m["profiles"][0]
    print("画像:", p["summary"], "| tags=", p["tags"])
    print("信心:", p["confidence"])
    print("推荐:", [(c["name"], c["score"]) for c in m["cards"]])
    if m["cards"]:
        print("理由:", m["cards"][0]["reason"])
        # 纯对话：不点卡片，直接说"就这个"
        r2 = _post("/api/message", {"session_id": sid, "text": "就这个吧", "images": []})
    else:
        # 用户已经说了城市，系统直接出了行程，没有候选可挑
        print("(用户点名了城市，已直接排程)")
        r2 = m
    it = r2["itinerary"]
    print("对话选完 →", it["dest"]["name"], f"{len(it['days'])} 天")
    for d in it["days"]:
        names = [i["name"] for i in d["items"]]
        print(f"  第{d['day']}天 {d['total_min']}分钟 {names}")
    print("bot:", r2["text"].replace("\n", " ")[:90])

    import time as _t
    _t0 = _t.time()
    pol = _post("/api/polish", {"session_id": sid})
    first = pol["itinerary"]["days"][0]["items"][0]
    print(f"补攻略 {round(_t.time() - _t0, 1)}s → {first['highlight'][:50]}")

    r3 = _post("/api/message", {"session_id": sid, "text": "第1天下雨了怎么办", "images": []})
    print("调整:", r3["text"])
    print("第1天全室内:", all(i["indoor"] for i in r3["itinerary"]["days"][0]["items"]))

    r4 = _post("/api/message", {"session_id": sid, "text": "好累", "images": []})
    print("调整:", r4["text"])

    # 攻略内容
    first = r2["itinerary"]["days"][0]["items"][0]
    print("攻略条目:", first["name"], "|", first["highlight"], "|", first["tip"])
    # 换一个
    r5 = _post("/api/swap", {"session_id": sid, "day": 2,
                             "poi_id": r2["itinerary"]["days"][1]["items"][0]["poi_id"]})
    print("换点:", r5["text"])
    print("第2天现在:", [i["name"] for i in r5["itinerary"]["days"][1]["items"]])

    # 配图（不联网时应该是占位图，但必须有响应）
    with urllib.request.urlopen(BASE + "/api/photo?q=" + urllib.parse.quote("洱海"), timeout=15) as r:
        body = r.read()
        print("配图:", r.status, r.headers.get("Content-Type"), len(body), "bytes")

    with urllib.request.urlopen(BASE + "/", timeout=10) as r:
        html = r.read()
    print("首页字节数:", len(html))

    server.should_exit = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
