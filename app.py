import os
import sqlite3
import json
from datetime import datetime, timedelta
import re
from functools import wraps
from uuid import uuid4
import secrets
import hashlib
import threading
import requests
from email.utils import parseaddr
import mimetypes
import shutil
import subprocess
from pathlib import Path

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_file, abort, Response, make_response
)

from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

from menuwed_meta import (
    CONFIG as META_CONFIG,
    app_version as meta_app_version,
    default_data_dir,
    project_name as meta_project_name,
    load_config as load_menuwed_config,
    save_config as save_menuwed_config,
)

app = Flask(__name__, static_folder=STATIC_DIR, template_folder=TEMPLATE_DIR)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)


def apply_runtime_config_to_env() -> None:
    config = dict(META_CONFIG)

    def cfg(*keys: str, default: str = "") -> str:
        for key in keys:
            value = config.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return default

    def resolved_app_version() -> str:
        env_version = os.getenv("APP_VERSION", "").strip()
        if env_version and env_version.lower() != "latest":
            return env_version
        configured = cfg("version", "APP_VERSION")
        if configured and configured.lower() != "latest":
            return configured
        return meta_app_version()

    mappings = {
        "SECRET_KEY": cfg("secret_key", "SECRET_KEY"),
        "DATA_DIR": cfg("data_dir", "DATA_DIR"),
        "WEB_PORT": cfg("web_port", "WEB_PORT", default="5000"),
        "PORT": cfg("web_port", "WEB_PORT", "PORT", default="5000"),
        "PROJECT_NAME": cfg("project_name", "PROJECT_NAME", default=meta_project_name()),
        "APP_VERSION": cfg("version", "APP_VERSION", default=resolved_app_version()),
        "PUBLIC_BASE_URL": cfg("public_base_url", "PUBLIC_BASE_URL"),
        "TURNSTILE_SITE_KEY": cfg("turnstile_site_key", "TURNSTILE_SITE_KEY"),
        "TURNSTILE_SECRET_KEY": cfg("turnstile_secret_key", "TURNSTILE_SECRET_KEY"),
        "TURNSTILE_ALLOWED_HOSTNAMES": cfg("turnstile_allowed_hostnames", "TURNSTILE_ALLOWED_HOSTNAMES"),
        "TURNSTILE_REQUIRED": cfg("turnstile_required", "TURNSTILE_REQUIRED", default="false"),
        "WEB_HOST": cfg("web_host", "WEB_HOST", default="0.0.0.0"),
        "WEB_CONCURRENCY": cfg("web_concurrency", "WEB_CONCURRENCY", default="2"),
        "GUNICORN_THREADS": cfg("gunicorn_threads", "GUNICORN_THREADS", default="2"),
        "GUNICORN_TIMEOUT": cfg("gunicorn_timeout", "GUNICORN_TIMEOUT", default="120"),
        "FLASK_ENV": cfg("flask_env", "FLASK_ENV", default="production"),
        "IS_PRODUCTION": cfg("is_production", "IS_PRODUCTION", default="false"),
        "ADMIN_USERNAME": cfg("admin_username", "ADMIN_USERNAME", default="admin"),
        "ADMIN_PASSWORD": cfg("admin_password", "ADMIN_PASSWORD", default="1234"),
        "BREVO_API_KEY": cfg("brevo_api_key", "BREVO_API_KEY"),
        "BREVO_SENDER_EMAIL": cfg("brevo_sender_email", "BREVO_SENDER_EMAIL"),
        "BREVO_SENDER_NAME": cfg("brevo_sender_name", "BREVO_SENDER_NAME", default=meta_project_name()),
    }

    for key, value in mappings.items():
        value = str(value or "").strip()
        if value:
            os.environ[key] = value


apply_runtime_config_to_env()


