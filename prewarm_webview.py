import os
import sys
import time
import threading


# 强制刷新缓冲区，确保 GitHub Actions 能实时看到每一行 stdout
def log(msg):
    print(f"⏰ [{time.strftime('%H:%M:%S')}] {msg}")
    sys.stdout.flush()


# 🌟 核心看门狗：15秒后不管处于什么状态，无条件强杀当前 Python 进程，防止 CI 卡死
def watchdog_timer():
    time.sleep(15)
    log("🚨 [看门狗] 15秒绝对时间到！WebView 仍未自主结束，正在执行强制硬杀...")
    os._exit(0)  # 类似 kill -9，不触发任何清理，直接离场


def main():
    log("🚀 开始执行 WebView2 环境预热与隔离测试...")

    # 打印当前继承的环境变量，确认路径是否正确注入
    wv2_env = os.environ.get("WEBVIEW2_BROWSER_EXECUTABLE_FOLDER")
    log(f"📋 当前检测到 WEBVIEW2_BROWSER_EXECUTABLE_FOLDER = {wv2_env}")

    # 自动安装 pywebview 依赖（CI 环境纯净，动态安装最省心）
    log("📦 正在动态安装 pywebview 依赖...")
    os.system(f"{sys.executable} -m pip install pywebview --disable-pip-version-check -q")

    try:
        import webview
    except ImportError:
        log("❌ pywebview 安装失败，跳过测试。")
        return

    # 启动看门狗线程
    threading.Thread(target=watchdog_timer, daemon=True).start()
    log("🎯 15秒看门狗线程已就绪。")

    # 异步线程：负责在 10 秒后正常关闭窗口（如果没卡死的话）
    def close_window_normally(window_obj):
        log("⏳ 异步销毁线程启动，开始 10 秒倒计时...")
        time.sleep(10)
        log("💥 10秒已到，正在尝试通过 API 正常销毁 WebView 窗体...")
        try:
            window_obj.destroy()
            log("✅ API 销毁指令已发出。")
        except Exception as e:
            log(f"⚠️ 销毁窗体时发生异常: {e}")

    log("1️⃣  [准备就绪] 即将执行 webview.create_window() [等同于 Go 的 webview.New]...")
    try:
        # 创建一个空白窗体
        window = webview.create_window('Orbit CI Pre-warm Tool', 'about:blank')
        log("🎉 [成功] webview.create_window() 顺利通过！未发生阻塞。")
    except Exception as e:
        log(f"❌ [失败] webview.create_window() 发生崩溃: {e}")
        return

    # 绑定正常关闭的线程
    threading.Thread(target=close_window_normally, args=(window,), daemon=True).start()

    log("2️⃣  [准备就绪] 即将执行 webview.start() [等同于 Go 的 webview.Run]...")
    try:
        # 启动主消息循环
        webview.start()
        log("🎉 [成功] webview.start() 顺利起飞并正常安全退出！")
    except Exception as e:
        log(f"❌ [失败] webview.start() 发生崩溃: {e}")

    log("🏁 预热脚本生命周期正常结束。")


if __name__ == '__main__':
    main()