#!/usr/bin/env python3
"""
퍼스트메디스킨(@firstmediskin_) 게시물 이미지 생성기 (1080x1350 JPEG)

tools/posts.json 을 읽어 저장소 루트에 mediskin_YYYYMMDD_NN.jpg 를 만들고
content_queue.json 에 신규 날짜 항목만 추가합니다. (이미 있는 항목·게시완료 항목은 보존)

템플릿
  mood   : 사진(상단) + 아이보리 패널(하단) 손글씨 헤드라인 + 로고   ← 감성 단일 이미지
  cover  : 풀사진 + 어두운 톤 + 민트 태그 + 굵은 흰 제목            ← 캐러셀 표지
  list   : 풀사진 + 제목 + 불릿/번호 목록                         ← 캐러셀 본문
  cta    : 풀사진 + 마무리 문구 + 예약 안내                        ← 캐러셀 마지막

사용법
  python tools/make_posts.py                  # 전체 (신규 날짜만 큐에 추가)
  python tools/make_posts.py 2026-10-06       # 특정 날짜만
  python tools/make_posts.py 2026-10-06 --force  # 아직 안 올라간 항목 내용 교체
사진 폴더: 환경변수 PHOTO_DIR (기본 tools/assets/photos). 파일명은 확장자 없이 적어도 됩니다.
로고는 홈페이지와 같은 "First Mediskin" 워드마크(Cormorant Garamond, 골드)로 그립니다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent          # tools/
REPO = ROOT.parent                              # 저장소 루트 (게시 이미지·큐 위치)
FONTS = ROOT / "assets" / "fonts"
PHOTO_DIR = Path(os.environ.get("PHOTO_DIR", ROOT / "assets" / "photos"))
W, H = 1080, 1350

C = {
    "ivory": (243, 238, 230),
    "navy": (46, 72, 104),
    "gray": (138, 130, 120),
    "gold": (176, 141, 87),
    "gold_light": (214, 186, 140),
    "white": (255, 255, 255),
    "mint_bg": (214, 238, 232),
    "mint_fg": (62, 127, 116),
    "mint_text": (170, 225, 214),
    "slate": (34, 46, 56),
}


def F(name: str, size: int) -> ImageFont.FreeTypeFont:
    files = {
        "pen": "NanumPenScript-Regular.ttf",
        "myeongjo": "NanumMyeongjo-Regular.ttf",
        "sans": "NanumGothic-Regular.ttf",
        "sans_b": "NanumGothic-Bold.ttf",
        "sans_xb": "NanumGothic-ExtraBold.ttf",
    }
    return ImageFont.truetype(str(FONTS / files[name]), size)


# ------------------------------------------------------------------ helpers
def load_photo(name: str) -> Image.Image:
    for cand in (PHOTO_DIR / name, *(PHOTO_DIR / f"{name}{e}" for e in (".jpg", ".png", ".jpeg"))):
        if cand.exists():
            return Image.open(cand).convert("RGB")
    raise SystemExit(f"사진을 찾을 수 없습니다: {name} (폴더: {PHOTO_DIR})")


def cover_crop(img: Image.Image, w: int, h: int, focus_y: float = 0.35) -> Image.Image:
    """비율 유지하며 w×h 를 꽉 채우도록 확대 후 자르기. focus_y: 0=위쪽, 1=아래쪽 기준."""
    s = max(w / img.width, h / img.height)
    im = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    x = (im.width - w) // 2
    y = int((im.height - h) * min(max(focus_y, 0), 1))
    return im.crop((x, y, x + w, y + h))


def center_text(d: ImageDraw.ImageDraw, y: int, text: str, font, fill, shadow: bool = False, spacing: float = 1.25) -> int:
    for line in text.split("\n"):
        w = d.textlength(line, font=font)
        x = (W - w) / 2
        if shadow:
            d.text((x + 2, y + 3), line, font=font, fill=(0, 0, 0, 90))
        d.text((x, y), line, font=font, fill=fill)
        y += int(font.size * spacing)
    return y


def logo(img: Image.Image, y: int, dark: bool) -> None:
    """홈페이지(firstmediskin.com) 로고와 같은 'First Mediskin' 워드마크.
    글꼴 Cormorant Garamond, 골드 #C9A24C, 자간 약간 넓게. y = 글자 윗선."""
    d = ImageDraw.Draw(img, "RGBA")
    f = ImageFont.truetype(str(FONTS / "CormorantGaramond.ttf"), 54)
    f.set_variation_by_name("Medium")
    text, track = "First Mediskin", 3
    widths = [d.textlength(ch, font=f) for ch in text]
    total = sum(widths) + track * (len(text) - 1)
    x = (W - total) / 2
    col = (214, 178, 96) if dark else (201, 162, 76)
    for ch, w in zip(text, widths):
        if dark:
            d.text((x + 1, y + 2), ch, font=f, fill=(0, 0, 0, 90))
        d.text((x, y), ch, font=f, fill=col)
        x += w + track