def env_flag(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


DATA_DIR = os.path.abspath(
    os.getenv("DATA_DIR")
    or os.path.join(BASE_DIR, "data")
)

PROJECT_NAME = os.getenv("PROJECT_NAME", "MySeriesVideo")
APP_VERSION = os.getenv("APP_VERSION", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
IS_PRODUCTION = env_flag("IS_PRODUCTION") or (
    os.getenv("FLASK_ENV", "").strip().lower() == "production"
)

TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY", "")
TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "")
TURNSTILE_ALLOWED_HOSTNAMES = {
    item.strip().lower()
    for item in os.getenv("TURNSTILE_ALLOWED_HOSTNAMES", "").split(",")
    if item.strip()
}
TURNSTILE_REQUIRED = env_flag("TURNSTILE_REQUIRED", default=False)
TURNSTILE_WIDGET_ENABLED = bool(TURNSTILE_SITE_KEY)
TURNSTILE_VERIFY_ENABLED = bool(TURNSTILE_SECRET_KEY)
TURNSTILE_ENABLED = TURNSTILE_WIDGET_ENABLED

BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL", "").strip()
BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", PROJECT_NAME).strip() or PROJECT_NAME

OTP_EXPIRE_MINUTES = 10
OTP_MAX_ATTEMPTS = 5

# Video download settings
VIDEO_PROXY_TIMEOUT = 15
VIDEO_STREAM_CHUNK_SIZE = 1024 * 1024

DEFAULT_VIDEO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

if TURNSTILE_REQUIRED and not (TURNSTILE_WIDGET_ENABLED and TURNSTILE_VERIFY_ENABLED):
    raise RuntimeError(
        "Turnstile is required in this environment. Set TURNSTILE_SITE_KEY and "
        "TURNSTILE_SECRET_KEY before starting the app."
    )


def ensure_storage_directories():
    os.makedirs(DATA_DIR, exist_ok=True)


ensure_storage_directories()


def ensure_data_dir_ready(path: str) -> None:
    if not path:
        raise RuntimeError("DATA_DIR ว่าง")

    abs_path = os.path.abspath(path)
    if abs_path == BASE_DIR:
        raise RuntimeError("DATA_DIR ห้ามชี้ไปที่โฟลเดอร์โปรเจกต์")

    os.makedirs(abs_path, exist_ok=True)


def covers_dir() -> str:
    if DATA_DIR == BASE_DIR:
        return os.path.join(BASE_DIR, "covers")
    return os.path.join(DATA_DIR, "covers")


DB_PATH = os.path.join(DATA_DIR, "videos.db")
VIDEO_ROOT = os.path.join(DATA_DIR, "video_files")
COVER_ROOT = covers_dir()
EPISODE_COVER_ROOT = os.path.join(DATA_DIR, "episode_covers")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(VIDEO_ROOT, exist_ok=True)
os.makedirs(COVER_ROOT, exist_ok=True)
os.makedirs(EPISODE_COVER_ROOT, exist_ok=True)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=365)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024 * 15


