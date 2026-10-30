# -*- coding: utf-8 -*-
"""唱练 · 封装入口：准备用户目录与内置模型 → 启动本地服务 → 自动打开浏览器。
关闭控制台窗口即退出程序。
"""
import os, sys, time, socket, threading, webbrowser


def pick_port(preferred: int = 8178) -> int:
    for p in [preferred] + list(range(preferred + 1, preferred + 20)):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    return preferred


def main() -> None:
    if getattr(sys, "frozen", False):
        os.chdir(os.path.dirname(os.path.abspath(sys.executable)))
    else:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "server"))

    import paths
    paths.ensure_dirs()
    paths.seed_models()

    port = pick_port()
    url = f"http://127.0.0.1:{port}"
    print("=" * 58)
    print("  唱练 · 本地练歌工作室")
    print(f"  服务地址：{url}（浏览器应已自动打开）")
    print("  使用完毕直接关闭本窗口即可退出。")
    print("=" * 58)

    def _open_browser():
        time.sleep(2.0)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_open_browser, daemon=True).start()

    import uvicorn
    from app import app
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
