# 계속 새로 쓰는 장치

기록 파일을 넣으면 숫자 칸과 능력별 문단 후보를 다시 만들고, 내가 승인한 것만 사이트에 넣는다.
Python 3.8 이상, 표준 라이브러리만 쓴다. 설치할 것도, 환경 변수도, AI 호출도, 네트워크도 없다.
같은 입력이면 같은 결과(바이트까지)가 나온다.

처음 열어 보는 사람은 폴더 맨 위(`data/`, `device/`, `site/` 가 보이는 곳)에서 아래 3단계를 그대로 따라 하면 된다. 어느 폴더에서 실행해도 같은 기본 경로를 쓴다.

## 3단계

1. **기록 넣기.** `data/` 에 새 파일을 넣는다. 리추얼 기록(`ritual-history-YYYY-MM-DD.json`), `attendance.json`, `submissions.json` 이 필요하다. 리추얼 파일이 여러 개면 파일명 날짜가 가장 늦은 하나를 쓴다. 새 날짜가 들어 있으면 숫자는 저절로 바뀐다.
2. **숫자와 후보 만들기, 고르기.** `python device/refresh.py` 를 돌린다. `numbers: 12, candidates: 자기조절력 28, …` 처럼 한 줄이 나오면 성공이다. `device/output/candidates.md` 를 열어 능력별 표를 읽고, 사이트에 넣고 싶은 후보의 ID(`C-2026-09-22-e4345f` 같은 것)를 `device/approved.json` 의 `approved_candidates` 목록에 적는다. 적지 않은 후보는 사이트에 들어가지 않는다.
3. **사이트 만들기.** `python device/build_site.py` 를 돌린다. `site/index.html` 이 새로 만들어진다. 브라우저로 열어 보면 된다. 숫자와 승인한 인용이 새 기록으로 바뀌어 있다.

`python` 이 안 되면 `py` 나 `python3` 로 바꿔 쓴다. 한글이 깨져 보이면 `python -X utf8 device/refresh.py` 로 돌린다.

## 입력 형식 (data/)

- `ritual-history-YYYY-MM-DD.json`: `{ student, peerNamesMasked, days: [ { date, open: [...], close: [...] } ] }`. 각 문자열은 `"항목: 값"` 형식. `close` 가 비어 있거나 `"표시: …"` 만 있으면 마무리 기록 없음으로 센다. `"표시: 늦은 작성(…)"` 은 늦게 쓴 기록, `"호흡: 5분"` 은 숫자+분, `"강점 행동: 실천했다"` 또는 `"일부 실천했다"`. 같은 날짜가 두 번 있으면 멈추고 알려 준다.
- `attendance.json`: `training_days`, `present`, `absent`, `attendance_rate_percent`, `as_of`, `note`, `recent`.
- `submissions.json`: `tasks: [ { task, submitted, status } ]`, `completed`, `total_free`.
- `projects.json` 은 이 장치에서 쓰지 않는다.
- 줄바꿈이 CRLF(Windows)든 LF든, 파일 앞에 BOM 이 있든 결과가 같다.

## 출력 (device/output/)

- `numbers.json`: 숫자 12개(출석률, 리추얼 기록일, 아침·마무리 기록, 늦게 쓴 기록, 강점 행동, 호흡, 제출, 주차, 8/25 이후 이어진 기록일), 주차 목록, 8/25~8/26 장면 짝, 입력 파일 SHA-256, notes. 숫자마다 `text`(화면에 쓰는 한 줄)와 `detail`(계산식)이 있다.
- `candidates.json`: 능력(자기조절력·대인관계력·자기동기력)별 후보 상위 20개. 원문 그대로의 `quote`, 같은 날 동료가 말해 준 내 장점 `evidence`, `score`, `matched`.
- `candidates.md`: 능력별 상위 8개 표.

## 숫자를 읽을 때 주의할 점