# ---- 모바일 레이아웃 기준 (1080x1350, 4:5) --------------------------------
# · 좌우 여백 96px: 프로필 그리드(3:4)에서 좌우 34px씩 잘려도 글자가 안전
# · 글자는 하단 1/3에 배치: 얼굴(상단)을 가리지 않고, 엄지로 넘길 때 시선이 머무는 위치
# · 본문 최소 46px(폰에서 약 15pt), 보조 문구 32px 이상
# · 로고는 맨 아래 고정, 텍스트 블록은 로고 위에 아래 기준 정렬
SIDE = 96
LOGO_Y = 1232          # 로고 윗선
TEXT_BOTTOM = 1172     # 텍스트 블록 아랫선
MAX_W = W - SIDE * 2


def fit(d, text: str, name: str, size: int, max_w: int = MAX_W, min_size: int = 30):
    """가장 긴 줄이 max_w 를 넘지 않도록 글자 크기를 줄임."""
    while size > min_size:
        f = F(name, size)
        if max(d.textlength(l, font=f) for l in text.split("\n")) <= max_w:
            return f
        size -= 2
    return F(name, size)


def block_h(text: str, font, spacing: float) -> int:
    n = len(text.split("\n"))
    return int(font.size * spacing) * (n - 1) + font.size


def photo_bg(s: dict) -> Image.Image:
    """풀사진 + 전체 톤 다운 + 하단 텍스트 영역을 위한 그라데이션."""
    zoom = s.get("zoom", 1.0)
    im = load_photo(s["photo"])
    im = cover_crop(im, int(W * zoom), int(H * zoom), 0.5)
    x = (im.width - W) // 2
    y = int((im.height - H) * s.get("focus_y", 0.5))
    im = im.crop((x, y, x + W, y + H))
    im = Image.blend(im, Image.new("RGB", (W, H), C["slate"]), 0.14)
    grad = Image.new("L", (1, H))
    start = s.get("_grad_start", 620)
    for yy in range(H):
        t = max(0.0, (yy - start) / (H - start))
        grad.putpixel((0, yy), int(255 * min(0.86, 0.08 + 0.9 * t ** 0.9)))
    return Image.composite(Image.new("RGB", (W, H), (18, 26, 34)), im, grad.resize((W, H)))


def draw_center(d, y: int, text: str, font, fill, spacing: float, shadow: bool = True) -> int:
    lh = int(font.size * spacing)
    for line in text.split("\n"):
        x = (W - d.textlength(line, font=font)) / 2
        if shadow:
            d.text((x + 2, y + 3), line, font=font, fill=(0, 0, 0, 110))
        d.text((x, y), line, font=font, fill=fill)
        y += lh
    return y - lh + font.size


