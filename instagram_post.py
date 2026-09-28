#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
퍼스트메디스킨 인스타그램(@firstmediskin_) 자동 게시 — 이미지 + 캐러셀 + 릴스(영상) 지원
==========================================================================
(퍼스트커피랩 자동 게시 시스템과 동일 구조. 캐러셀 게시만 추가)

content_queue.json 에서 오늘 날짜/슬롯의 미게시 항목을 하나 꺼내 게시합니다.
media_type
  "IMAGE"    사진 1장     → image_path
  "CAROUSEL" 사진 2~10장  → image_paths (리스트, 순서대로)
  "REELS"    영상         → image_path (mp4), 선택 cover_path

필요: pip install requests / 같은 폴더 .env 에 IG_ACCESS_TOKEN
사용법:
    python instagram_post.py --slot am
    python instagram_post.py --slot pm
    python instagram_post.py --slot am --dry-run
    python instagram_post.py --check           (토큰만 확인)
"""

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("requests 라이브러리가 필요합니다:  pip install requests")

# 윈도우 한글(cp949) 환경에서 이모지 출력 시 크래시 방지 — 항상 UTF-8로 출력
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GRAPH = "https://graph.instagram.com/v23.0"
BASE = Path(__file__).resolve().parent
QUEUE = BASE / "content_queue.json"
LOG = BASE / "post_log.json"
ENV = BASE / ".env"
DEFAULT_IG_USER_ID = ""  # @firstmediskin_ — GitHub Secret IG_USER_ID 로 지정
KST = dt.timezone(dt.timedelta(hours=9))


def load_env():
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def load_json(p, d):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else d


def save_json(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def log(m):
    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {m}", flush=True)


def upload_public(path, mime):
    """로컬 파일을 임시 공개 호스트에 업로드하고 공개 URL 반환.
    catbox를 여러 번 재시도하고, 실패하면 백업 호스트(0x0.st)로 자동 전환."""
    name = Path(path).name
    errs = []
    # 1차: catbox.moe (최대 3회 재시도)
    for attempt in range(3):
        try:
            with open(path, "rb") as f:
                r = requests.post("https://catbox.moe/user/api.php",
                                  data={"reqtype": "fileupload"},
                                  files={"fileToUpload": (name, f, mime)}, timeout=180)
            url = r.text.strip()
            if r.status_code == 200 and url.startswith("http"):
                return url
            errs.append(f"catbox {r.status_code}")
        except Exception as e:
            errs.append(f"catbox:{e}")
        log(f"  이미지 호스팅 재시도({attempt+1}/3)...")
        time.sleep(5)
    # 2차: 0x0.st 백업
    try:
        with open(path, "rb") as f:
            r = requests.post("https://0x0.st",
                              files={"file": (name, f, mime)},
                              headers={"User-Agent": "firstmediskin-autopost/1.0"},
                              timeout=180)
        url = r.text.strip()
        if r.status_code == 200 and url.startswith("http"):
            return url
        errs.append(f"0x0 {r.status_code}")
    except Exception as e:
        errs.append(f"0x0:{e}")
    raise RuntimeError("이미지 호스팅 실패(모든 호스트): " + "; ".join(errs))


def public_url(rel_path, local_path, mime):
    """미디어의 공개 URL을 반환.
    - GitHub Actions(공개 저장소)에서 실행 시: raw.githubusercontent.com 직접 URL 사용(외부 호스팅 불필요).
    - 그 외(로컬 PC 등): 임시 호스트(catbox/0x0)에 업로드.
    IMAGE_BASE_URL 환경변수로 베이스 URL을 직접 지정할 수도 있음."""
    from urllib.parse import quote
    base = os.environ.get("IMAGE_BASE_URL")
    if not base:
        repo = os.environ.get("GITHUB_REPOSITORY")
        ref = os.environ.get("GITHUB_REF_NAME", "main")
        if repo:
            base = f"https://raw.githubusercontent.com/{repo}/{ref}/"
    if base:
        return base.rstrip("/") + "/" + quote(rel_path)
    return upload_public(local_path, mime)


def pick(queue, today, slot):
    items = queue.get("items", [])
    for it in items:
        if it.get("date") == today and it.get("slot") == slot and not it.get("posted"):
            return it
    # 폴백: 해당 슬롯의 '오늘 이전(과거)' 미게시 항목만 처리 — 미래 날짜 항목을 당겨쓰지 않음.
    # (예약을 한 슬롯당 여러 번 걸어도, 이미 오늘 게시가 끝났으면 다음날 것을 조기 게시하지 않도록)
    pend = [it for it in items
            if it.get("slot") == slot and not it.get("posted")
            and it.get("date", "") <= today]
    pend.sort(key=lambda it: it.get("date", ""))
    return pend[0] if pend else None


def wait_ready(cont, token, timeout_s, interval_s=5):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = requests.get(f"{GRAPH}/{cont}",
                         params={"fields": "status_code", "access_token": token}, timeout=60)
        code = r.json().get("status_code")
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise RuntimeError("미디어 처리 실패(ERROR)")
        log(f"  미디어 준비 중... ({code})")
        time.sleep(interval_s)
    raise RuntimeError("미디어 준비 시간 초과")


def create_container(ig_id, token, data):
    data = dict(data, access_token=token)
    r = requests.post(f"{GRAPH}/{ig_id}/media", data=data, timeout=300)
    j = r.json()
    if "id" not in j:
        raise RuntimeError(f"컨테이너 생성 실패: {j}")
    return j["id"]


def publish_container(ig_id, token, cont):
    last = None
    for _ in range(6):
        r2 = requests.post(f"{GRAPH}/{ig_id}/media_publish",
                           data={"creation_id": cont, "access_token": token}, timeout=120)
        j2 = r2.json()
        if "id" in j2:
            return j2["id"]
        last = j2
        if j2.get("error", {}).get("code") == 9007:
            log("  게시 대기 후 재시도...")
            time.sleep(6)
            continue
        break
    raise RuntimeError(f"게시 실패: {last}")


def publish_carousel(ig_id, token, media_urls, caption):
    """캐러셀: 장마다 자식 컨테이너 → 부모(CAROUSEL) 컨테이너 → 게시."""
    if not 2 <= len(media_urls) <= 10:
        raise RuntimeError(f"캐러셀은 2~10장이어야 합니다 ({len(media_urls)}장)")
    children = []
    for i, u in enumerate(media_urls, 1):
        c = create_container(ig_id, token, {"image_url": u, "is_carousel_item": "true"})
        wait_ready(c, token, 90)
        log(f"  {i}/{len(media_urls)}장 준비 완료: {c}")
        children.append(c)
    cont = create_container(ig_id, token, {"media_type": "CAROUSEL",
                                           "children": ",".join(children), "caption": caption})
    log(f"캐러셀 컨테이너 생성: {cont}")
    wait_ready(cont, token, 120)
    return publish_container(ig_id, token, cont)


def publish(ig_id, token, media_url, caption, media_type, cover_url=None):
    data = {"caption": caption, "access_token": token}
    if media_type == "REELS":
        data["media_type"] = "REELS"
        data["video_url"] = media_url
        if cover_url:
            data["cover_url"] = cover_url
        timeout_s = 300
    else:
        data["image_url"] = media_url
        timeout_s = 90
    r = requests.post(f"{GRAPH}/{ig_id}/media", data=data, timeout=300)
    j = r.json()
    if "id" not in j:
        raise RuntimeError(f"컨테이너 생성 실패: {j}")
    cont = j["id"]
    log(f"컨테이너 생성: {cont}")
    wait_ready(cont, token, timeout_s)
    last = None
    for _ in range(6):
        r2 = requests.post(f"{GRAPH}/{ig_id}/media_publish",
                           data={"creation_id": cont, "access_token": token}, timeout=120)
        j2 = r2.json()
        if "id" in j2:
            return j2["id"]
        last = j2
        if j2.get("error", {}).get("code") == 9007:
            log("  게시 대기 후 재시도...")
            time.sleep(6)
            continue
        break
    raise RuntimeError(f"게시 실패: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", choices=["am", "pm"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true", help="토큰만 확인 (게시 안 함)")
    args = ap.parse_args()

    load_env()
    ig_id = os.environ.get("IG_USER_ID") or DEFAULT_IG_USER_ID
    token = os.environ.get("IG_ACCESS_TOKEN")

    if args.check:
        if not ig_id:
            sys.exit("IG_USER_ID 가 없습니다. .env 또는 Secret 에 넣어주세요.")
        if not token:
            sys.exit("IG_ACCESS_TOKEN 이 없습니다. .env 파일에 토큰을 넣어주세요.")
        r = requests.get(f"{GRAPH}/{ig_id}",
                         params={"fields": "username", "access_token": token}, timeout=60)
        j = r.json()
        if "username" in j:
            log(f"토큰 정상! 연결된 계정: @{j['username']} (id={ig_id})")
        else:
            log(f"토큰 확인 실패: {j}"); sys.exit(1)
        return

    if not args.slot:
        sys.exit("--slot am 또는 --slot pm 이 필요합니다 (또는 --check).")
    if not args.dry_run and not ig_id:
        sys.exit("IG_USER_ID 가 없습니다. GitHub Secret(IG_USER_ID) 또는 .env 에 넣어주세요.")
    if not args.dry_run and not token:
        sys.exit("IG_ACCESS_TOKEN 이 없습니다. .env 파일에 토큰을 넣어주세요.")

    queue = load_json(QUEUE, {"items": []})
    logs = load_json(LOG, {"posts": []})
    today = dt.datetime.now(KST).date().isoformat()  # 서버(UTC)에서도 한국 날짜 기준

    # 1일 1건: 오늘(한국 날짜) 이미 게시 성공 기록이 있으면 추가 게시 안 함.
    # (하루 10회 분산 실행 시 밀린 과거 항목이 같은 날 연달아 올라가는 것 방지)
    if any(p.get("date") == today and p.get("status") == "success" for p in logs.get("posts", [])):
        log(f"오늘({today}) 이미 게시 완료 — 1일 1건 원칙으로 건너뜀."); sys.exit(2)

    item = pick(queue, today, args.slot)
    if not item:
        log(f"게시할 콘텐츠 없음 (date={today}, slot={args.slot})."); sys.exit(2)

    mt = item.get("media_type", "IMAGE").upper()
    paths = item["image_paths"] if mt == "CAROUSEL" else [item["image_path"]]
    for pth in paths:
        if not (BASE / pth).resolve().exists():
            sys.exit(f"파일을 찾을 수 없습니다: {BASE / pth}")
    media = (BASE / paths[0]).resolve()

    log(f"대상: {item.get('date')} {args.slot} · {item.get('title','')} · {mt}")
    log("캡션:\n" + "-"*40 + f"\n{item.get('caption','')}\n" + "-"*40)

    if args.dry_run:
        log("[DRY-RUN] 실제 게시 안 함."); return

    try:
        if mt == "CAROUSEL":
            urls = [public_url(p, str((BASE / p).resolve()), "image/jpeg") for p in paths]
            log(f"공개 URL 확보: {len(urls)}장 (첫 장 {urls[0]})")
            mid = publish_carousel(ig_id, token, urls, item.get("caption", ""))
        else:
            mime = "video/mp4" if mt == "REELS" else "image/jpeg"
            url = public_url(item["image_path"], str(media), mime)
            log(f"공개 URL 확보: {url}")
            cover = None
            if item.get("cover_path"):
                cp = (BASE / item["cover_path"]).resolve()
                if cp.exists():
                    cover = public_url(item["cover_path"], str(cp), "image/jpeg")
            mid = publish(ig_id, token, url, item.get("caption", ""), mt, cover)
        log(f"게시 완료! media_id={mid}")
        item["posted"] = True
        item["posted_at"] = dt.datetime.now().isoformat()
        save_json(QUEUE, queue)
        logs["posts"].append({"date": today, "slot": args.slot, "type": mt,
                              "title": item.get("title"), "media_id": mid, "status": "success"})
        save_json(LOG, logs)
    except Exception as e:
        log(f"실패: {e}")
        logs["posts"].append({"date": today, "slot": args.slot, "type": mt,
                              "title": item.get("title"), "status": "error", "error": str(e)})
        save_json(LOG, logs)
        sys.exit(1)


if __name__ == "__main__":
    main()
