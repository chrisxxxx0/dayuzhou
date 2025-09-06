# scripts/mirror_plus.py
import os, urllib.request
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

ORIGIN = os.environ["ORIGIN_FEED_URL"]                 
PUBLIC_SITE = os.environ["PUBLIC_SITE"].rstrip("/")    
OUT_DIR = os.environ.get("OUT_DIR", "docs/feeds")      

# 命名空间
ns = {
    "atom": "http://www.w3.org/2005/Atom",
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "content": "http://purl.org/rss/1.0/modules/content/",
}
ET.register_namespace("atom", ns["atom"])
ET.register_namespace("itunes", ns["itunes"])
ET.register_namespace("content", ns["content"])

UA = {"User-Agent": "GitHubActions-RSSMirror/2.2"}

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
    return u.split("@")[0] if u else u

def infer_mime(url: str) -> str:
    u = url.lower()
    if u.endswith(".m4a"): return "audio/mp4"
    if u.endswith(".mp3"): return "audio/mpeg"
    if u.endswith(".aac"): return "audio/aac"
    if u.endswith(".wav"): return "audio/wav"
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

def last_path_segment(url: str) -> str:
    try:
        p = urlparse(url)
        parts = [seg for seg in p.path.split("/") if seg]
        return parts[-1] if parts else "feed"
    except Exception:
        return "feed"

def main():
    xml_bytes = fetch(ORIGIN)
    root = ET.fromstring(xml_bytes)
    if not root.tag.endswith("rss"):
        raise SystemExit("Only RSS 2.0 is supported")

    channel = root.find("channel")

    gen = channel.find("generator")
    if gen is None:
        gen = ET.SubElement(channel, "generator")
    gen.text = "dayuzhou"

    if channel.find("language") is None:
        ET.SubElement(channel, "language").text = "zh-CN"
    if channel.find("itunes:explicit", ns) is None:
        ET.SubElement(channel, f"{{{ns['itunes']}}}explicit").text = "false"
    if channel.find("itunes:type", ns) is None:
        ET.SubElement(channel, f"{{{ns['itunes']}}}type").text = "episodic"
    if channel.find("itunes:category", ns) is None:
        c1 = ET.SubElement(channel, f"{{{ns['itunes']}}}category", {"text":"Leisure"})
        ET.SubElement(c1, f"{{{ns['itunes']}}}category", {"text":"Automotive"})

    ensure_text(channel, "lastBuildDate",
                datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT"))

    img = channel.find("image")
    if img is not None:
        url_el = img.find("url")
        if url_el is not None and url_el.text:
            url_el.text = strip_at_style(url_el.text)
    itimg = channel.find("itunes:image", ns)
    if itimg is not None and itimg.get("href"):
        itimg.set("href", strip_at_style(itimg.get("href")))

    for item in channel.findall("item"):
        enc = item.find("enclosure")
        if enc is not None:
            u = enc.get("url","")
            mime = infer_mime(u)
            if mime:
                enc.set("type", mime)
            if enc.get("length") in (None, "", "0"):
                info = head(u)
                if info and info.get("Content-Length"):
                    enc.set("length", info.get("Content-Length"))
        if item.find("itunes:explicit", ns) is None:
            ch_exp = channel.find("itunes:explicit", ns)
            ET.SubElement(item, f"{{{ns['itunes']}}}explicit").text = (ch_exp.text if ch_exp is not None else "false")
        if item.find("itunes:episodeType", ns) is None:
            ET.SubElement(item, f"{{{ns['itunes']}}}episodeType").text = "full"
        ii = item.find("itunes:image", ns)
        if ii is not None and ii.get("href"):
            ii.set("href", strip_at_style(ii.get("href")))

    ch_link = channel.findtext("link", default="") or ""
    base_name = last_path_segment(ch_link) or "feed"
    out_name = f"{base_name}.xml"
    OUT_PATH = Path(OUT_DIR) / out_name
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    self_link = None
    for link in channel.findall("atom:link", ns):
        if link.attrib.get("rel") == "self":
            self_link = link
            break
    if self_link is None:
        self_link = ET.SubElement(channel, f"{{{ns['atom']}}}link",
                                  {"rel":"self","type":"application/rss+xml"})
    self_link.set("href", f"{PUBLIC_SITE}/feeds/{out_name}")

    ET.indent(root, space="  ")
    OUT_PATH.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    print(f"Wrote {OUT_PATH}")

if __name__ == "__main__":
    main()
