#!/usr/bin/env python3
"""장치 분석 단계: data/ 의 기록을 읽어 numbers.json, candidates.json, candidates.md 를 만든다.

표준 라이브러리만 사용. 시각·난수·네트워크·AI 호출 없음. 같은 입력이면 바이트까지 같은 출력.
사용: python device/refresh.py [--data data] [--out device/output]
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)   # data/, device/, site/ 가 보이는 폴더. 어느 폴더에서 실행해도 같은 기본 경로를 쓴다.
RITUAL_RE = re.compile(r"^ritual-history-(\d{4}-\d{2}-\d{2})\.json$")
SINCE = datetime.date(2026, 8, 11)          # 개강일(화)
SCENE_DATE = "2026-08-25"                    # 힘든 날(타이레놀)
NEXT_DATE = "2026-08-26"
MASK = "(이름 가림)"
PEER_RE = re.compile(r"^동료 (\d+)가 말해 준 내 장점$")
STREAK_LABEL = "8/25 이후 이어진 기록일"


def read_text(path):
    """UTF-8 (BOM 있어도 됨). CRLF 도 LF 로 읽는다."""
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.replace(b"\r\n", b"\n").decode("utf-8")


def sha256_file(path):
    """BOM·CRLF 차이는 무시하고 해시한다(LF·BOM 없는 파일이면 일반 sha256 과 같다)."""
    return hashlib.sha256(read_text(path).encode("utf-8")).hexdigest()


def load_json(path):
    return json.loads(read_text(path))


def dump_json(obj, path):
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def split_item(s):
    key, sep, val = s.partition(": ")
    return (key, val) if sep else (s, "")


def has_content(items):
    """'표시: …' 같은 꼬리표만 있으면 내용이 없는 것으로 본다."""
    return any(s.strip() and split_item(s)[0] != "표시" for s in items)


WEEKDAY_KO = "월화수목금토일"


def find_ritual(data_dir):
    names = sorted(n for n in os.listdir(data_dir) if RITUAL_RE.match(n))
    if not names:
        sys.exit("data/ 에 ritual-history-YYYY-MM-DD.json 이 없습니다.")
    return names[-1]  # 파일명 날짜가 가장 늦은 것


def monday_of_week1():
    return SINCE - datetime.timedelta(days=SINCE.weekday())


def week_no(day):
    """개강일이 속한 월요일 시작 주를 1주차로."""
    return (day - monday_of_week1()).days // 7 + 1


def fmt(v):
    return "%g" % v


def compute_numbers(ritual, attendance, submissions, inputs):
    days = sorted(ritual["days"], key=lambda x: x["date"])
    if not days:
        sys.exit("리추얼 파일에 days 가 비어 있습니다.")
    for x in days:
        x.setdefault("open", [])
        x.setdefault("close", [])
    notes = []
    dates = [x["date"] for x in days]
    if len(set(dates)) != len(dates):
        sys.exit("리추얼 파일에 같은 날짜가 두 번 들어 있습니다: %s" % ", ".join(
            sorted({d for d in dates if dates.count(d) > 1})))
    last = datetime.date.fromisoformat(dates[-1])
    n_days = len(days)
    n_open = sum(1 for x in days if has_content(x["open"]))
    close_empty = [x["date"] for x in days if not has_content(x["close"])]
    n_close = n_days - len(close_empty)

    late_days = sorted({x["date"] for x in days for s in x["open"] + x["close"]
                        if split_item(s)[0] == "표시" and "늦은 작성" in split_item(s)[1]})

    act = [split_item(s)[1].strip() for x in days for s in x["close"] if split_item(s)[0] == "강점 행동"]
    n_done = sum(1 for v in act if v == "실천했다")
    n_part = sum(1 for v in act if v == "일부 실천했다")

    breath = []
    for x in days:
        for s in x["open"]:
            k, v = split_item(s)
            m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*분", v) if k == "호흡" else None
            if m:
                breath.append((x["date"], float(m.group(1))))
    if breath:
        first_b = breath[0][1]
        max_b = max(v for _, v in breath)
        n_at_max = sum(1 for _, v in breath if v == max_b)
        max_b = int(max_b) if max_b == int(max_b) else max_b
    else:
        first_b, max_b, n_at_max = 0, 0, 0
        notes.append("호흡 기록이 하나도 없어 호흡 숫자를 0으로 두었다.")
    n_ge5 = sum(1 for _, v in breath if v >= 5)

    # 주차
    counts = {}
    for x in days:
        w = week_no(datetime.date.fromisoformat(x["date"]))
        counts[w] = counts.get(w, 0) + 1
    last_w = week_no(last)
    week_list = [{"week": w,
                  "start": (monday_of_week1() + datetime.timedelta(days=7 * (w - 1))).isoformat(),
                  "records": counts.get(w, 0)} for w in range(1, last_w + 1)]
    weeks_with = sum(1 for w in week_list if w["records"] > 0)

    # 출석
    tr, pr, ab = attendance["training_days"], attendance["present"], attendance["absent"]
    rate = round(pr * 100.0 / tr, 1)
    if abs(rate - attendance["attendance_rate_percent"]) > 0.05:
        notes.append("계산한 출석률 %s%% 와 파일의 attendance_rate_percent %s 가 다르다." % (
            fmt(rate), attendance["attendance_rate_percent"]))
    absent_dates = [r["date"] for r in attendance.get("recent", []) if r.get("status") == "결석"]

    # 제출
    tasks = submissions["tasks"]
    n_tasks = len(tasks)
    n_final = sum(1 for t in tasks if t["status"] == "최종 확인 완료")

    items = []

    def add(label, value, unit, text, source, ability, detail):
        items.append({"id": "N%02d" % (len(items) + 1), "label": label, "value": value,
                      "unit": unit, "text": text, "source": source, "ability": ability,
                      "detail": detail})

    add("훈련일 대비 출석률", rate, "%",
        "훈련일 %d일 중 %d일 출석 (%s%%, 훈련일에는 오늘 확정 전 1일 포함)" % (tr, pr, fmt(rate)),
        "내 출석 기록", "과제지속력",
        "출석 %d / 훈련일 %d × 100 = %s%% (결석 %d일: %s)" % (
            pr, tr, fmt(rate), ab, ", ".join(absent_dates) or "날짜 미상"))
    add("리추얼 기록일", n_days, "일",
        "%s ~ %s 사이 리추얼을 쓴 날 %d일" % (dates[0], dates[-1], n_days),
        "리추얼 기록", "과제지속력", "days 배열 길이 = %d" % n_days)
    add("아침 기록", n_open, "일", "아침 기록이 있는 날 %d일" % n_open,
        "리추얼 기록", "과제지속력", "open 이 비어 있지 않은 날 수 = %d" % n_open)
    add("마무리 기록", n_close, "일",
        "마무리 기록이 있는 날 %d일 (마무리가 비어 있는 날 %d일)" % (n_close, len(close_empty)),
        "리추얼 기록", "과제지속력",
        "close 가 비어 있지 않은 날 %d일. 비어 있는 날: %s" % (n_close, ", ".join(close_empty) or "없음"))
    add("늦게 쓴 기록일", len(late_days), "일",
        "빠뜨린 날을 나중에 쓴 기록이 있는 날 %d일" % len(late_days),
        "리추얼 기록", "회복탄력성", "'표시: 늦은 작성' 항목이 있는 날 = %s" % ", ".join(late_days))
    add("강점 행동 실천", n_done, "일", "마무리에서 '실천했다'고 쓴 날 %d일" % n_done,
        "리추얼 기록", "과제지속력", "'강점 행동: 실천했다' 횟수 = %d" % n_done)
    add("강점 행동 일부 실천", n_part, "일", "마무리에서 '일부 실천했다'고 쓴 날 %d일" % n_part,
        "리추얼 기록", "과제지속력", "'강점 행동: 일부 실천했다' 횟수 = %d" % n_part)
    if breath:
        add("호흡 기록 최댓값", max_b, "분",
            "호흡 기록 처음 %s분 → 최댓값 %s분" % (fmt(first_b), fmt(max_b)),
            "리추얼 기록", "회복탄력성",
            "첫 기록 %s분(%s) → 최댓값 %s분. 호흡 기록 %d회 중 최댓값과 같은 기록 %d회" % (
                fmt(first_b), breath[0][0], fmt(max_b), len(breath), n_at_max))
    else:
        add("호흡 기록 최댓값", 0, "분", "호흡 기록 없음", "리추얼 기록", "회복탄력성", "호흡 항목이 있는 날 0일")
    add("5분 이상 호흡 기록", n_ge5, "일", "호흡을 5분 이상 기록한 날 %d일" % n_ge5,
        "리추얼 기록", "회복탄력성", "호흡 값 >= 5분인 날 수 = %d / 호흡 기록 %d일" % (n_ge5, len(breath)))
    add("제출 최종 확인 완료", n_final, "개",
        "제출 %d개 중 %d개가 '최종 확인 완료' (무료 과제 %d개 중 %d개 완료)" % (
            n_tasks, n_final, submissions["total_free"], submissions["completed"]),
        "내 제출 현황", "과제지속력",
        "tasks %d개 중 상태가 '최종 확인 완료'인 것 %d개 (%s ~ %s)" % (
            n_tasks, n_final, tasks[0]["task"], tasks[-1]["task"]))
    add("기록이 있는 주", weeks_with, "주",
        "개강 주부터 %d주(마지막 주는 %s요일까지 지남) 중 기록이 있는 주 %d주" % (
            last_w, WEEKDAY_KO[last.weekday()], weeks_with),
        "리추얼 기록", "과제지속력",
        "개강 %s(화)가 속한 월요일 시작 주를 1주차로, 마지막 기록일 %s까지 %d주. 기록이 있는 주 %d주. 마지막 주는 %s요일까지만 지났다." % (
            SINCE.isoformat(), dates[-1], last_w, weeks_with, WEEKDAY_KO[last.weekday()]))

    # 8/25 이후 이어진 기록일: 빠진 훈련일이 없다고 확인될 때만 만든다
    unconfirmed = 1 if (datetime.date.fromisoformat(attendance["as_of"]) > last
                        and "확정 전 1일" in attendance.get("note", "")) else 0
    confirmed_training = tr - unconfirmed
    after = [x for x in dates if x > SCENE_DATE]
    weekend_records = [x for x in dates if datetime.date.fromisoformat(x).weekday() >= 5]
    span = [SINCE + datetime.timedelta(days=i) for i in range((last - SINCE).days + 1)]
    no_record_weekdays = [d.isoformat() for d in span if d.weekday() < 5 and d.isoformat() not in dates]
    if SCENE_DATE in dates and confirmed_training == n_days and not weekend_records:
        late_after = [x for x in late_days if x > SCENE_DATE]
        absent_late_after = [x for x in late_after if x in absent_dates]
        extra = ""
        if late_after:
            extra = ", 늦게 쓴 기록 %d일 포함" % len(late_after)
            if absent_late_after:
                extra += "(그중 결석일 %d일)" % len(absent_late_after)
        add(STREAK_LABEL, len(after), "일",
            "힘들었던 8/25 다음 날부터 %s까지 빠진 훈련일 없이 기록이 남은 날 %d일%s" % (dates[-1], len(after), extra),
            "리추얼 기록", "회복탄력성",
            "정의: 8/25 다음 날부터 %s까지 리추얼 기록이 있는 날의 수. 그날 제때 썼다는 뜻이 아니라, 빠진 훈련일이 없다는 뜻이다. "
            "빠진 훈련일이 없다는 판단: 출석 파일의 훈련일 %d일에서 확정 전 %d일을 뺀 %d일이 리추얼 기록일 %d일과 같고 주말 기록이 없다(공휴일 달력과 대조한 것은 아니다). "
            "기록이 없는 평일 %d일(%s)은 훈련일에 들어 있지 않은 날이다. "
            "늦게 쓴 기록 %d일 포함(%s)%s. 8/25 를 포함하면 %d일." % (
                dates[-1], tr, unconfirmed, confirmed_training, n_days,
                len(no_record_weekdays), ", ".join(no_record_weekdays) or "없음",
                len(late_after), ", ".join(late_after) or "없음",
                ", 이 중 결석일 %s" % ", ".join(absent_late_after) if absent_late_after else "",
                len(after) + 1))
    else:
        notes.append("'8/25 이후 이어진 기록일'은 만들지 않았다: 출석 파일의 확정 훈련일(%d)과 리추얼 기록일(%d)이 다르거나, 주말 기록(%d일)이 있거나, 8/25 기록이 없어 빠진 훈련일 여부를 확인할 수 없다." % (
            confirmed_training, n_days, len(weekend_records)))
    notes.append("주말·공휴일·휴강일은 기록이 없는 것이 정상이므로 달력 평일을 기준으로 연속을 세지 않았다. 기준은 출석 파일의 훈련일 수와 리추얼 기록일 수가 같은지 여부다.")
    if absent_dates:
        notes.append("결석일(%s)에도 리추얼 기록이 있다. 늦은 작성 표시가 붙은 날: %s. 숫자에는 그대로 포함했다." % (
            ", ".join(absent_dates), ", ".join(x for x in absent_dates if x in late_days) or "없음"))
    if unconfirmed:
        notes.append("출석 파일의 훈련일 %d에는 확정 전인 %s 하루가 들어 있다." % (tr, attendance["as_of"]))
    notes.append("projects.json 은 이 장치에서 쓰지 않는다.")

    # 장면 짝
    by_date = {x["date"]: x for x in days}

    def pick(date, key):
        x = by_date.get(date)
        for s in (x["open"] + x["close"]) if x else []:
            k, v = split_item(s)
            if k == key:
                return v
        return None

    scene_pairs = []
    num_id = next((i["id"] for i in items if i["label"] == STREAK_LABEL), None)
    sq = pick(SCENE_DATE, "감사일기")
    sq = sq.split(" — ")[0].strip() if sq else sq
    nq = pick(NEXT_DATE, "오늘의 첫 행동")
    if sq and nq and num_id:
        scene_pairs.append({"scene_date": SCENE_DATE, "scene_field": "감사일기",
                            "number_id": num_id, "scene_quote": sq,
                            "next_day_date": NEXT_DATE, "next_day_field": "오늘의 첫 행동",
                            "next_day_quote": nq})
    else:
        notes.append("장면 짝을 만들지 못했다(8/25·8/26 원문 또는 짝지을 숫자가 없음).")

    return {
        "inputs": inputs,
        "items": items,
        "notes": notes,
        "scene_pairs": scene_pairs,
        "weeks": {"since": SINCE.isoformat(), "weeks_elapsed": last_w,
                  "weeks_with_record": weeks_with, "week_list": week_list},
    }


def classify(ritual, rules):
    days = sorted(ritual["days"], key=lambda x: x["date"])
    order = rules["field_order"]
    fw = rules["field_weights"]
    exclude = [re.compile(p) for p in rules.get("exclude_patterns", [])]
    soft = [re.compile(p) for p in rules.get("sensitive_penalty_patterns", [])]
    soft_pts = rules.get("sensitive_penalty_points", 4)
    cands = []
    for x in days:
        peers = []
        for s in x["open"]:
            k, v = split_item(s)
            m = PEER_RE.match(k)
            if m and v.replace(MASK, "").strip(" /.,—-"):
                peers.append((int(m.group(1)), v))
        evidence = [v for _, v in sorted(peers)]
        # 같은 날 '일화·노력·결과·남기는 말'은 한 장면이다. 한 항목이 제외 대상이면 그 장면의 나머지 항목도 뺀다.
        scene_tainted = any(
            split_item(s)[0] in fw and fw[split_item(s)[0]] > 0
            and any(p.search(split_item(s)[1].replace(MASK, "")) for p in exclude)
            for s in x["close"] + x["open"])
        for s in x["close"] + x["open"]:
            k, v = split_item(s)
            if k not in fw or not v:
                continue
            text = v.replace(MASK, "")
            if any(p.search(text) for p in exclude) or (scene_tainted and fw[k] > 0):
                continue   # 제3자의 민감한 사생활 등: 후보에서만 뺀다(원문은 그대로)
            best = None
            for ab in order:
                kw = rules["abilities"][ab]
                matched, score = [], fw[k]
                for w in kw["strong"]:
                    if w in text:
                        matched.append(w)
                        score += 2
                for w in kw["normal"]:
                    if w in text:
                        matched.append(w)
                        score += 1
                for w, pts in kw.get("penalty", {}).items():
                    if w in text:
                        score -= pts
                if matched and (best is None or score > best[1]):
                    best = (ab, score, matched)
            if best is not None and any(p.search(text) for p in soft):
                best = (best[0], best[1] - soft_pts, best[2])
            if best is None or best[1] < rules["min_score"]:
                continue
            h = hashlib.sha1((k + "\n" + v).encode("utf-8")).hexdigest()[:6]
            cands.append({"id": "C-%s-%s" % (x["date"], h), "ability": best[0], "date": x["date"],
                          "field": k, "quote": v, "evidence": evidence,
                          "score": best[1], "matched": best[2]})
    seen, uniq = set(), []
    for c in cands:
        if c["id"] not in seen:
            seen.add(c["id"])
            uniq.append(c)
    out = {}
    for ab in order:
        lst = [c for c in uniq if c["ability"] == ab]
        lst.sort(key=lambda c: (-c["score"], c["date"], c["id"]))
        out[ab] = lst
    return out


def md_cell(s):
    return s.replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def render_md(by_ability, rules, numbers):
    n = rules["top_per_ability_in_md"]
    lines = ["# 승인 후보 (자동 분류, 사람이 고른다)", "",
             "- 이 표는 `python device/refresh.py` 가 만든다. 인용 문장은 리추얼 원문 그대로이고 고치지 않았다.",
             "- 사이트에 넣고 싶은 후보의 ID 를 `device/approved.json` 의 `approved_candidates` 에 적는다. 적지 않은 후보는 사이트에 들어가지 않는다.",
             "- 점수 = 항목 가중치 + 키워드 점수(`device/abilities.json`). 근거 = 같은 날 동료가 말해 준 내 장점 원문.",
             "- 제3자의 연애·신체·건강 같은 사생활이 드러나는 장면은 사전의 `exclude_patterns` 로 후보에서 뺐다(원문은 그대로).", ""]
    for ab in rules["field_order"]:
        lst = by_ability[ab]
        lines += ["## %s (후보 %d개 중 상위 %d개)" % (ab, len(lst), min(n, len(lst))), "",
                  "| ID | 날짜 | 항목 | 점수 | 인용 | 근거(같은 날 동료가 말해 준 내 장점) |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for c in lst[:n]:
            ev = " / ".join(md_cell(e) for e in c["evidence"]) or "(그날 동료 말 없음)"
            lines.append("| %s | %s | %s | %d | %s | %s |" % (
                c["id"], c["date"], c["field"], c["score"], md_cell(c["quote"]), ev))
        lines.append("")
    if numbers["scene_pairs"]:
        sp = numbers["scene_pairs"][0]
        item = next(i for i in numbers["items"] if i["id"] == sp["number_id"])
        lines += ["## 장면과 숫자의 짝", "",
                  "- %s: %s" % (sp["scene_date"], sp["scene_quote"]),
                  "- %s: %s" % (sp["next_day_date"], sp["next_day_quote"]),
                  "- 짝지은 숫자 %s: %s (%s)" % (item["id"], item["text"], item["source"]), ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="리추얼·출석·제출 기록에서 숫자와 승인 후보를 만든다.")
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("--out", default=os.path.join(ROOT, "device", "output"))
    ap.add_argument("--abilities", default=os.path.join(HERE, "abilities.json"))
    a = ap.parse_args(argv)

    rit_name = find_ritual(a.data)
    paths = {rit_name: os.path.join(a.data, rit_name),
             "attendance.json": os.path.join(a.data, "attendance.json"),
             "submissions.json": os.path.join(a.data, "submissions.json")}
    inputs = {k: sha256_file(v) for k, v in sorted(paths.items())}
    inputs["abilities.json"] = sha256_file(a.abilities)

    ritual = load_json(paths[rit_name])
    attendance = load_json(paths["attendance.json"])
    submissions = load_json(paths["submissions.json"])
    rules = load_json(a.abilities)

    numbers = compute_numbers(ritual, attendance, submissions, inputs)
    by_ability = classify(ritual, rules)

    os.makedirs(a.out, exist_ok=True)
    dump_json(numbers, os.path.join(a.out, "numbers.json"))
    k = rules["top_per_ability_in_json"]
    dump_json({"inputs": inputs,
               "candidates": [c for ab in rules["field_order"] for c in by_ability[ab][:k]]},
              os.path.join(a.out, "candidates.json"))
    with open(os.path.join(a.out, "candidates.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(render_md(by_ability, rules, numbers))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")   # 콘솔 인코딩이 한글을 못 써도 죽지 않게
    print("numbers: %d, candidates: %s" % (len(numbers["items"]),
          ", ".join("%s %d" % (ab, len(by_ability[ab])) for ab in rules["field_order"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
