#!/usr/bin/env python3
"""numbers.json + candidates.json + approved.json + site/template.html -> site/index.html

표준 라이브러리만 사용. 같은 입력이면 같은 출력(시각·난수 없음).
사용: python device/build_site.py [--data data] [--out device/output] [--site site]
"""
import argparse
import json
import re
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAFT_BADGE = '<span class="badge draft">임시(AI 작성)</span>'
DRAFT_BADGE_SM = '<span class="badge draft sm" title="작성자가 직접 고칠 문장">임시(AI 작성)</span>'
DRAFT_NOTE = '<span class="draft-note">작성자가 직접 고칠 문장</span>'
# 숫자 카드로 먼저 보일 항목(없는 ID 는 건너뜀). 값은 {카드 ID: 같은 카드에 덧붙일 항목 ID}
CORE_CARDS = {"N01": None, "N02": None, "N04": "N05", "N10": None}


def e(value):
    return escape("" if value is None else str(value), quote=True)


def load_json(path, required=True):
    if not path.exists():
        if required:
            sys.exit("입력 파일이 없습니다: %s" % path)
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def warn(msg):
    print("경고: " + msg, file=sys.stderr)


def fmt_value(v):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)


def safe_url(url):
    """http(s) 또는 상대 경로만 허용."""
    url = (url or "").strip()
    if not url:
        return ""
    if re.match(r"^https?://", url, re.I) or not re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I):
        return url
    return ""


def draft_marks():
    """작은 배지(첫 번째 큰 안내는 hero 에서 한 번만)."""
    return DRAFT_BADGE_SM


def draft_banner():
    return ('<p class="draft-banner" role="note">%s <span>노란 배지가 붙은 문장은 AI가 임시로 쓴 것이라 '
            '작성자가 직접 고칠 문장입니다(한 줄 소개와 이야기의 첫·마지막 문장 포함).</span></p>' % DRAFT_BADGE)


# ---------- 섹션 ----------

def split_paragraph(text, per=2):
    """문장 단위로 끊어 2문장씩 묶는다(글자는 바꾸지 않음)."""
    sents = re.findall(r".+?(?:[.!?](?=\s|$)|$)", text.strip(), flags=re.S)
    sents = [x.strip() for x in sents if x.strip()]
    return [" ".join(sents[i:i + per]) for i in range(0, len(sents), per)] or [text]


def render_story(story):
    parts = []
    for p in story.get("paragraphs", []):
        when = p.get("date", "")
        head = p.get("heading", "")
        chips = "".join("<li>%s</li>" % e(a) for a in p.get("abilities", []))
        out = ['<article class="scene">']
        mark = (" " + draft_marks()) if p.get("draft") else ""
        out.append('<p class="when">%s%s</p>' % (e(when), mark))
        out.append("<h3>%s</h3>" % e(head))
        for chunk in split_paragraph(p.get("text", "")):
            out.append("<p>%s</p>" % e(chunk))
        if chips:
            out.append('<ul class="chips" aria-label="드러난 능력">%s</ul>' % chips)
        if p.get("source"):
            out.append('<p class="src">근거: %s</p>' % e(p["source"]))
        out.append("</article>")
        parts.append("\n".join(out))
    return "\n".join(parts)


def story_summary(approved, numbers):
    """이야기 위 한 줄 요약. 숫자와 장면 날짜에서만 만든다(새 사실 없음)."""
    pairing = approved.get("pairing") or {}
    item = next((i for i in numbers.get("items", []) if i.get("id") == pairing.get("number_id")), None)
    m = re.match(r"^\d{4}-(\d{2})-(\d{2})$", pairing.get("scene_date", ""))
    chars = sum(len(p.get("text", "")) for p in approved.get("story", {}).get("paragraphs", []))
    mins = max(1, round(chars / 600))
    line = ""
    if item and m:
        line = ("%d월 %d일에 힘들었던 날의 기록을 남겼고, 그다음 날부터 기록이 %s%s 이어졌습니다. "
                % (int(m.group(1)), int(m.group(2)), e(fmt_value(item.get("value"))), e(item.get("unit", ""))))
    return ('<p class="summary"><strong>먼저 한 줄로</strong> %s고난, 다시 일어난 날, 더 나아진 지금 순서로 읽습니다 '
            '(약 %d자, 읽는 데 %d분 안팎).</p>' % (line, round(chars, -2), mins))