def normalize_email(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    parsed = parseaddr(text)[1].strip()
    return parsed.lower()


def get_client_ip() -> str | None:
    candidates = [
        request.headers.get("CF-Connecting-IP"),
        request.headers.get("X-Forwarded-For"),
        request.remote_addr,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        first_ip = candidate.split(",")[0].strip()
        if first_ip:
            return first_ip
    return None


def normalize_public_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def is_safe_public_path(path: str) -> bool:
    normalized = normalize_public_path(path)
    return bool(normalized) and not normalized.startswith("../") and "/../" not in normalized



def guess_mime_type(source: str | None, default: str = "video/mp4") -> str:
    if not source:
        return default
    guessed, _ = mimetypes.guess_type(source)
    if guessed:
        return guessed
    # fallback for common direct media URLs without an extension
    lowered = source.lower()
    if any(token in lowered for token in (".m3u8", "application/vnd.apple.mpegurl")):
        return "application/vnd.apple.mpegurl"
    return default


def media_kind_from_mime(mime_type: str | None) -> str:
    if mime_type and mime_type.startswith("audio/"):
        return "audio"
    return "video"


# ---------------------------
# iOS compatibility helpers
# ---------------------------
IOS_VIDEO_CODEC = "h264"
IOS_AUDIO_CODEC = "aac"


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def ffprobe_info(path: str) -> dict | None:
    """Return ffprobe JSON for a media file, or None when ffprobe is unavailable/failed."""
    if not ffprobe_available():
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout or "{}") or None
    except Exception:
        return None


def is_ios_playable_mp4(path: str) -> bool:
    """Best-effort check: MP4 container + H.264 video + AAC audio (or no audio)."""
    info = ffprobe_info(path)
    if not info:
        return False

    fmt = (info.get("format") or {}).get("format_name") or ""
    fmt = str(fmt).lower()
    if "mp4" not in fmt and "mov" not in fmt:
        return False

    video_codec = None
    audio_codec = None
    for stream in info.get("streams") or []:
        if not isinstance(stream, dict):
            continue
        stype = stream.get("codec_type")
        codec = (stream.get("codec_name") or "").lower()
        if stype == "video" and not video_codec:
            video_codec = codec
        if stype == "audio" and not audio_codec:
            audio_codec = codec

    if video_codec and video_codec != IOS_VIDEO_CODEC:
        return False
    if audio_codec and audio_codec != IOS_AUDIO_CODEC:
        return False
    return True


def ensure_ios_compatible_mp4(input_path: str) -> str:
    """
    Convert/remux a local media file to an iOS-friendly MP4.

    - If the file is already MP4 (H.264/AAC), we remux with `+faststart` (no re-encode).
    - Otherwise, we transcode to H.264/AAC + `+faststart`.
    - Returns the final MP4 path (may differ from input_path when input is not .mp4).

    This is designed to run at *ingestion time* (upload/Drive/YouTube), not per-request.
    """
    if not input_path or not os.path.exists(input_path):
        return input_path
    if not ffmpeg_available():
        # Can't convert without ffmpeg; keep original.
        return input_path

    base, ext = os.path.splitext(input_path)
    output_path = input_path if ext.lower() == ".mp4" else base + ".mp4"
    tmp_path = output_path + ".tmp"

    def _run(cmd: list[str]) -> bool:
        try:
            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            return True
        except Exception:
            return False

    # 1) If MP4: try a faststart remux (no re-encode).
    # If ffprobe is available, only trust the copy-remux as "done" when the codecs are iOS-friendly.
    # If ffprobe is NOT available, we still do a copy-remux (better streaming) and stop there.
    if ext.lower() == ".mp4" and (not ffprobe_available() or is_ios_playable_mp4(input_path)):
        ok = _run(["ffmpeg", "-y", "-i", input_path, "-map", "0", "-c", "copy", "-movflags", "+faststart", tmp_path])
        if ok and os.path.exists(tmp_path):
            try:
                os.replace(tmp_path, output_path)
            except Exception:
                pass
            return output_path

    # 2) Otherwise -> transcode to H.264/AAC MP4.
    ok = _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-map",
            "0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-profile:v",
            "baseline",
            "-level",
            "3.1",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            tmp_path,
        ]
    )
    if ok and os.path.exists(tmp_path):
        try:
            os.replace(tmp_path, output_path)
        except Exception:
            pass
        if output_path != input_path:
            try:
                os.remove(input_path)
            except Exception:
                pass
        return output_path

    # Conversion failed; keep original.
    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except Exception:
        pass
    return input_path


