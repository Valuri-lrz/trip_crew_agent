"""验证流式：首字节时间、token 数、内容是否真的一点点出来。"""
import json
import threading
import time
import urllib.request

import uvicorn

from travel.main import app

PORT = 8805
BASE = f"http://127.0.0.1:{PORT}"


def main():
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.1)

    req = urllib.request.Request(
        BASE + "/api/session", data=b"{}", headers={"Content-Type": "application/json"})
    sid = json.loads(urllib.request.urlopen(req, timeout=30).read())["session_id"]

    body = json.dumps({"session_id": sid, "text": "五一去大理三天，两个人，喜欢安静怕人多",
                       "images": []}).encode()
    req = urllib.request.Request(BASE + "/api/stream", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    first_meta = first_delta = None
    text = ""
    n_delta = 0
    with urllib.request.urlopen(req, timeout=180) as r:
        for raw in r:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            evt = json.loads(line[5:].strip())
            if evt["type"] == "meta" and first_meta is None:
                first_meta = time.time() - t0
                it = evt.get("itinerary")
                print("meta:", round(first_meta, 1), "s  stage=", evt.get("stage"),
                      "天数=", len(it["days"]) if it else 0)
            elif evt["type"] == "delta":
                if first_delta is None:
                    first_delta = time.time() - t0
                text += evt["text"]
                n_delta += 1
    print("首字:", round(first_delta, 1), "s | 块数:", n_delta, "| 总耗时:", round(time.time() - t0, 1))
    print("正文:", text)
    srv.should_exit = True


if __name__ == "__main__":
    main()
