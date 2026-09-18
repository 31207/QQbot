"""搜索结果 / 点歌记录图片渲染（Pillow，同步函数，调用方用 asyncio.to_thread 包装）。"""

from __future__ import annotations

import io
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from radio.util import format_short_time

logger = logging.getLogger("radio.render")

WIDTH = 920
PAD = 28
ROW_H = 96
HEADER_H = 118
FOOTER_H = 52
COVER_SIZE = 76
COVER_RADIUS = 10

BG = (245, 246, 248)
ROW_BG = (255, 255, 255)
ROW_ALT = (250, 251, 253)
DIVIDER = (229, 231, 236)
TEXT_MAIN = (33, 37, 43)
TEXT_SUB = (128, 134, 143)
ACCENT = (76, 141, 255)
PLACEHOLDER_BG = (235, 238, 242)

SOURCE_NAMES = {
    "netease": "网易云",
    "qq": "QQ音乐",
    "kugou": "酷狗",
    "kuwo": "酷我",
    "migu": "咪咕",
    "joox": "JOOX",
    "soda": "汽水",
    "jamendo": "Jamendo",
    "qianqian": "千千",
    "bilibili": "B站",
    "fivesing": "5sing",
}

SOURCE_COLORS = {
    "netease": (227, 59, 59),
    "qq": (49, 194, 124),
    "kugou": (44, 166, 248),
    "kuwo": (255, 126, 5),
    "migu": (255, 62, 77),
    "soda": (58, 130, 246),
}

_REGULAR_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-DemiLight.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-DemiLight.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/Deng.ttf",
)
_BOLD_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Medium.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
)

_CJK_NAME_KEYWORDS = (
    "cjk", "uming", "ukai", "wqy", "microhei", "zenhei",
    "sourcehansans", "notosanssc", "notoserifsc", "msyh", "simhei", "simsun", "deng",
)
_BOLD_NAME_KEYWORDS = ("bold", "medium", "black", "semibold")


def _fc_match_file(pattern: str) -> str | None:
    """用 fontconfig 按 pattern 查询字体文件路径；不可用返回 None。"""
    try:
        out = subprocess.run(
            ["fc-match", "-f", "%{file}", pattern],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    path = (out.stdout or "").strip().splitlines()[:1]
    return path[0].strip() if path and path[0].strip() else None


def _scan_cjk_fonts() -> list[Path]:
    """扫描常见字体目录下的 CJK 字体（fontconfig 不可用时兜底）。"""
    roots = (
        Path("/usr/share/fonts"),
        Path.home() / ".fonts",
        Path.home() / ".local/share/fonts",
    )
    found: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in (".ttf", ".ttc", ".otf"):
                continue
            if any(k in path.name.lower() for k in _CJK_NAME_KEYWORDS):
                found.append(path)
    return sorted(set(found))


def _resolve_fonts() -> tuple[str | None, str | None]:
    """解析常规/加粗 CJK 字体：显式候选 → fontconfig → 目录扫描。"""
    regular = next((p for p in _REGULAR_CANDIDATES if os.path.exists(p)), None)
    bold = next((p for p in _BOLD_CANDIDATES if os.path.exists(p)), None)

    if regular is None:
        for pattern in ("sans-serif:lang=zh-cn", "sans-serif:lang=zh"):
            candidate = _fc_match_file(pattern)
            if candidate and os.path.exists(candidate):
                regular = candidate
                break
    if bold is None:
        if regular is not None:
            candidate = _fc_match_file("sans-serif:lang=zh-cn:weight=bold")
            bold = candidate if candidate and os.path.exists(candidate) else regular
        else:
            bold = None

    if regular is None:
        scanned = _scan_cjk_fonts()
        if scanned:
            regular = str(scanned[0])
            bold_picks = [
                str(p) for p in scanned if any(k in p.name.lower() for k in _BOLD_NAME_KEYWORDS)
            ]
            bold = bold_picks[0] if bold_picks else regular
    return regular, bold


_REGULAR_FILE, _BOLD_FILE = _resolve_fonts()

if _REGULAR_FILE is None:
    logger.warning(
        "未找到任何中文字体，渲染图片中的中文将显示为方框；"
        "请安装中文字体（Debian/Ubuntu: fonts-noto-cjk，Arch: noto-fonts-cjk）"
    )


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = _BOLD_FILE if bold else _REGULAR_FILE
    if path:
        for index in (2, 0):
            try:
                return ImageFont.truetype(path, size, index=index)
            except OSError:
                continue
    return ImageFont.load_default(size)


def _truncate(draw: ImageDraw.ImageDraw, text: str, font, max_w: float) -> str:
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return f"{text}…" if text else ""


def _fmt_duration(seconds) -> str:
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return "--:--"
    return f"{total // 60:02d}:{total % 60:02d}"


def _center_crop(img: Image.Image, size: int) -> Image.Image:
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side)).resize(
        (size, size), Image.LANCZOS
    )


