import os
import platform
import subprocess
import sys
import urllib.request

# === 配置区 ===
WEBDAV_BASE_URL = "http://100.113.111.18:20002/opt/orbit-test"

# 从环境变量获取 release-tag，如果读取不到则默认为 'dev'
# 你可以在 GitHub Actions 中设置环境变量： env: RELEASE_TAG: ${{ github.ref_name }}
RELEASE_TAG = os.environ.get("RELEASE_TAG", "dev")


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

        print(f"成功生成本地截图: {name}")
        return True
    except Exception as e:
        print(f"本地截图失败: {e}", file=sys.stderr)
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
                print(f"🎉 截图上传成功！")
                print("========================================")
            else:
                print(
                    f"上传响应异常，状态码: {response.status}",
                    file=sys.stderr,
                )
    except Exception as e:
        print(f"WebDAV 上传失败: {e}", file=sys.stderr)


if __name__ == "__main__":
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