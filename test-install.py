import os
import platform
import subprocess
import sys
import threading
import urllib.request
import urllib.parse
import hashlib
import time

# 强行让 Windows 环境下的控制台支持 UTF-8 实时中文输出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')


# ==========================================================
# 1. 核心测试：手动重定向追踪器 (Manual Redirect Tracer)
# ==========================================================
def trace_redirects_manually(url, headers):
    """
    手动追踪 HTTP 重定向（不带任何 Range 干扰），完全还原浏览器行为。
    能完美通过 302 路由一直追踪到 GitHub (海外) 或 GitCode (境内) 的最终直连下载源。
    """
    current_url = url
    redirect_count = 0
    max_redirects = 15

    # 构造一个阻止自动重定向的处理器
    class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            return None  # 返回 None 阻止 urllib 自动跳转，由我们手动捕获

    opener = urllib.request.build_opener(NoRedirectHandler)

    print("🛰️ 开始验证智能路由架构（手动追踪 302 链）...")
    while redirect_count < max_redirects:
        req = urllib.request.Request(current_url, headers=headers, method="GET")
        try:
            # 打开连接。如果不触发 302 异常，说明已经抵达最终的直连下载源
            with opener.open(req, timeout=15) as resp:
                print(f"\n🎯 架构验证成功！已抵达最终直连源 (HTTP {resp.status})")
                print(f"   🔹 最终下载源: {current_url}")
                return current_url
        except urllib.error.HTTPError as e:
            # 捕获重定向状态码
            if e.code in (301, 302, 303, 307, 308):
                new_url = e.headers.get("Location")
                if not new_url:
                    raise RuntimeError(f"收到重定向状态码 {e.code}，但未找到 Location 响应头")

                # 兼容相对路径跳转
                new_url = urllib.parse.urljoin(current_url, new_url)
                print(f"   🔄 [重定向触发] HTTP {e.code}: -> {new_url}")
                current_url = new_url
                redirect_count += 1
            else:
                raise e

    raise RuntimeError("达到了最大重定向次数限制")


def download_file(url, filename, headers):
    """
    对最终直连源进行标准高速流式下载。
    因为此时的 URL 已经是 GitHub 或 GitCode 真实节点，无任何 1MB 掐断限制，无需分片，直接拉取。
    """
    print(f"\n📥 正在从最终直连源下载安装包...")
    req = urllib.request.Request(url, headers=headers)

    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                total_size = int(response.getheader('Content-Length', 0))
                downloaded = 0

                with open(filename, 'wb') as f:
                    while True:
                        chunk = response.read(1024 * 128)  # 128KB 缓冲区
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        # 打印进度（每 2MB 打印一次，避免日志刷屏）
                        if total_size and (downloaded % (2 * 1024 * 1024) < 128 * 1024 or downloaded == total_size):
                            percent = (downloaded / total_size) * 100
                            print(f"   进度: {percent:.1f}% ({downloaded}/{total_size} 字节)")

                print("✅ 下载顺利完成！")
                return True
        except Exception as e:
            print(f"   ⚠️ 下载遭遇抖动 (尝试 {attempt}/3): {e}，正在重试...")
            time.sleep(2)

    raise RuntimeError("💥 经历 3 次重试后，下载仍然失败。")


def calculate_sha256(filepath):
    """
    高效计算本地文件的 SHA-256 校验和
    """
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        return f"计算失败: {e}"


def run_command_streaming(cmd):
    """
    实时流式输出进程日志
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


# ==========================================================
# 2. 自动识别系统与架构
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

# 4. 路由追踪与直连高速下载
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

try:
    # 第一步：追踪得到最终不被拦截的 direct-download 真实地址
    final_direct_url = trace_redirects_manually(url, headers)

    # 第二步：直接下载
    download_file(final_direct_url, filename, headers)

    if sys_os != "Windows":
        os.chmod(filename, 0o755)
except Exception as e:
    print(f"💥 运行失败并退出: {e}", file=sys.stderr)
    sys.exit(1)

# 5. 计算并显示下载文件的 SHA-256 校验和
print("\n🔒 正在校验安装包哈希值...")
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