def render_quotes(approved_ids, candidates):
    by_id = {c.get("id"): c for c in candidates}
    items = []
    for cid in approved_ids:
        c = by_id.get(cid)
        if c is None:
            warn("승인된 후보 %s 를 candidates.json 에서 찾지 못해 건너뜀" % cid)
            continue
        meta = "%s · %s · %s" % (c.get("date", ""), c.get("ability", ""), c.get("field", ""))
        block = ['<figure class="quote">', '<p class="meta">%s</p>' % e(meta),
                 "<blockquote>%s</blockquote>" % e(c.get("quote", ""))]
        evs = list(c.get("evidence", []))
        # 기본으로 보일 1개: 이름 가림이 없는 첫 근거(없으면 첫 근거). 나머지는 접는다. 원문은 그대로.
        first = next((i for i, ev in enumerate(evs) if "(이름 가림)" not in ev), 0)
        if evs:
            block.append('<p class="peer"><strong>같은 날 동료 근거:</strong> %s</p>' % e(evs[first]))
            rest = [ev for i, ev in enumerate(evs) if i != first]
            if rest:
                block.append('<details class="more"><summary>같은 날 동료 근거 %d개 더 보기</summary>' % len(rest))
                for ev in rest:
                    block.append('<p class="peer">%s</p>' % e(ev))
                block.append("</details>")
        block.append("</figure>")
        items.append("\n".join(block))
    if not items:
        return ""
    return ('<div class="quotes">\n<h3>근거 인용</h3>\n<p class="lead">기록 원문을 고치지 않고 그대로 옮겼습니다.</p>\n%s\n</div>'
            % "\n".join(items))


def render_pairing(pairing, numbers):
    if not pairing:
        return ""
    item = next((i for i in numbers.get("items", []) if i.get("id") == pairing.get("number_id")), None)
    pair = next((p for p in numbers.get("scene_pairs", [])
                 if p.get("scene_date") == pairing.get("scene_date")), None)
    if item is None:
        warn("pairing.number_id %s 가 numbers.json 에 없어 숫자 없이 장면만 표시" % pairing.get("number_id"))
    out = ['<div class="pair">', '<h3>고난의 날과 짝지은 숫자%s</h3>'
           % ((" " + draft_marks()) if pairing.get("draft") else "")]
    if item:
        out.append('<p class="big">%s<small>%s</small></p>' % (e(fmt_value(item.get("value"))), e(item.get("unit", ""))))
        out.append('<p class="text">%s <span class="src-badge">출처: %s</span></p>'
                   % (e(item.get("text", "")), e(item.get("source", ""))))
    if pair:
        out.append('<div class="scene-q"><p class="meta">%s</p><p>%s</p></div>'
                   % (e(pair.get("scene_date", "")), e(pair.get("scene_quote", ""))))
        if pair.get("next_day_quote"):
            out.append('<div class="scene-q"><p class="meta">%s</p><p>%s</p></div>'
                       % (e(pair.get("next_day_date", "")), e(pair.get("next_day_quote", ""))))
    if pairing.get("caption"):
        out.append('<p class="cap">%s</p>' % e(pairing["caption"]))
    out.append("</div>")
    return "\n".join(out)


def num_card(it, extra, kind_attr=""):
    ability = it.get("ability", "")
    ab = '<span class="ab">관련 능력: %s</span>' % e(ability) if ability and ability != "—" else ""
    body = ['<li class="card">',
            '<p class="v">%s<small>%s</small></p>' % (e(fmt_value(it.get("value"))), e(it.get("unit", ""))),
            '<p class="t">%s</p>' % e(it.get("text", ""))]
    if extra:
        body.append('<p class="t plus">함께 보기: %s</p>' % e(extra.get("text", "")))
    body.append('<p class="srcline"><span class="src-badge">출처: %s</span> %s</p>' % (e(it.get("source", "")), ab))
    calc = [x for x in (it, extra) if x and x.get("detail")]
    if calc:
        body.append('<details class="calc"><summary>계산 보기</summary>%s</details>'
                    % "".join("<p>%s</p>" % e(x["detail"]) for x in calc))
    body.append("</li>")
    return "".join(body)