def _rounded(img: Image.Image, radius: int) -> Image.Image:
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle(
        (0, 0, img.size[0] - 1, img.size[1] - 1), radius=radius, fill=255
    )
    img.putalpha(mask)
    return img


def _draw_cover(
    canvas: Image.Image,
    pos: tuple[int, int],
    cover,
    size: int = COVER_SIZE,
    radius: int = COVER_RADIUS,
) -> None:
    x, y = pos
    if cover is not None:
        img = _rounded(_center_crop(cover, size), radius)
        canvas.paste(img, (x, y), img)
        return
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle(
        (x, y, x + size - 1, y + size - 1),
        radius=radius,
        fill=PLACEHOLDER_BG,
    )
    note_font = _font(30)
    note = "♪"
    tw = d.textlength(note, font=note_font)
    d.text(
        (x + (size - tw) / 2, y + size / 2 - 22),
        note,
        font=note_font,
        fill=(170, 175, 182),
    )


def render_page(
    query: str,
    source_label: str,
    songs: list[dict],
    page: int,
    page_size: int,
    total_pages: int,
    total: int,
    covers: dict[str, Image.Image | None],
) -> bytes:
    """把一页歌曲画成 PNG。covers 以封面 URL 为键。"""
    height = HEADER_H + len(songs) * ROW_H + FOOTER_H
    canvas = Image.new("RGB", (WIDTH, height), BG)
    d = ImageDraw.Draw(canvas)

    f_title = _font(34, bold=True)
    f_sub = _font(22)
    f_index = _font(22, bold=True)
    f_name = _font(26, bold=True)
    f_meta = _font(21)
    f_right = _font(21)
    f_right_bold = _font(21, bold=True)
    f_footer = _font(20)

    d.text((PAD, 20), f"搜索「{_truncate(d, query, f_title, WIDTH - PAD * 2)}」",
           font=f_title, fill=TEXT_MAIN)
    sub = f"平台：{source_label}    共 {total} 条    第 {page}/{total_pages} 页"
    d.text((PAD, 78), sub, font=f_sub, fill=TEXT_SUB)
    d.line((PAD, HEADER_H - 1, WIDTH - PAD, HEADER_H - 1), fill=DIVIDER, width=2)

    index_x = PAD
    cover_x = PAD + 46
    text_x = cover_x + COVER_SIZE + 18
    right_x = WIDTH - PAD

    for i, song in enumerate(songs):
        y0 = HEADER_H + i * ROW_H
        d.rectangle((0, y0, WIDTH, y0 + ROW_H), fill=ROW_ALT if i % 2 else ROW_BG)

        global_no = (page - 1) * page_size + i + 1
        d.text((index_x, y0 + ROW_H / 2 - 14), f"{global_no:02d}",
               font=f_index, fill=TEXT_SUB)

        cover = covers.get(song.get("cover") or "")
        _draw_cover(canvas, (cover_x, y0 + (ROW_H - COVER_SIZE) // 2), cover)

        name = song.get("name") or "未知歌曲"
        artist = song.get("artist") or "未知歌手"
        album = song.get("album") or ""
        meta = f"{artist} · {album}" if album else artist
        max_text_w = right_x - text_x - 150
        d.text((text_x, y0 + 16), _truncate(d, name, f_name, max_text_w),
               font=f_name, fill=TEXT_MAIN)
        d.text((text_x, y0 + 56), _truncate(d, meta, f_meta, max_text_w),
               font=f_meta, fill=TEXT_SUB)

        source = song.get("source") or ""
        src_name = SOURCE_NAMES.get(source, source)
        src_color = SOURCE_COLORS.get(source, ACCENT)
        d.text((right_x, y0 + 22), src_name, font=f_right_bold, fill=src_color,
               anchor="ra")
        dur = _fmt_duration(song.get("duration"))
        bitrate = song.get("bitrate")
        right_info = f"{dur} · {bitrate}kbps" if bitrate else dur
        d.text((right_x, y0 + 56), right_info, font=f_right, fill=TEXT_SUB,
               anchor="ra")

        if i < len(songs) - 1:
            d.line((PAD, y0 + ROW_H - 1, WIDTH - PAD, y0 + ROW_H - 1),
                   fill=DIVIDER, width=1)

    footer = "回复「上一页」/「下一页」翻页 · 回复「退出搜索」结束"
    fy = HEADER_H + len(songs) * ROW_H + (FOOTER_H - 24) / 2
    d.text((WIDTH / 2, fy), footer, font=f_footer, fill=TEXT_SUB, anchor="ma")

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


RECORD_ROW_H = 104


def render_records(
    records: list[dict],
    covers: dict[str, Image.Image | None],
    total: int,
) -> bytes:
    """把点歌记录画成 PNG。records 需含 name/artist/album/cover/source/song_id/time/remark。"""
    height = HEADER_H + len(records) * RECORD_ROW_H + FOOTER_H
    canvas = Image.new("RGB", (WIDTH, height), BG)
    d = ImageDraw.Draw(canvas)

    f_title = _font(34, bold=True)
    f_sub = _font(22)
    f_index = _font(22, bold=True)
    f_name = _font(26, bold=True)
    f_meta = _font(21)
    f_remark = _font(20)
    f_right = _font(20)
    f_right_bold = _font(20, bold=True)
    f_footer = _font(20)

    d.text((PAD, 20), "我的歌单", font=f_title, fill=TEXT_MAIN)
    sub = f"共 {total} 条    生成于 {datetime.now():%Y-%m-%d %H:%M}"
    d.text((PAD, 78), sub, font=f_sub, fill=TEXT_SUB)
    d.line((PAD, HEADER_H - 1, WIDTH - PAD, HEADER_H - 1), fill=DIVIDER, width=2)

    index_x = PAD
    cover_x = PAD + 46
    text_x = cover_x + COVER_SIZE + 18
    right_x = WIDTH - PAD

    for i, r in enumerate(records):
        y0 = HEADER_H + i * RECORD_ROW_H
        d.rectangle(
            (0, y0, WIDTH, y0 + RECORD_ROW_H), fill=ROW_ALT if i % 2 else ROW_BG
        )

        d.text((index_x, y0 + RECORD_ROW_H / 2 - 14), f"{i + 1:02d}",
               font=f_index, fill=TEXT_SUB)

        _draw_cover(canvas, (cover_x, y0 + (RECORD_ROW_H - COVER_SIZE) // 2),
                    covers.get(r.get("cover") or ""))

        name = r.get("name") or "未知歌曲"
        artist = r.get("artist") or "未知歌手"
        album = r.get("album") or ""
        meta = f"{artist} · {album}" if album else artist
        remark = (r.get("remark") or "").strip()
        max_text_w = right_x - text_x - 150

        d.text((text_x, y0 + 10), _truncate(d, name, f_name, max_text_w),
               font=f_name, fill=TEXT_MAIN)
        d.text((text_x, y0 + 42), _truncate(d, meta, f_meta, max_text_w),
               font=f_meta, fill=TEXT_SUB)
        if remark:
            d.text((text_x, y0 + 72),
                   _truncate(d, f"备注：{remark}", f_remark, max_text_w),
                   font=f_remark, fill=ACCENT)

        source = r.get("source") or ""
        d.text((right_x, y0 + 12), SOURCE_NAMES.get(source, source),
               font=f_right_bold, fill=SOURCE_COLORS.get(source, ACCENT),
               anchor="ra")
        d.text((right_x, y0 + 40), format_short_time(r.get("time")),
               font=f_right, fill=TEXT_SUB, anchor="ra")
        d.text((right_x, y0 + 68), f"[编号{r.get('song_id')}]",
               font=f_right, fill=TEXT_SUB, anchor="ra")

        if i < len(records) - 1:
            d.line((PAD, y0 + RECORD_ROW_H - 1, WIDTH - PAD, y0 + RECORD_ROW_H - 1),
                   fill=DIVIDER, width=1)

    footer = "「备注 编号 内容」添加备注 ·「备注 编号」清除备注"
    fy = HEADER_H + len(records) * RECORD_ROW_H + (FOOTER_H - 24) / 2
    d.text((WIDTH / 2, fy), footer, font=f_footer, fill=TEXT_SUB, anchor="ma")

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------- 播放历史卡片图

HISTORY_CARD_H = 132
HISTORY_COVER = 100


def render_history_image(
    range_label: str,
    records: list[dict],
    covers: dict[str, Image.Image | None],
) -> bytes:
    """把一段播放历史画成卡片式长图。

    records 需含 name/artist/cover/played_at/user_id/note；
    covers 以封面 URL 为键，封面缺失时绘制占位符。
    """
    total = len(records)
    height = HEADER_H + 40 + total * HISTORY_CARD_H + FOOTER_H
    canvas = Image.new("RGB", (WIDTH, height), BG)
    d = ImageDraw.Draw(canvas)

    f_title = _font(34, bold=True)
    f_sub = _font(22)
    f_name = _font(28, bold=True)
    f_artist = _font(22)
    f_meta = _font(20)
    f_footer = _font(20)

    d.text((PAD, 20), "校园广播站 · 播放记录", font=f_title, fill=TEXT_MAIN)
    sub = f"{range_label}    共 {total} 首"
    d.text((PAD, 78), sub, font=f_sub, fill=TEXT_SUB)
    d.line((PAD, HEADER_H - 1, WIDTH - PAD, HEADER_H - 1), fill=DIVIDER, width=2)

    card_h = HISTORY_CARD_H - 16
    cover_size = HISTORY_COVER
    for i, r in enumerate(records):
        y0 = HEADER_H + 32 + i * HISTORY_CARD_H
        d.rounded_rectangle(
            (PAD, y0, WIDTH - PAD, y0 + card_h),
            radius=12,
            fill=ROW_BG,
            outline=DIVIDER,
        )
        _draw_cover(
            canvas,
            (PAD + 16, y0 + (card_h - cover_size) // 2),
            covers.get(r.get("cover") or ""),
            size=cover_size,
        )

        text_x = PAD + 16 + cover_size + 22
        right_x = WIDTH - PAD - 16
        max_text_w = right_x - text_x - 190

        name = r.get("name") or "未知歌曲"
        artist = r.get("artist") or "未知歌手"
        d.text((text_x, y0 + 20), _truncate(d, name, f_name, max_text_w), font=f_name, fill=TEXT_MAIN)
        d.text((text_x, y0 + 62), _truncate(d, artist, f_artist, max_text_w), font=f_artist, fill=TEXT_SUB)

        meta_parts = []
        if r.get("user_id"):
            meta_parts.append(f"点歌人 {r['user_id']}")
        if meta_parts:
            d.text(
                (text_x, y0 + 96),
                _truncate(d, " · ".join(meta_parts), f_meta, max_text_w),
                font=f_meta,
                fill=ACCENT,
            )

        time_text = format_short_time(r.get("played_at"))
        d.text((right_x, y0 + 38), time_text, font=f_meta, fill=TEXT_SUB, anchor="ra")

    footer = "生成于 " + datetime.now().strftime("%Y-%m-%d %H:%M")
    fy = HEADER_H + 32 + total * HISTORY_CARD_H + (FOOTER_H - 24) / 2
    d.text((WIDTH / 2, fy), footer, font=f_footer, fill=TEXT_SUB, anchor="ma")

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()
