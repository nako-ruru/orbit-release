import os
import platform
import subprocess
import sys
import threading
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
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        return f"计算失败: {e}"


def robust_download(url, filename):
    """
    【终极对策】调用系统原生 curl 进行下载。
    1. 彻底解决 Python TLS 指纹（JA3）被防火墙拦截导致的 1MB 斩断问题。
    2. 利用 curl 自带的 -L (追踪重定向) 和 --retry (自动重试) 确保高可用。
    """
    print(f"📥 正在通过系统 curl 下载: {url}")

    # 构造 curl 参数：
    # -L: 自动跟踪重定向
    # -f: HTTP 报错时直接失败退出
    # --retry 5: 异常时自动重试 5 次
    # --retry-delay 3: 每次重试等待 3 秒
    # -o: 输出到指定文件
    cmd = ["curl", "-L", "-f", "--retry", "5", "--retry-delay", "3", "-o", filename, url]

    try:
        # 在 Windows 下，如果是 python 执行，系统能自动找到 C:\Windows\System32\curl.exe
        # shell=False 更加安全防止注入
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            print("✅ 下载完成。")
            return True
        else:
            raise RuntimeError(f"curl 退出码非零 ({result.returncode})\n错误日志: {result.stderr}")
    except Exception as e:
        print(f"❌ curl 下载遭遇致命错误: {e}", file=sys.stderr)
        raise e


def run_command_streaming(cmd):
    """
    实时流式输出进程日志，且严格基于 PID 阻塞，绝不因主程序常驻而挂起 CI
    """
    print(f"执行命令: {' '.join(cmd)}")
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        def reader_thread():
            try:
                for line in iter(process.stdout.readline, ''):
                    print(line, end='', flush=True)
            except Exception:
                pass

        t = threading.Thread(target=reader_thread)
        t.daemon = True
        t.start()

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
    uninstall_cmd = [uninstaller] if sys_os == "Windows" else ["sudo", "-E", uninstaller]
    code = run_command_streaming(uninstall_cmd)
    if code == 0:
        print("旧版本卸载完毕。")
    else:
        print(f"旧版本卸载返回非零状态码: {code}（尝试继续安装）")
else:
    print("未检测到旧版本或无需卸载，跳过此步骤。")

# 4. 安全下载安装包
try:
    robust_download(url, filename)
    if sys_os != "Windows":
        os.chmod(filename, 0o755)
except Exception as e:
    print(f"💥 下载失败并退出: {e}", file=sys.stderr)
    sys.exit(1)

# 5. 计算并显示下载文件的 SHA-256 校验和
print("🔒 正在校验安装包哈希值...")
sha256_result = calculate_sha256(filename)
print(f"💾 文件名: {filename}")
print(f"🔑 SHA-256: {sha256_result}\n")

# 6. 流式执行安装程序
print(f"正在以 [流式阻塞模式] 启动安装程序...")
if sys_os == "Windows":
    exec_cmd = [filename, "--silent", "--install-dir", r"C:\Program Files\Orbit"]
else:
    exec_cmd = ["sudo", "-E", f"./{filename}"]

exit_code = run_command_streaming(exec_cmd)

if exit_code == 0:
    print("🎉 安装程序执行完毕且成功退出，日志已全部冲刷至控制台。")
else:
    print(f"❌ 安装程序执行失败，退出码: {exit_code}", file=sys.stderr)
    sys.exit(exit_code)