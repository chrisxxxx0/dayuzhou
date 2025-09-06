# scripts/mirror_plus.py
import os, urllib.request
from pathlib import Path
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

ORIGIN = os.environ["ORIGIN_FEED_URL"]                 # 源 RSS（从 Secret 里来）
PUBLIC_SITE = os.environ["PUBLIC_SITE"].rstrip("/")    # 你的 Pages 站点
OUT_FILE = os.environ.get("OUTPUT_FILE", "docs/feeds/feed.xml")

# 命名空间
ns = {
    "atom": "http://www.w3.org/2005/Atom",
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "content": "http://purl.org/rss/1.0/modules/content/",
}
ET.register_namespace("atom", ns["atom"])
ET.register_namespace("itunes", ns["itunes"])
ET.register_namespace("content", ns["content"])

UA = {"User-Agent": "GitHubActions-RSSMirror/2.1"}

def fetch(url: str, method="GET"):
    req = urllib.request.Request(url, headers=UA, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read() if method != "HEAD" else r.info()

def head(url: str):
    try:
        return fetch(url, "HEAD")
    except Exception:
        return None

def strip_at_style(u: str) -> str:
    # 去掉形如 ...jpg@middle / @xxx 的样式后缀
    return u.split("@")[0] if u else u

def infer_mime(url: str) -> str:
    u = url.lower()
    if u.endswith(".m4a"): return "audio/mp4"
    if u.endswith(".mp3"): return "audio/mpeg"
    if u.endswith(".aac"): return "audio/aac"
    if u.endswith(".wav"): return "audio/wav"
    # 默认返回空：不强改
    return ""

def ensure_text(parent, tag, text):
    el = parent.find(tag) if ":" not in tag else parent.find(tag, ns)
    if el is None:
        if ":" in tag:
            pfx, local = tag.split(":")
            el = ET.SubElement(parent, f"{{{ns[pfx]}}}{local}")
        else:
            el = ET.SubElement(parent, tag)
    el.text = text
    return el

def main():
    xml_bytes = fetch(ORIGIN)
    root = ET.fromstring(xml_bytes)

    if not root.tag.endswith("rss"):
        raise SystemExit("Only RSS 2.0 is supported")

    channel = root.find("channel")

    # ——频道级：补齐 / 修正——
    # language
    if channel.find("language") is None:
        ET.SubElement(channel, "language").text = "zh-CN"
    # itunes:explicit
    if channel.find("itunes:explicit", ns) is None:
        ET.SubElement(channel, f"{{{ns['itunes']}}}explicit").text = "false"
    # itunes:type
    if channel.find("itunes:type", ns) is None:
        ET.SubElement(channel, f"{{{ns['itunes']}}}type").text = "episodic"
    # itunes:category（若缺少，给一个合理默认：Leisure/Automotive）
    if channel.find("itunes:category", ns) is None:
        c1 = ET.SubElement(channel, f"{{{ns['itunes']}}}category", {"text":"Leisure"})
        ET.SubElement(c1, f"{{{ns['itunes']}}}category", {"text":"Automotive"})

    # lastBuildDate（更新为当前）
    ensure_text(channel, "lastBuildDate",
                datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT"))

    # atom:link rel=self -> 指向 GitHub Pages 的新订阅地址
    self_link = None
    for link in channel.findall("atom:link", ns):
        if link.attrib.get("rel") == "self":
            self_link = link
            break
    if self_link is None:
        self_link = ET.SubElement(channel, f"{{{ns['atom']}}}link",
                                  {"rel":"self","type":"application/rss+xml"})
    self_link.set("href", f"{PUBLIC_SITE}/feeds/{Path(OUT_FILE).name}")

    # 频道图片：只去掉 @middle（不下载、不换域名）
    # <image><url>...
    img = channel.find("image")
    if img is not None:
        url_el = img.find("url")
        if url_el is not None and url_el.text:
            url_el.text = strip_at_style(url_el.text)
    # <itunes:image href="...">
    itimg = channel.find("itunes:image", ns)
    if itimg is not None and itimg.get("href"):
        itimg.set("href", strip_at_style(itimg.get("href")))

    # ——逐集修正——
    for item in channel.findall("item"):
        # enclosure：修正 MIME、尝试写入真实 length
        enc = item.find("enclosure")
        if enc is not None:
            u = enc.get("url","")
            # MIME 类型
            mime = infer_mime(u)
            if mime:
                enc.set("type", mime)
            # length：只有空或为 "0" 时，我们尝试用 HEAD 写入
            if enc.get("length") in (None, "", "0"):
                info = head(u)
                if info and info.get("Content-Length"):
                    enc.set("length", info.get("Content-Length"))

        # itunes:explicit（若缺失，继承频道）
        if item.find("itunes:explicit", ns) is None:
            ch_exp = channel.find("itunes:explicit", ns)
            ET.SubElement(item, f"{{{ns['itunes']}}}explicit").text = (ch_exp.text if ch_exp is not None else "false")

        # itunes:episodeType（推荐）
        if item.find("itunes:episodeType", ns) is None:
            ET.SubElement(item, f"{{{ns['itunes']}}}episodeType").text = "full"

        # 单集图片：只去掉 @middle
        ii = item.find("itunes:image", ns)
        if ii is not None and ii.get("href"):
            ii.set("href", strip_at_style(ii.get("href")))

    # 输出
    Path(OUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root, space="  ")
    Path(OUT_FILE).write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    print(f"Wrote {OUT_FILE}")

if __name__ == "__main__":
    main()
