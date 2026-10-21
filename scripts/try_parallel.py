"""测一下：两个 Crew 能不能并行跑（决定要不要把两次调用叠起来）。"""
import threading
import time

from travel import agents

out = {}


def run(name, fn):
    t0 = time.time()
    try:
        out[name] = (round(time.time() - t0, 1), "ok")
        fn()
        out[name] = (round(time.time() - t0, 1), "ok")
    except Exception as e:
        out[name] = (round(time.time() - t0, 1), f"{type(e).__name__}: {str(e)[:60]}")


def profiler():
    b = agents.run_profiler(["五一两个人去大理三天，喜欢安静怕人多"], [None], 1)
    out["profiles"] = len(b.profiles) if b else 0


def draft():
    pois = agents.run_draft_pois("大理", [], 3)
    out["pois"] = len(pois) if pois else 0


if __name__ == "__main__":
    t0 = time.time()
    a = threading.Thread(target=run, args=("p", profiler))
    b = threading.Thread(target=run, args=("d", draft))
    a.start(); b.start()
    a.join(); b.join()
    print("并行总耗时:", round(time.time() - t0, 1), "s")
    print(out)