def pill(d, y: int, text: str) -> int:
    f = F("sans_b", 32)
    tw = d.textlength(text, font=f)
    pw, ph = tw + 52, 60
    x = (W - pw) / 2
    d.rounded_rectangle((x, y, x + pw, y + ph), radius=ph // 2, fill=C["mint_bg"])
    d.text((x + 26, y + 12), text, font=f, fill=C["mint_fg"])
    return y + ph


# ------------------------------------------------------------------ templates
def t_mood(s: dict) -> Image.Image:
    img = Image.new("RGB", (W, H), C["ivory"])
    ph = 850
    img.paste(cover_crop(load_photo(s["photo"]), W, ph, s.get("focus_y", 0.3)), (0, 0))
    d = ImageDraw.Draw(img)
    d.line((0, ph, W, ph), fill=C["gold_light"], width=3)
    f_t = fit(d, s["title"], "pen", 112, max_w=W - 2 * 80)
    f_s = fit(d, s.get("subtitle", " "), "myeongjo", 38)
    total = block_h(s["title"], f_t, 1.08) + 26 + f_s.size
    y = ph + (LOGO_Y - 40 - ph - total) // 2
    y = draw_center(d, y, s["title"], f_t, C["navy"], 1.08, shadow=False)
    draw_center(d, y + 26, s.get("subtitle", ""), f_s, C["gray"], 1.4, shadow=False)
    logo(img, LOGO_Y, dark=False)
    return img


def t_cover(s: dict) -> Image.Image:
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    f_t = fit(probe, s["title"], "sans_xb", 104)
    f_s = F("sans_b", 42)
    h = (60 + 30 if s.get("tag") else 0) + block_h(s["title"], f_t, 1.18) + (24 + f_s.size if s.get("subtitle") else 0)
    top = TEXT_BOTTOM - h
    img = photo_bg(s | {"_grad_start": max(360, top - 320)})
    d = ImageDraw.Draw(img, "RGBA")
    y = top
    if s.get("tag"):
        y = pill(d, y, s["tag"]) + 30
    y = draw_center(d, y, s["title"], f_t, C["white"], 1.18)
    if s.get("subtitle"):
        draw_center(d, y + 24, s["subtitle"], f_s, (236, 236, 236), 1.3)
    logo(img, LOGO_Y, dark=True)
    return img


def t_list(s: dict) -> Image.Image:
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    items = s["items"]
    f_t = fit(probe, s["title"], "sans_xb", 78)
    f_i = F("sans_b", 50)
    marker_w = 64
    while max(probe.textlength(i, font=f_i) for i in items) > MAX_W - marker_w and f_i.size > 38:
        f_i = F("sans_b", f_i.size - 2)
    row = int(f_i.size * 1.75)
    f_n = F("sans", 32)
    h = block_h(s["title"], f_t, 1.2) + 46 + row * (len(items) - 1) + f_i.size + (34 + f_n.size if s.get("note") else 0)
    top = TEXT_BOTTOM - h
    img = photo_bg(s | {"_grad_start": max(300, top - 300)})
    d = ImageDraw.Draw(img, "RGBA")
    y = draw_center(d, top, s["title"], f_t, C["white"], 1.2) + 46
    widest = max(d.textlength(i, font=f_i) for i in items)
    x = (W - widest - marker_w) / 2
    for i, it in enumerate(items, 1):
        if s.get("numbered"):
            d.text((x, y), str(i), font=F("sans_xb", f_i.size), fill=C["gold_light"])
        else:
            r = 7
            cy = y + f_i.size * 0.55
            d.ellipse((x + 10 - r, cy - r, x + 10 + r, cy + r), fill=C["gold_light"])
        d.text((x + marker_w + 2, y + 3), it, font=f_i, fill=(0, 0, 0, 110))
        d.text((x + marker_w, y), it, font=f_i, fill=C["white"])
        y += row
    if s.get("note"):
        draw_center(d, y - row + f_i.size + 34, s["note"], f_n, (214, 214, 214), 1.3, shadow=False)
    logo(img, LOGO_Y, dark=True)
    return img


def t_cta(s: dict) -> Image.Image:
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    f_t = fit(probe, s["title"], "sans_xb", 96)
    f_s, f_a = F("sans_b", 42), F("sans_b", 38)
    sub = s.get("subtitle", "퍼스트메디스킨이 함께합니다")
    act = s.get("action", "프로필 링크에서 상담 예약")
    h = block_h(s["title"], f_t, 1.18) + 30 + f_s.size + 34 + 68
    top = TEXT_BOTTOM - h
    img = photo_bg(s | {"_grad_start": max(360, top - 320)})
    d = ImageDraw.Draw(img, "RGBA")
    y = draw_center(d, top, s["title"], f_t, C["white"], 1.18)
    y = draw_center(d, y + 30, sub, f_s, (240, 240, 240), 1.3) + 34
    # 예약 버튼 모양 (탭하고 싶어지는 CTA)
    tw = d.textlength(act, font=f_a)
    bw, bh = tw + 80, 68
    bx = (W - bw) / 2
    d.rounded_rectangle((bx, y, bx + bw, y + bh), radius=bh // 2, outline=C["mint_text"], width=3)
    d.text((bx + 40, y + (bh - f_a.size) / 2 - 3), act, font=f_a, fill=C["mint_text"])
    logo(img, LOGO_Y, dark=True)
    return img


TEMPLATES = {"mood": t_mood, "cover": t_cover, "list": t_list, "cta": t_cta}


# ------------------------------------------------------------------ captions & queue
def caption(post: dict, cfg: dict) -> str:
    """캡션 = 훅 + 공통 하단 문구 + 해시태그. 하단 문구·해시태그는 posts.json 의 config 에서 한 번에 관리."""
    tags = " ".join(cfg["hashtags"] + post.get("extra_tags", []))
    if post["kind"] == "mood":
        return f"{post['hook']}\n\n{cfg['mood_footer']}\n\n{tags}"
    return f"{post['hook']}\n{post['hook2']}\n\n{cfg['info_footer']}\n\n{tags}"


def update_queue(entries: list[dict], force: bool = False) -> None:
    """content_queue.json 에 신규 날짜만 추가. 이미 있는 항목(특히 posted=true)은 보존.
    --force 를 주면 '아직 게시 안 된' 기존 항목만 새 내용으로 교체."""
    q = REPO / "content_queue.json"
    queue = json.loads(q.read_text(encoding="utf-8")) if q.exists() else {"items": []}
    queue.setdefault("_설명", "클라우드(GitHub Actions) 자동 게시 대기열. slot=am. "
                     "IMAGE=image_path / CAROUSEL=image_paths(순서대로). posted=true는 게시완료.")
    items = queue.setdefault("items", [])
    idx = {(it.get("date"), it.get("slot")): it for it in items}
    added = replaced = kept = 0
    for e in entries:
        cur = idx.get((e["date"], e["slot"]))
        if cur is None:
            items.append(e); added += 1
        elif not cur.get("posted") and force:
            cur.clear(); cur.update(e); replaced += 1
        else:
            kept += 1
            print(f"  (유지) {e['date']} {'게시완료' if cur.get('posted') else '기존 대기 항목 — 바꾸려면 --force'}")
    items.sort(key=lambda it: (it.get("date", ""), it.get("slot", "")))
    q.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"큐: 추가 {added} · 교체 {replaced} · 유지 {kept}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    only = args[0] if args else None
    data = json.loads((ROOT / "posts.json").read_text(encoding="utf-8"))
    cfg, posts = data["config"], data["posts"]
    entries = []
    for post in posts:
        if only and post["date"] != only:
            continue
        paths = []
        stamp = post["date"].replace("-", "")
        for i, slide in enumerate(post["slides"], 1):
            name = f"mediskin_{stamp}_{i:02d}.jpg"
            TEMPLATES[slide["t"]](slide).save(REPO / name, "JPEG", quality=90, optimize=True, progressive=True)
            paths.append(name)
            print("✓", name)
        title = post.get("title") or post["slides"][0]["title"].replace("\n", " ")
        e = {"date": post["date"], "slot": "am", "title": title, "posted": False,
             "caption": caption(post, cfg)}
        if len(paths) == 1:
            e.update(media_type="IMAGE", image_path=paths[0])
        else:
            e.update(media_type="CAROUSEL", image_paths=paths)
        entries.append(e)
    update_queue(entries, force)


if __name__ == "__main__":
    main()
