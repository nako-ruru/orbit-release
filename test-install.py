import hashlib
import os
import platform
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

# 强行让 Windows 环境下的控制台支持 UTF-8 实时中文输出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


# ==========================================================
# 1. 核心测试：手动重定向追踪器
# ==========================================================
def trace_redirects_manually(url, headers):
    """手动追踪 HTTP 重定向，完美支持 Hugging Face / CDN 302 跳转。"""
    current_url = url
    redirect_count = 0
    max_redirects = 15

    class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirectHandler)

    print("🛰️ 开始验证智能路由架构（手动追踪 302 链）...")
    while redirect_count < max_redirects:
        req = urllib.request.Request(current_url, headers=headers, method="GET")
        try:
            with opener.open(req, timeout=15) as resp:
                print(f"\n🎯 架构验证成功！已抵达最终直连源 (HTTP {resp.status})")
                print(f"   🔹 最终下载源: {current_url}")
                return current_url
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                new_url = e.headers.get("Location")
                if not new_url:
                    raise RuntimeError(
                        f"收到重定向状态码 {e.code}，但未找到 Location 响应头"
                    )

                new_url = urllib.parse.urljoin(current_url, new_url)
                print(f"   🔄 [重定向触发] HTTP {e.code}: -> {new_url}")
                current_url = new_url
                redirect_count += 1
            else:
                raise e

    raise RuntimeError("达到了最大重定向次数限制")


def download_file(url, filename, headers):
    """从最终直连源进行标准高速流式下载。"""
    print("\n📥 正在从私有/公开源拉取测试安装包...")
    req = urllib.request.Request(url, headers=headers)

    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                total_size = int(response.getheader("Content-Length", 0))
                downloaded = 0

                with open(filename, "wb") as f:
                    while True:
                        chunk = response.read(1024 * 128)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total_size and (
                            downloaded % (2 * 1024 * 1024) < 128 * 1024
                            or downloaded == total_size
                        ):
                            percent = (downloaded / total_size) * 100
                            print(
                                f"   进度: {percent:.1f}% ({downloaded}/{total_size} 字节)"
                            )

                print("✅ 下载顺利完成！")
                return True
        except Exception as e:
            print(f"   ⚠️ 下载遭遇抖动 (尝试 {attempt}/3): {e}，正在重试...")
            time.sleep(2)

    raise RuntimeError("💥 经历 3 次重试后，下载仍然失败。")


def calculate_sha256(filepath):
    """计算本地文件的 SHA-256 校验和"""
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        return f"计算失败: {e}"


def run_command_streaming(cmd):
    """实时流式输出进程日志"""
    print(f"执行命令: {' '.join(cmd)}")
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        def reader_thread():
            try:
                for line in iter(process.stdout.readline, ""):
                    print(line, end="", flush=True)
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
# 2. 排查问题专用环境变量看板 (保留不可删除)
# ==========================================================
print("=================== 初始环境检查 ===================")
target_envs = ["GITHUB_ACTIONS", "ORBIT_LOG_PATH"]
for var in target_envs:
    val = os.environ.get(var)
    if val is not None and val.strip() != "":
        print(f"🌱 环境变量检测到: {var}={val}")
    else:
        print(f"⚠️ 环境变量未配置: {var}")

release_tag = os.environ.get("RELEASE_TAG", "main").strip()
deps_url = os.environ.get("DEPS_URL", "").strip()
hf_token = os.environ.get("HF_TOKEN", "").strip()

if not deps_url:
    deps_url = f"https://huggingface.co/datasets/nako-ruru/orbit/resolve/main/releases/{release_tag}/dependencies.yml"

print(f"🏷️ 当前测试 Release Tag : {release_tag}")
print(f"🔗 注入 Dependencies URL: {deps_url}")
print("====================================================\n")

sys_os = platform.system()
arch = platform.machine().lower()

uninstaller = ""
filename = ""

# 指向私有 Dataset nako-ruru/orbit-private，避免测试版文件泄露
hf_private_base = f"https://huggingface.co/datasets/nako-ruru/orbit-private/resolve/main/releases/{release_tag}"

if sys_os == "Windows":
    base_path = r"C:\Program Files\orbit\uninstaller"
    if os.path.exists(base_path + ".exe"):
        uninstaller = base_path + ".exe"
    elif os.path.exists(base_path):
        uninstaller = base_path

    filename = "orbit_installer_windows.exe"
    url = f"{hf_private_base}/{filename}"

elif sys_os == "Linux":
    uninstaller = "/opt/orbit/Orbit.AppDir/usr/bin/uninstaller"
    filename = "orbit_installer_linux"
    url = f"{hf_private_base}/{filename}"

elif sys_os == "Darwin":
    uninstaller = "/Applications/Orbit.app/Contents/MacOS/uninstaller"
    if "arm64" in arch:
        filename = "orbit_installer_darwin_arm64"
    else:
        filename = "orbit_installer_darwin_x86_64"
    url = f"{hf_private_base}/{filename}"
else:
    print(f"不支持的操作系统: {sys_os}", file=sys.stderr)
    sys.exit(1)

# 3. 执行旧版本卸载
if uninstaller and os.path.exists(uninstaller):
    print("【旧版本审计】检测到旧版本，正在流式执行卸载...")
    uninstall_cmd = (
        [uninstaller] if sys_os == "Windows" else ["sudo", "-E", uninstaller]
    )
    code = run_command_streaming(uninstall_cmd)
    if code == 0:
        print("旧版本卸载完毕。")
    else:
        print(f"旧版本卸载返回非零状态码: {code}（尝试继续安装）")
else:
    print("未检测到旧版本或无需卸载，跳过此步骤。")

# 4. 从私有 Hugging Face 仓库下载测试版安装程序 (携带 Bearer Auth Token)
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
if hf_token:
    headers["Authorization"] = f"Bearer {hf_token}"

try:
    final_direct_url = trace_redirects_manually(url, headers)
    download_file(final_direct_url, filename, headers)

    if sys_os != "Windows":
        os.chmod(filename, 0o755)
except Exception as e:
    print(f"💥 运行失败并退出: {e}", file=sys.stderr)
    sys.exit(1)

# 5. 计算安装包哈希
print("\n🔒 正在校验安装包哈希值...")
sha256_result = calculate_sha256(filename)
print(f"💾 文件名: {filename}")
print(f"🔑 SHA-256: {sha256_result}\n")

# 6. 流式启动安装程序 (携带 --allow-skip-verify / --allow-custom-deps / -d 参数)
print("正在以 [流式阻塞模式] 启动测试版安装程序...")
if sys_os == "Windows":
    exec_cmd = [
        filename,
        "--silent",
        "--allow-skip-verify",
        "--allow-custom-deps",
        "--install-dir",
        r"C:\Program Files\Orbit",
        "-d",
        deps_url,
    ]
else:
    exec_cmd = [
        "sudo",
        "-E",
        f"./{filename}",
        "--allow-skip-verify",
        "--allow-custom-deps",
        "-d",
        deps_url,
    ]

exit_code = run_command_streaming(exec_cmd)

if exit_code == 0:
    print("🎉 安装程序执行完毕且成功退出，日志已全部冲刷至控制台。")
else:
    print(f"❌ 安装程序执行失败，退出码: {exit_code}", file=sys.stderr)
    sys.exit(exit_code)