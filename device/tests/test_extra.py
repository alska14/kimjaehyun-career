"""원본 재계산, 민감 후보 제외, 입력 변화, 결정성(폴더·줄바꿈) 시험."""
import copy
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "device"))
import refresh  # noqa: E402

DATA = os.path.join(ROOT, "data")
RITUAL = os.path.join(DATA, "ritual-history-2026-10-19.json")
OUTS = ("numbers.json", "candidates.json", "candidates.md")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_all(out):
    res = {}
    for n in OUTS:
        with open(os.path.join(out, n), "rb") as f:
            res[n] = f.read()
    return res


def make_data(dst, mutate=None, crlf=False):
    """data/ 의 입력 3개를 dst 로 복사한다. mutate 가 있으면 리추얼을 고친 새 파일(10-21)로 바꾼다."""
    os.makedirs(dst, exist_ok=True)
    for n in ("attendance.json", "submissions.json"):
        shutil.copy(os.path.join(DATA, n), os.path.join(dst, n))
    name = "ritual-history-2026-10-19.json"
    if mutate:
        r = load(RITUAL)
        mutate(r)
        name = "ritual-history-2026-10-21.json"
        text = json.dumps(r, ensure_ascii=False, indent=2) + "\n"
    else:
        with open(RITUAL, "rb") as f:
            text = f.read().replace(b"\r\n", b"\n").decode("utf-8")
    with open(os.path.join(dst, name), "w", encoding="utf-8", newline="\r\n" if crlf else "\n") as f:
        f.write(text)
    return dst