def render_numbers(numbers, pairing_id=None):
    items = numbers.get("items", [])
    by_id = {i.get("id"): i for i in items}
    shown = set()
    cards = []
    for cid, xid in CORE_CARDS.items():
        it = by_id.get(cid)
        if not it:
            continue
        extra = by_id.get(xid) if xid else None
        shown.add(cid)
        if extra:
            shown.add(xid)
        cards.append(num_card(it, extra))
    if pairing_id:
        shown.add(pairing_id)  # 짝지은 숫자는 위 강조 칸에 이미 나옴
    rows = []
    for it in items:
        if it.get("id") in shown:
            continue
        detail = '<span class="detail">계산: %s</span>' % e(it["detail"]) if it.get("detail") else ""
        ability = it.get("ability", "")
        ability_txt = ' <span class="detail">관련 능력: %s</span>' % e(ability) if ability and ability != "—" else ""
        rows.append(
            "<tr><td class=\"v\">%s %s</td><td>%s%s%s</td><td><span class=\"src-badge\">%s</span></td></tr>"
            % (e(fmt_value(it.get("value"))), e(it.get("unit", "")), e(it.get("text", "")), detail,
               ability_txt, e(it.get("source", ""))))
    out = []
    if cards:
        out.append('<ul class="cards" aria-label="핵심 숫자">%s</ul>' % "\n".join(cards))
    if rows:
        out.append('<details class="more-nums"><summary>나머지 숫자 %d개 보기 (출처와 계산식 포함)</summary>' % len(rows))
        out.append('<table class="nums">')
        out.append("<caption>그 밖의 기록 숫자와 출처</caption>")
        out.append('<thead><tr><th scope="col">숫자</th><th scope="col">내용</th><th scope="col">출처</th></tr></thead>')
        out.append("<tbody>\n%s\n</tbody></table>" % "\n".join(rows))
        weeks = numbers.get("weeks") or {}
        wl = weeks.get("week_list") or []
        if wl:
            out.append('<h4 class="weeks-h">주차별 기록 수 (%s 개강 주부터, 지난 주 %s개 중 기록이 있는 주 %s개)'
                       ' <span class="src-badge">출처: 리추얼 기록</span></h4>'
                       % (e(weeks.get("since", "")), e(weeks.get("weeks_elapsed", "")), e(weeks.get("weeks_with_record", ""))))
            out.append('<ul class="weeks">%s</ul>' % "".join(
                "<li>%s주차(%s) %s건</li>" % (e(w.get("week")), e(w.get("start")), e(w.get("records"))) for w in wl))
        out.append("</details>")
    return "\n".join(out)


def file_exists(site_dir, rel):
    rel = (rel or "").strip()
    if not rel or rel.startswith(("/", "..")) or ":" in rel:
        return False
    return (site_dir / rel).is_file()


def render_showcase(showcase, site_dir):
    out = []
    paper = showcase.get("paper") or {}
    title = paper.get("title") or "10번 논문"
    url = safe_url(paper.get("url"))
    fil = paper.get("file", "")
    if paper.get("status") == "공개 링크" and url:
        out.append('<div class="slot"><h3>%s</h3><p><a href="%s">논문 열기</a> (로그인 없이 열리는 링크)</p></div>'
                   % (e(title), e(url)))
    elif fil and not url:
        if file_exists(site_dir, fil):
            out.append('<div class="slot"><h3>%s</h3><p><a href="%s">논문 문서 파일 열기 (%s)</a></p></div>' % (e(title), e(fil), e(fil.rsplit('.', 1)[-1].upper() if '.' in fil else '파일')))
        else:
            out.append('<div class="slot empty"><h3>%s</h3><p><span class="wait">준비 중</span> 문서 파일이 올라오면 이곳에 링크가 생깁니다.</p></div>' % e(title))
    else:
        out.append('<div class="slot empty"><h3>%s</h3><p><span class="wait">준비 중</span> 이 자리에 논문을 올릴 예정입니다. 링크나 문서 파일이 생기면 바로 열리게 합니다.</p></div>' % e(title))
    app = showcase.get("app") or {}
    if safe_url(app.get("url")):
        out.append('<div class="slot"><h3>%s</h3><p><a href="%s">앱 열기</a></p></div>'
                   % (e(app.get("title") or "13번 앱"), e(safe_url(app["url"]))))
    else:
        out.append('<div class="slot empty"><h3>%s</h3><p><span class="wait">예정</span> %s</p></div>'
                   % (e(app.get("title") or "13번 앱"), e(app.get("eta") or "13번 과제를 마친 뒤 추가")))
    return "\n".join(out)


