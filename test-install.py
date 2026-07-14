import os
import platform
import subprocess
import sys
import threading
import urllib.request
import hashlib  # 导入哈希库

# 强行让 Windows 环境下的控制台支持 UTF-8 实时中文输出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')


# ==========================================================
# 1. 入口环境变量检查与打印
# ==========================================================
print("=================== 初始环境检查 ===================")
target_envs = ["GITHUB_ACTIONS", "ORBIT_LOG_PATH"]
for var in target_envs:
    val = os.environ.get(var)
    if val is not None and val.strip() != "":
        print(f"🌱 环境变量检测到: {var}={val}")
    else:
        print(f"⚠️ 环境变量未配置: {var}")
print("====================================================\n")


def calculate_sha256(filepath):
    """
    高效计算本地文件的 SHA-256 校验和（流式读取，内存安全）
    """
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            # 每次读取 4096 字节，防止大文件吃满内存
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        return f"计算失败: {e}"


def run_command_streaming(cmd):
    """
    核心黑科技：实时流式输出进程日志，且严格基于 PID 阻塞，绝不因主程序常驻而挂起 CI
    """
    print(f"执行命令: {' '.join(cmd)}")
    try:
        # 将 stderr 合并到 stdout，统一流式捕获
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        # 创建后台守护线程，实时榨干管道里的每一行日志并打印
        def reader_thread():
            try:
                for line in iter(process.stdout.readline, ''):
                    print(line, end='', flush=True)  # flush=True 保证 GitHub Actions 网页实时跳字
            except Exception:
                pass

        t = threading.Thread(target=reader_thread)
        t.daemon = True # 设为守护线程，主线程退出时它自动消亡
        t.start()

        # 主线程死等安装包/卸载包自身的 PID 退出，不关心它拉起的子进程
        returncode = process.wait()
        return returncode
    except Exception as e:
        print(f"执行命令时发生异常: {e}", file=sys.stderr)
        return -1


# 2. 自动识别系统与架构
sys_os = platform.system()
arch = platform.machine().lower()

uninstaller = ""
url = ""
filename = ""

if sys_os == "Windows":
    base_path = r"C:\Program Files\orbit\uninstaller"
    if os.path.exists(base_path + ".exe"):
        uninstaller = base_path + ".exe"
    elif os.path.exists(base_path):
        uninstaller = base_path

    url = "https://guanghe.co/download/orbit_installer_windows.exe"
    filename = "orbit_installer_windows.exe"

elif sys_os == "Linux":
    uninstaller = "/opt/orbit/Orbit.AppDir/usr/bin/uninstaller"
    url = "https://guanghe.co/download/orbit_installer_linux"
    filename = "orbit_installer_linux"

elif sys_os == "Darwin":
    uninstaller = "/Applications/Orbit.app/Contents/MacOS/uninstaller"
    if "arm64" in arch:
        url = "https://guanghe.co/download/orbit_installer_darwin_arm64"
        filename = "orbit_installer_darwin_arm64"
    else:
        url = "https://guanghe.co/download/orbit_installer_darwin_x86_64"
        filename = "orbit_installer_darwin_x86_64"
else:
    print(f"不支持的操作系统: {sys_os}", file=sys.stderr)
    sys.exit(1)


# 3. 如果卸载程序存在，先执行卸载
if uninstaller and os.path.exists(uninstaller):
    print(f"【旧版本审计】检测到旧版本，正在流式执行卸载...")
    # 💡 关键改动：Linux/Darwin 下使用 sudo -E 确保原进程的环境变量透传给卸载程序
    uninstall_cmd = [uninstaller] if sys_os == "Windows" else ["sudo", "-E", uninstaller]
    code = run_command_streaming(uninstall_cmd)
    if code == 0:
        print("旧版本卸载完毕。")
    else:
        print(f"旧版本卸载返回非零状态码: {code}（尝试继续安装）")
else:
    print("未检测到旧版本或无需卸载，跳过此步骤。")


# 4. 下载对应的安装包
print(f"正在下载 ({sys_os}/{arch}): {url}")
try:
    urllib.request.urlretrieve(url, filename)
    if sys_os != "Windows":
        os.chmod(filename, 0o755)
    print("下载完成。")
except Exception as e:
    print(f"下载失败: {e}", file=sys.stderr)
    sys.exit(1)


# ==========================================================
# 5. 计算并显示下载文件的 SHA-256 校验和
# ==========================================================
print("🔒 正在校验安装包哈希值...")
sha256_result = calculate_sha256(filename)
print(f"💾 文件名: {filename}")
print(f"🔑 SHA-256: {sha256_result}\n")


# 6. 流式执行安装程序
print(f"正在以 [流式阻塞模式] 启动安装程序...")
if sys_os == "Windows":
    # 完美注入你的非交互静默安装参数
    exec_cmd = [filename, "--silent", "--install-dir", r"C:\Program Files\Orbit"]
else:
    # 💡 关键改动：Linux/Darwin 下使用 sudo -E 确保原进程的环境变量透传给安装程序
    exec_cmd = ["sudo", "-E", f"./{filename}"]

exit_code = run_command_streaming(exec_cmd)

if exit_code == 0:
    print("🎉 安装程序执行完毕且成功退出，日志已全部冲刷至控制台。")
else:
    print(f"❌ 安装程序执行失败，退出码: {exit_code}", file=sys.stderr)
    sys.exit(exit_code)