def resolve_video_path(file_path: str | None) -> str | None:
    if not file_path:
        return None
    if os.path.isabs(file_path):
        return file_path

    normalized = file_path.replace("/", os.sep)
    candidates = [
        os.path.join(DATA_DIR, normalized),
        os.path.join(BASE_DIR, normalized),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return candidates[0]


def resolve_cover_path(file_path: str | None) -> str | None:
    if not file_path:
        return None
    if os.path.isabs(file_path):
        return file_path
    if not is_safe_public_path(file_path):
        return None

    normalized = file_path.replace("/", os.sep)
    candidates = []
    if DATA_DIR != BASE_DIR:
        candidates.append(os.path.join(DATA_DIR, normalized))
    candidates.append(os.path.join(STATIC_DIR, normalized))
    candidates.append(os.path.join(BASE_DIR, normalized))

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return candidates[0] if candidates else None


def resolve_file_for_public_path(relative_path: str) -> str | None:
    if not relative_path or not is_safe_public_path(relative_path):
        return None

    normalized = normalize_public_path(relative_path)
    candidates = [
        os.path.join(VIDEO_ROOT, normalized),
        os.path.join(COVER_ROOT, normalized),
        os.path.join(EPISODE_COVER_ROOT, normalized),
        os.path.join(DATA_DIR, normalized),
        os.path.join(BASE_DIR, normalized),
        os.path.join(STATIC_DIR, normalized),
    ]

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return candidates[0] if candidates else None


def media_url(file_path: str) -> str:
    normalized = normalize_public_path(file_path)
    return url_for("media_file", filename=normalized)


# ---------- Database init ----------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            thumbnail_url TEXT,
            created_at TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            episode_number INTEGER,
            source_type TEXT DEFAULT 'direct',
            video_url TEXT,
            drive_id TEXT,
            file_path TEXT,
            thumbnail_url TEXT,
            created_at TEXT,
            FOREIGN KEY(series_id) REFERENCES series(id) ON DELETE CASCADE
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            plain_password TEXT,
            user_key TEXT UNIQUE,
            email TEXT,
            created_at TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS watch_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            series_id INTEGER NOT NULL,
            episode_id INTEGER NOT NULL,
            watched_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(series_id) REFERENCES series(id) ON DELETE CASCADE,
            FOREIGN KEY(episode_id) REFERENCES episodes(id) ON DELETE CASCADE
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS password_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS otp_challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_id TEXT UNIQUE NOT NULL,
            purpose TEXT NOT NULL,
            email TEXT NOT NULL,
            code_hash TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            last_sent_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            verified_at TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS backup_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backup_type TEXT NOT NULL,
            file_name TEXT NOT NULL,
            operation TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


init_db()

# ---------- Helpers ----------

def get_setting(key: str, default: str = "") -> str:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row is None:
        return default
    return row[0] if row[0] is not None else default


def set_setting(key: str, value: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def generate_user_key() -> str:
    return secrets.token_hex(8)


def validate_password_strength(password: str) -> tuple[bool, str]:
    if len(password) < 6:
        return False, "รหัสผ่านต้องอย่างน้อย 6 ตัวอักษร"
    return True, ""


def hash_otp_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def verify_turnstile(token, remote_ip=None):
    """Validate a Turnstile token with Cloudflare Siteverify."""
    if not TURNSTILE_VERIFY_ENABLED:
        return not TURNSTILE_REQUIRED

    if not token:
        return False

    try:
        resp = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={
                "secret": TURNSTILE_SECRET_KEY,
                "response": token,
                "remoteip": remote_ip or "",
                "idempotency_key": str(uuid4()),
            },
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            app.logger.warning(
                "Turnstile validation failed: %s",
                ", ".join(data.get("error-codes", [])) or "unknown-error",
            )
            return False

        hostname = str(data.get("hostname") or "").strip().lower()
        if TURNSTILE_ALLOWED_HOSTNAMES and hostname not in TURNSTILE_ALLOWED_HOSTNAMES:
            app.logger.warning("Turnstile hostname mismatch: %s", hostname or "missing")
            return False

        return True
    except Exception:
        return False


def no_store(rendered_html):
    """ห่อ response ของหน้าที่ต้องไม่ถูกแคช/เก็บใน bfcache ของเบราว์เซอร์
    ใช้กับหน้า OTP และหน้าฟอร์มต้นทาง (สมัคร/กู้บัญชี/เปลี่ยนอีเมล) เพื่อให้กดปุ่มย้อนกลับ
    แล้วเบราว์เซอร์ต้องขอหน้าใหม่จากเซิร์ฟเวอร์จริง ๆ แทนที่จะโชว์หน้า OTP ที่ค้างอยู่ใน cache"""
    response = make_response(rendered_html)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def parse_range_header(range_header: str | None, total_size: int | None = None):
    """Parse a simple single-range header and return (start, end)."""
    if not range_header:
        return None

    match = re.match(r"bytes=(\d*)-(\d*)", range_header.strip(), re.IGNORECASE)
    if not match:
        return "invalid"

    start_text, end_text = match.groups()
    if not start_text and not end_text:
        return "invalid"

    try:
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else None
        else:
            if total_size is None:
                return None
            suffix_length = int(end_text)
            if suffix_length <= 0:
                return "invalid"
            start = max(total_size - suffix_length, 0)
            end = total_size - 1
    except ValueError:
        return "invalid"

    if start < 0:
        return "invalid"

    if total_size is not None:
        if start >= total_size:
            return "invalid"
        if end is None or end >= total_size:
            end = total_size - 1

    if end is not None and end < start:
        return "invalid"

    return start, end


def iter_remote_video_chunks(upstream_response, start=0, end=None):
    """Yield video bytes while optionally trimming to the requested byte range."""
    position = 0
    remaining = None if end is None else (end - start + 1)

    try:
        for chunk in upstream_response.iter_content(chunk_size=VIDEO_STREAM_CHUNK_SIZE):
            if not chunk:
                continue

            chunk_start = position
            chunk_end = position + len(chunk) - 1
            position = chunk_end + 1

            if chunk_end < start:
                continue

            if chunk_start < start:
                chunk = chunk[start - chunk_start :]
                chunk_start = start

            if remaining is not None and len(chunk) > remaining:
                chunk = chunk[:remaining]

            if chunk:
                yield chunk

            if remaining is not None:
                remaining -= len(chunk)
                if remaining <= 0:
                    break
    finally:
        upstream_response.close()


def stream_remote_video(video_url: str):
    """Proxy remote MP4 URLs through this app so every client gets consistent headers."""
    range_header = request.headers.get("Range")
    upstream_headers = dict(DEFAULT_VIDEO_HEADERS)
    if range_header:
        upstream_headers["Range"] = range_header

    try:
        upstream = requests.get(
            video_url,
            headers=upstream_headers,
            stream=True,
            allow_redirects=True,
            timeout=VIDEO_PROXY_TIMEOUT,
        )
    except requests.RequestException:
        abort(502)

    total_size = None
    content_length = upstream.headers.get("Content-Length")
    if content_length:
        try:
            total_size = int(content_length)
        except (TypeError, ValueError):
            total_size = None

    passthrough_headers = {"Accept-Ranges": upstream.headers.get("Accept-Ranges", "bytes")}
    for header_name in ("Cache-Control", "Content-Range", "Content-Type", "ETag", "Last-Modified"):
        value = upstream.headers.get(header_name)
        if value:
            passthrough_headers[header_name] = value

    if "Content-Type" not in passthrough_headers:
        passthrough_headers["Content-Type"] = guess_mime_type(video_url)

    if upstream.status_code == 416:
        if total_size is not None and "Content-Range" not in passthrough_headers:
            passthrough_headers["Content-Range"] = f"bytes */{total_size}"
        upstream.close()
        return Response(status=416, headers=passthrough_headers)

    # Preferred case: the upstream already honors range requests.
    if upstream.status_code in (200, 206) and (not range_header or upstream.status_code == 206):
        if total_size is not None:
            passthrough_headers["Content-Length"] = str(total_size)
        return Response(
            iter_remote_video_chunks(upstream),
            status=upstream.status_code,
            headers=passthrough_headers,
            direct_passthrough=True,
        )

    # Fallback for hosts that ignore Range but still send the whole file.
    if upstream.status_code == 200 and range_header and total_size is not None:
        parsed_range = parse_range_header(range_header, total_size)
        if parsed_range == "invalid":
            upstream.close()
            return Response(
                status=416,
                headers={
                    "Accept-Ranges": "bytes",
                    "Content-Range": f"bytes */{total_size}",
                    "Content-Type": passthrough_headers["Content-Type"],
                },
            )

        if parsed_range:
            start, end = parsed_range
            end = total_size - 1 if end is None else end
            length = end - start + 1
            passthrough_headers["Accept-Ranges"] = "bytes"
            passthrough_headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
            passthrough_headers["Content-Length"] = str(length)
            return Response(
                iter_remote_video_chunks(upstream, start=start, end=end),
                status=206,
                headers=passthrough_headers,
                direct_passthrough=True,
            )

    if upstream.status_code >= 400:
        upstream.close()
        abort(502)

    if total_size is not None:
        passthrough_headers["Content-Length"] = str(total_size)

    return Response(
        iter_remote_video_chunks(upstream),
        status=upstream.status_code,
        headers=passthrough_headers,
        direct_passthrough=True,
    )


@app.route("/media/<path:filename>")
def media_file(filename):
    if not is_safe_public_path(filename):
        abort(404)

    absolute_path = resolve_cover_path(filename)
    if not absolute_path or not os.path.exists(absolute_path):
        abort(404)

    return send_file(absolute_path, conditional=True, max_age=3600)


@app.context_processor
def inject_globals():
    return {
        "TURNSTILE_SITE_KEY": TURNSTILE_SITE_KEY,
        "TURNSTILE_ENABLED": TURNSTILE_ENABLED,
        "media_url": media_url,
        "PROJECT_NAME": PROJECT_NAME,
        "APP_VERSION": APP_VERSION,
        "PUBLIC_BASE_URL": PUBLIC_BASE_URL,
        "CURRENT_YEAR": datetime.utcnow().year,
        # ปิดค่าเริ่มต้นเพื่อให้ระบบ OTP ไม่ถูกเปิดใช้โดยไม่ตั้งใจ (เช่น ยังไม่ได้ตั้งค่าอีเมล)
        "ACCOUNT_RECOVERY_ENABLED": get_setting("account_recovery_enabled", "false").strip().lower() in {"1", "true", "yes", "on"},
    }



# Thai datetime filter
from datetime import datetime, timedelta

def thdt(value):
    try:
        dt=datetime.fromisoformat(value)
    except Exception:
        return value
    dt=dt+timedelta(hours=7)
    return dt.strftime("%Y-%m-%d : %H:%M")

app.jinja_env.filters['thdt']=thdt


# ---------- Admin login defaults (loaded from config) ----------
DEFAULT_ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"
DEFAULT_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1234")

# ค่า login ปัจจุบันในหน่วยความจำ (รีเซ็ตเมื่อรีสตาร์ท)
current_admin_username = DEFAULT_ADMIN_USERNAME
current_admin_password = DEFAULT_ADMIN_PASSWORD


def get_db_connection():
    # SQLite concurrency notes:
    # - Only one writer at a time; concurrent writes can briefly lock the DB.
    # - On busy/slow storage or multiple Gunicorn workers, we should WAIT (busy_timeout)
    #   instead of failing immediately with "database is locked".
    # - WAL mode improves concurrency (readers don't block writers).
    timeout_seconds = int(os.getenv("SQLITE_TIMEOUT", "30") or "30")
    busy_timeout_ms = int(os.getenv("SQLITE_BUSY_TIMEOUT_MS", "30000") or "30000")

    conn = sqlite3.connect(DB_PATH, timeout=timeout_seconds)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms};")
    except Exception:
        # Best-effort only; keep working even if PRAGMA is blocked by environment.
        pass
    return conn


def ensure_episode_thumbnail_column(conn: sqlite3.Connection):
    """เพิ่มคอลัมน์ thumbnail_url ให้ตาราง episodes ถ้ายังไม่มี (ใช้ตอนอัปเดตจากเวอร์ชันเก่า)."""
    cur = conn.execute("PRAGMA table_info(episodes)")
    cols = [row[1] for row in cur.fetchall()]
    if "thumbnail_url" not in cols:
        conn.execute("ALTER TABLE episodes ADD COLUMN thumbnail_url TEXT")
        conn.commit()

# (truncated for brevity)
