import hashlib
import json
import os
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


def run(out):
    refresh.main(["--data", DATA, "--out", out])
    res = {}
    for n in OUTS:
        with open(os.path.join(out, n), "rb") as f:
            res[n] = f.read()
    return res


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class RefreshTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.o1 = os.path.join(cls.tmp.name, "a")
        cls.o2 = os.path.join(cls.tmp.name, "b")
        cls.r1 = run(cls.o1)
        cls.r2 = run(cls.o2)
        cls.numbers = json.loads(cls.r1["numbers.json"].decode("utf-8"))
        cls.cands = json.loads(cls.r1["candidates.json"].decode("utf-8"))["candidates"]
        cls.items = {i["label"]: i for i in cls.numbers["items"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_a_same_bytes_twice(self):
        for n in OUTS:
            self.assertEqual(self.r1[n], self.r2[n], n)
            self.assertNotIn(b"\r", self.r1[n])
            self.assertTrue(self.r1[n].endswith(b"\n"))

    def test_b_numbers(self):
        it = self.items
        self.assertEqual(it["훈련일 대비 출석률"]["value"], 93.5)
        self.assertEqual(it["훈련일 대비 출석률"]["text"], "훈련일 46일 중 43일 출석 (93.5%, 훈련일에는 오늘 확정 전 1일 포함)")
        self.assertEqual(it["리추얼 기록일"]["value"], 45)
        self.assertEqual(it["아침 기록"]["value"], 45)
        self.assertEqual(it["마무리 기록"]["value"], 43)
        self.assertIn("2026-08-11, 2026-09-21", it["마무리 기록"]["detail"])
        self.assertEqual(it["늦게 쓴 기록일"]["value"], 4)
        self.assertEqual(it["강점 행동 실천"]["value"], 42)
        self.assertEqual(it["강점 행동 일부 실천"]["value"], 1)
        self.assertEqual(it["호흡 기록 최댓값"]["value"], 5)
        self.assertIn("처음 0.01분", it["호흡 기록 최댓값"]["text"])
        self.assertEqual(it["제출 최종 확인 완료"]["value"], 11)
        self.assertEqual(it["기록이 있는 주"]["value"], 11)
        self.assertEqual(it["8/25 이후 이어진 기록일"]["value"], 35)
        self.assertIn("정의", it["8/25 이후 이어진 기록일"]["detail"])
        w = self.numbers["weeks"]
        self.assertEqual((w["since"], w["weeks_elapsed"], w["weeks_with_record"]), ("2026-08-11", 11, 11))
        self.assertEqual(w["week_list"][0]["start"], "2026-08-10")
        self.assertEqual(sum(x["records"] for x in w["week_list"]), 45)
        for i in self.numbers["items"]:
            self.assertIn(i["source"], ("내 출석 기록", "리추얼 기록", "내 제출 현황"))

    def test_b_inputs_hash(self):
        with open(RITUAL, "rb") as f:
            h = hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()  # CRLF/LF 차이는 해시에 영향 없음
        self.assertEqual(self.numbers["inputs"]["ritual-history-2026-10-19.json"], h)

    def test_scene_pair(self):
        sp = self.numbers["scene_pairs"][0]
        ids = {i["id"] for i in self.numbers["items"]}
        self.assertIn(sp["number_id"], ids)
        self.assertEqual((sp["scene_date"], sp["next_day_date"]), ("2026-08-25", "2026-08-26"))
        self.assertIn("코딩이 어려워서", sp["scene_quote"])
        values = self.values_by_date()
        self.assertIn(sp["scene_quote"], " ".join(values["2026-08-25"]))
        self.assertIn(sp["next_day_quote"], values["2026-08-26"])

    def test_c_five_per_ability(self):
        for ab in ("자기조절력", "대인관계력", "자기동기력"):
            n = sum(1 for c in self.cands if c["ability"] == ab)
            self.assertGreaterEqual(n, 5, ab)
            with_ev = [c for c in self.cands if c["ability"] == ab and c["evidence"]]
            self.assertGreaterEqual(len(with_ev), 5, ab + " 근거 있는 후보")

    def values_by_date(self):
        d = load(RITUAL)
        out = {}
        for day in d["days"]:
            out[day["date"]] = [s.partition(": ")[2] for s in day["open"] + day["close"]]
        return out

    def test_d_quotes_verbatim_no_new_text(self):
        values = self.values_by_date()
        for c in self.cands:
            self.assertIn(c["quote"], values[c["date"]], c["id"])
            for e in c["evidence"]:
                self.assertIn(e, values[c["date"]], c["id"])
        ids = [c["id"] for c in self.cands]
        self.assertEqual(len(ids), len(set(ids)))

    def test_d_md_has_no_foreign_names(self):
        # 출력의 모든 한글 인용은 입력 어딘가에 있어야 한다: md 표의 인용 칸을 입력과 대조
        values = {v for vs in self.values_by_date().values() for v in vs}
        md = self.r1["candidates.md"].decode("utf-8")
        shown = 0
        for line in md.splitlines():
            if line.startswith("| C-"):
                cells = [x.strip() for x in line.strip("|").split("|")]
                quote = cells[4]
                self.assertIn(quote.replace("\\", ""), values)
                shown += 1
        self.assertGreaterEqual(shown, 15)


if __name__ == "__main__":
    unittest.main()