class IndependentRecomputeTest(unittest.TestCase):
    """refresh.py 의 코드를 쓰지 않고 원본에서 다시 센 값과 numbers.json 을 대조한다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        refresh.main(["--data", DATA, "--out", cls.tmp.name])
        cls.numbers = load(os.path.join(cls.tmp.name, "numbers.json"))
        cls.items = {i["label"]: i for i in cls.numbers["items"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_recount_from_raw(self):
        days = load(RITUAL)["days"]
        it = self.items
        every = [s.partition(": ") for d in days for s in d["open"] + d["close"]]
        late = {d["date"] for d in days for s in d["open"] + d["close"]
                if s.startswith("표시: ") and "늦은 작성" in s}
        act = [s.partition(": ")[2] for d in days for s in d["close"] if s.startswith("강점 행동: ")]
        br = [float(re.match(r"[\d.]+", v).group(0)) for k, _, v in every if k == "호흡"]
        monday = datetime.date(2026, 8, 10)
        weeks = {(datetime.date.fromisoformat(d["date"]) - monday).days // 7 for d in days}
        self.assertEqual(it["리추얼 기록일"]["value"], len(days))
        self.assertEqual(it["아침 기록"]["value"], sum(1 for d in days if d["open"]))
        self.assertEqual(it["마무리 기록"]["value"], sum(1 for d in days if d["close"]))
        self.assertEqual(it["늦게 쓴 기록일"]["value"], len(late))
        self.assertEqual(it["강점 행동 실천"]["value"], act.count("실천했다"))
        self.assertEqual(it["강점 행동 일부 실천"]["value"], act.count("일부 실천했다"))
        self.assertEqual(it["호흡 기록 최댓값"]["value"], max(br))
        self.assertEqual(it["5분 이상 호흡 기록"]["value"], sum(1 for v in br if v >= 5))
        self.assertEqual(it["기록이 있는 주"]["value"], len(weeks))
        self.assertEqual(it["8/25 이후 이어진 기록일"]["value"],
                         sum(1 for d in days if d["date"] > "2026-08-25"))

    def test_streak_wording_is_honest(self):
        it = self.items["8/25 이후 이어진 기록일"]
        self.assertIn("늦게 쓴 기록 4일", it["text"])
        self.assertIn("결석일 2일", it["text"])
        self.assertIn("공휴일 달력과 대조한 것은 아니다", it["detail"])
        self.assertIn("2026-10-09", it["detail"])   # 기록이 없는 평일을 숨기지 않는다

    def test_all_candidates_verbatim_and_not_sensitive(self):
        rules = load(os.path.join(ROOT, "device", "abilities.json"))
        by = refresh.classify(load(RITUAL), rules)
        values = {s.partition(": ")[2] for d in load(RITUAL)["days"] for s in d["open"] + d["close"]}
        bad = [re.compile(p) for p in rules["exclude_patterns"]]
        for lst in by.values():
            for c in lst:
                self.assertIn(c["quote"], values, c["id"])
                self.assertFalse(any(p.search(c["quote"]) for p in bad), c["id"])
        # 민감한 장면(데이트, 외국인 신체, 담배·냄새)이 있는 날은 장면 전체가 후보에서 빠진다
        dates = {c["date"] for lst in by.values() for c in lst}
        for d in ("2026-08-11", "2026-08-26", "2026-08-27"):
            self.assertNotIn(d, dates)

    def test_each_ability_has_enough_top_candidates(self):
        rules = load(os.path.join(ROOT, "device", "abilities.json"))
        by = refresh.classify(load(RITUAL), rules)
        for ab, lst in by.items():
            self.assertGreaterEqual(len(lst), 8, ab)


class InputChangeTest(unittest.TestCase):
    def run_refresh(self, mutate):
        with tempfile.TemporaryDirectory() as tmp:
            data = make_data(os.path.join(tmp, "data"), mutate)
            out = os.path.join(tmp, "out")
            refresh.main(["--data", data, "--out", out])
            return load(os.path.join(out, "numbers.json")), load(os.path.join(out, "candidates.json"))

    def test_new_day_appended(self):
        def add(r):
            d = copy.deepcopy(r["days"][-1])
            d["date"] = "2026-10-20"
            r["days"].append(d)
        n, _ = self.run_refresh(add)
        it = {i["label"]: i for i in n["items"]}
        self.assertEqual(it["리추얼 기록일"]["value"], 46)
        self.assertEqual(it["마무리 기록"]["value"], 44)
        self.assertEqual(it["8/25 이후 이어진 기록일"]["value"], 36)   # 출석 파일의 훈련일 46 = 기록 46
        self.assertEqual(n["weeks"]["weeks_elapsed"], 11)

    def test_empty_close_tag_only_and_no_breath_day(self):
        def add(r):
            base = r["days"][-1]
            d1 = copy.deepcopy(base)
            d1["date"] = "2026-10-20"
            d1["close"] = []
            d2 = copy.deepcopy(base)
            d2["date"] = "2026-10-21"
            d2["close"] = ["표시: 늦은 작성(빠뜨린 날을 나중에 쓴 기록)"]
            d2["open"] = [x for x in d2["open"] if not x.startswith("호흡")]
            r["days"] += [d1, d2]
        n, _ = self.run_refresh(add)
        it = {i["label"]: i for i in n["items"]}
        self.assertEqual(it["리추얼 기록일"]["value"], 47)
        self.assertEqual(it["마무리 기록"]["value"], 43)       # 빈 마무리·꼬리표만 있는 마무리는 세지 않는다
        self.assertEqual(it["늦게 쓴 기록일"]["value"], 5)
        self.assertEqual(it["호흡 기록 최댓값"]["value"], 5)
        self.assertNotIn("8/25 이후 이어진 기록일", it)         # 출석 파일과 맞지 않으면 만들지 않는다
        self.assertTrue(any("만들지 않았다" in x for x in n["notes"]))

    def test_no_breath_at_all(self):
        def strip(r):
            for d in r["days"]:
                d["open"] = [x for x in d["open"] if not x.startswith("호흡")]
        n, _ = self.run_refresh(strip)
        it = {i["label"]: i for i in n["items"]}
        self.assertEqual(it["호흡 기록 최댓값"]["value"], 0)
        self.assertEqual(it["5분 이상 호흡 기록"]["value"], 0)

    def test_duplicate_date_stops(self):
        def dup(r):
            r["days"].append(copy.deepcopy(r["days"][-1]))
        with self.assertRaises(SystemExit):
            self.run_refresh(dup)


class DeterminismTest(unittest.TestCase):
    def run_in(self, root):
        res = subprocess.run([sys.executable, "-X", "utf8", os.path.join(root, "device", "refresh.py")],
                             cwd=root, capture_output=True)
        self.assertEqual(res.returncode, 0, res.stderr.decode("utf-8", "replace"))
        return read_all(os.path.join(root, "device", "output"))

    def test_copy_with_korean_path_crlf_lf_same_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            roots = []
            for name, crlf in (("새 폴더 A", True), ("새 폴더 B", False)):
                root = os.path.join(tmp, name)
                make_data(os.path.join(root, "data"), crlf=crlf)
                shutil.copytree(os.path.join(ROOT, "device"), os.path.join(root, "device"),
                                ignore=shutil.ignore_patterns("output", "__pycache__", "tests"))
                roots.append(root)
            a1 = self.run_in(roots[0])
            a2 = self.run_in(roots[0])
            b1 = self.run_in(roots[1])
            self.assertEqual(a1, a2)
            self.assertEqual(a1, b1)    # 줄바꿈이 CRLF 든 LF 든, 폴더 이름이 달라도 같다
            orig = os.path.join(tmp, "orig")
            refresh.main(["--data", DATA, "--out", orig])
            self.assertEqual(a1, read_all(orig))   # 원래 폴더의 결과와도 같다
            for n, b in a1.items():
                for leak in (tmp, "새 폴더", "Users", "\\\\"):
                    self.assertNotIn(leak.encode("utf-8"), b, n)


if __name__ == "__main__":
    unittest.main()