- "8/25 이후 이어진 기록일 35일"은 8/26부터 10/19까지 리추얼이 남은 날의 수다. 그날 제때 썼다는 뜻은 아니다. 이 35일 안에 늦게 쓴 기록이 4일 있고, 그중 2일(10/15, 10/16)은 출석 기록상 결석일이다. 화면 문구(`text`)에 이 사실을 적어 두었다.
- "빠진 훈련일이 없다"는 판단은 출석 파일의 훈련일 수(46, 확정 전 1일 포함)에서 확정 전 1일을 뺀 45가 리추얼 기록일 45와 같고, 주말 기록이 없다는 점으로 한다. 공휴일 달력과 대조한 것은 아니다. 기록이 없는 평일 5일(8/17, 9/24, 9/25, 10/5, 10/9)은 `detail` 에 날짜를 적었다. 두 수가 다르면 이 숫자는 만들지 않고 `notes` 에 이유를 적는다.
- 호흡 "처음 0.01분 → 최댓값 5분": 5분을 넘는 기록은 없고 5분이 14일이다. 상한에 닿은 값이라는 뜻으로 읽어야 한다.
- 주차: 개강 2026-08-11(화)이 속한 월요일 시작 주를 1주차로 센다. 마지막 11주차는 월요일 하루만 지났다.

## 후보 고르기와 사전 고치기

- 능력 분류는 `device/abilities.json` 의 키워드 사전으로 정한다. `strong` 2점, `normal` 1점, `penalty` 는 그 단어가 있으면 그 능력 점수에서 뺀다. 고친 뒤 2단계를 다시 돌린다.
- 제3자의 연애·신체·건강 같은 사생활이 드러나는 장면은 `exclude_patterns` 로 후보에서 뺀다. 한 항목이 걸리면 같은 날 그 장면의 나머지 항목도 뺀다. 원문은 고치지 않는다. 더 빼고 싶은 말이 있으면 그 단어를 `exclude_patterns` 에 한 줄 더하면 된다.
- 후보 `quote` 는 원문과 글자까지 같다(시험으로 확인). 원문의 `(이름 가림)` 은 그대로 둔다.

## 시험

`python -m unittest discover -s device/tests` (16개). 원본에서 따로 다시 센 값과 numbers.json 대조, 후보 인용이 원문과 같은지, 민감한 장면이 빠졌는지, 새 날짜·빈 마무리·꼬리표만 있는 날·호흡 없는 날, 한글 경로와 CRLF/LF 복사본에서 같은 바이트가 나오는지를 본다.

## 검증 기록

2026-10-20, 다른 담당 파일(`build_site.py`, `approved.json`, `site/`)은 고치지 않고 읽기만 했다.

- 원본 재계산: 별도 스크립트로 `data/` 에서 처음부터 다시 세어 `numbers.json` 의 숫자와 대조했다. 출석 43/46(93.5%), 기록일 45, 아침 45, 마무리 43, 늦은 작성 4, 실천 42, 일부 실천 1, 호흡 최댓값 5분, 5분 이상 14일, 제출 11/11, 기록이 있는 주 11, 8/25 이후 35일이 모두 같았다.
- 새 폴더(`새 폴더 확인`, 한글·공백 경로)에 `data/`, `device/`(output 제외), `site/` 를 복사해 3단계를 그대로 두 번 실행했다. 두 번의 결과가 같았고, 원래 폴더의 `device/output` 과도 같았다. 출력에 경로는 들어 있지 않았다.
  - numbers.json `de3b87a665c1812fc47bc4d677fa6dffa1e40b05fb77e6d831cc99281b7a5330`
  - candidates.json `4cb5c58e0f9beaf49b5eda59c470b1eb2ab003d8fd1da21da65ca6622ba56ded`
  - candidates.md `bae3f68761675db8ad08ec750e534d87e5db77e03ffca6331c94a7ff2f6a2ea1`
  - 새 폴더에서 `build_site.py` 를 두 번 돌린 `site/index.html` 은 `1ae83d6829cdae2081054d8b43915f5884c25948632de56346d904d1b7e4f977` 로 같았다(이 해시는 그때의 `approved.json`·`site/` 기준이며 그 파일을 고치면 바뀐다).
- 입력 데이터가 CRLF 인 것을 확인했다. 해시와 읽기에서 줄바꿈 차이를 무시하게 고쳤으므로, Git 설정 때문에 LF 로 바뀐 사본에서도 같은 출력이 나온다(시험으로 확인).
- 새 날짜(마지막 날을 복제해 +1일), 마무리 없는 날, `표시: 늦은 작성` 만 있는 날, 호흡 없는 날을 임시 폴더에서 돌려 오류 없이 숫자가 바뀌었다. 원본 `data/` 는 건드리지 않았다.
- `python -m unittest discover -s device/tests` 16개 통과.
- 확인하지 않은 것: macOS·Linux 에서의 실행.