def render_documents(docs, site_dir):
    items = []
    for d in docs:
        rel = d.get("file", "")
        label = e(d.get("label", ""))
        ext = rel.rsplit(".", 1)[-1].upper() if "." in rel else "파일"
        if file_exists(site_dir, rel):
            items.append('<li class="doc"><a href="%s">%s 열기 (%s 파일)</a></li>' % (e(rel), label, e(ext)))
        else:
            items.append('<li class="doc"><span class="docname">%s</span> <span class="wait">준비 중</span></li>' % label)
    return '<ul class="docs">\n%s\n</ul>' % "\n".join(items)


def render_contact(contact):
    url = safe_url(contact.get("url"))
    label = contact.get("label", "")
    out = ['<div class="contact-card">']
    mark = (" " + draft_marks()) if contact.get("draft") else ""
    if url:
        out.append('<p><a href="%s">%s</a>%s</p>' % (e(url), e(label), mark))
    else:
        out.append("<p>%s%s</p>" % (e(label), mark))
    if contact.get("note"):
        out.append("<p>%s</p>" % e(contact["note"]))
    out.append("</div>")
    return "\n".join(out)


def any_draft(approved):
    if approved.get("draft"):
        return True
    if approved.get("hero", {}).get("tagline_draft"):
        return True
    if approved.get("contact", {}).get("draft"):
        return True
    return any(p.get("draft") for p in approved.get("story", {}).get("paragraphs", []))


def build(args):
    out_dir = Path(args.out)
    site_dir = Path(args.site)
    approved_path = Path(args.approved)
    numbers = load_json(out_dir / "numbers.json")
    candidates_raw = load_json(out_dir / "candidates.json", required=False)
    approved = load_json(approved_path)

    # candidates.json 은 후보 리스트이거나 {능력: [후보…]} 또는 {"candidates": […]} 형태일 수 있다.
    if isinstance(candidates_raw, dict):
        if isinstance(candidates_raw.get("candidates"), list):
            candidates = candidates_raw["candidates"]
        else:
            candidates = [c for v in candidates_raw.values() if isinstance(v, list) for c in v]
    else:
        candidates = candidates_raw or []

    template = (site_dir / "template.html").read_text(encoding="utf-8")
    hero = approved.get("hero", {})
    name = hero.get("name", "")
    tagline = hero.get("tagline", "")
    story = approved.get("story", {})

    footer = "<p>%s의 소개 페이지입니다. 방문자 통계, 댓글, 로그인, 쿠키를 쓰지 않습니다.</p>" % e(name)
    if any_draft(approved):
        footer += "\n    <p>%s 표시가 붙은 문장은 AI가 임시로 쓴 것이라 작성자가 직접 고칠 예정입니다.</p>" % DRAFT_BADGE_SM

    parts = {
        "TITLE": e("%s - 소개" % name),
        "DESCRIPTION": e(tagline),
        "NAME": e(name),
        "TAGLINE": e(tagline),
        "TAGLINE_DRAFT": draft_banner() if any_draft(approved) else "",
        "SUMMARY": story_summary(approved, numbers),
        "STORY_TITLE": e(story.get("title", "이야기")),
        "STORY": render_story(story),
        "QUOTES": render_quotes(approved.get("approved_candidates", []), candidates),
        "PAIRING": render_pairing(approved.get("pairing"), numbers),
        "NUMBERS": render_numbers(numbers, (approved.get("pairing") or {}).get("number_id")),
        "SHOWCASE": render_showcase(approved.get("showcase", {}), site_dir),
        "DOCUMENTS": render_documents(approved.get("documents", []), site_dir),
        "CONTACT": render_contact(approved.get("contact", {})),
        "FOOTER": footer,
    }

    def sub(m):
        key = m.group(1)
        if key not in parts:
            warn("템플릿 자리표시자 %s 에 해당하는 값이 없음" % key)
            return ""
        return parts[key]

    html = re.sub(r"\{\{(\w+)\}\}", sub, template)
    target = site_dir / "index.html"
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print("만듦: %s" % target)


def main():
    ap = argparse.ArgumentParser(description="공개 소개 사이트 index.html 생성")
    ap.add_argument("--data", default=str(ROOT / "data"), help="입력 data 폴더(이 스크립트는 읽지 않음, 규격 호환용)")
    ap.add_argument("--out", default=str(ROOT / "device" / "output"), help="numbers.json, candidates.json 이 있는 폴더")
    ap.add_argument("--site", default=str(ROOT / "site"), help="template.html 이 있고 index.html 을 쓸 폴더")
    ap.add_argument("--approved", default=str(ROOT / "device" / "approved.json"), help="승인 파일")
    build(ap.parse_args())


if __name__ == "__main__":
    main()
