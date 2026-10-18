# Morning Brief (무료 버전)

Claude 없이 매일 자동으로 갱신되는 뉴스·날씨 페이지입니다. 비용은 0원입니다.

- **날씨**: 페이지를 열 때마다 Open-Meteo에서 서울·상하이·LA 날씨를 실시간으로 가져옵니다.
- **뉴스**: 매일 아침 6시(한국 시간)에 GitHub가 CNBC·SCMP·연합뉴스 RSS에서 분야별 최신 기사를 모아 `data/news.json`을 갱신합니다.

## 올리는 방법 (처음 한 번, 약 10분)

1. https://github.com 에 가입하고 로그인합니다.
2. 오른쪽 위 **+ → New repository**. 이름은 `morning-brief`, **Public**으로 두고 **Create repository**.
3. 새 저장소 화면에서 **uploading an existing file** 링크를 누르고, 이 폴더의 `index.html`, `manifest.webmanifest`, `sw.js`, `README.md`와 `scripts`·`data`·`icons` 폴더를 끌어다 놓은 뒤 **Commit changes**.
4. 자동 갱신 설정 파일 만들기: **Add file → Create new file**, 파일 이름 칸에 `.github/workflows/update-news.yml` 을 그대로 입력하고, 이 폴더의 같은 파일 내용을 복사해 붙여 넣은 뒤 **Commit changes**.
   (맥 Finder에서는 점으로 시작하는 `.github` 폴더가 숨겨져 있어 끌어다 놓기가 안 될 수 있어서 이렇게 만듭니다.)
5. **Settings → Pages**에서 Source를 **Deploy from a branch**, Branch를 **main / (root)** 로 두고 **Save**.
   1~2분 뒤 `https://<내 아이디>.github.io/morning-brief/` 주소가 생깁니다. 휴대폰에서는 홈 화면에 추가해 두면 앱처럼 열립니다.
6. 처음 한 번 바로 갱신해 보기: **Actions** 탭 → **Update news** → **Run workflow**.

## 두 가지 판

- **한국어판**: `https://<내 아이디>.github.io/morning-brief/`
- **중국어판**: `https://<내 아이디>.github.io/morning-brief/zh/`

| 구역 | 한국어판 | 중국어판 |
|---|---|---|
| 미국 | CNBC (영어) | CNBC (영어) |
| 중국 | 중국신문사 中新网 (중국어) | 중국신문사 中新网 (중국어) |
| 한국 | 연합뉴스 (한국어) | 연합뉴스 (한국어) |

번역기는 쓰지 않고 모든 기사를 원문 그대로 보여줍니다. 외국어 기사는 "번역해서 보기"를 누르면 구글 번역으로 열립니다.
두 판은 위쪽 버튼(中文版 / 한국어판)으로 오갈 수 있습니다.
`index.html`을 고친 뒤에는 `python3 scripts/make_zh.py`를 실행하면 중국어판 화면에도 그대로 반영됩니다.

## 휴대폰에 앱처럼 설치하기

- **아이폰(Safari)**: 주소를 연 뒤 아래쪽 공유 버튼 → **홈 화면에 추가**.
- **안드로이드(Chrome)**: 주소를 연 뒤 오른쪽 위 ⋮ → **홈 화면에 추가** 또는 **앱 설치**.

홈 화면의 "Brief" 아이콘을 누르면 주소창 없이 전체 화면으로 열립니다. 인터넷이 끊겨도 마지막으로 받은 뉴스와 날씨가 보입니다.
위쪽 **미국 · 중국 · 한국** 버튼을 누르면 그 나라 뉴스로 바로 이동합니다.

## 알아둘 점

- 뉴스 요약은 각 언론사가 RSS에 제공한 기사 첫머리입니다. "가장 중요한 3개"가 아니라 **분야별 최신 기사 3개**(연합뉴스는 `(종합)` 기사를 먼저)를 보여주고, 나머지는 "더 보기"로 펼칩니다.
- 영어 기사는 "한국어로 보기"를 누르면 Google 번역으로 원문이 열립니다.
- GitHub는 저장소에 60일 동안 활동이 없으면 예약 실행을 멈출 수 있습니다. 이 봇이 매일 커밋하므로 보통은 계속 돌아가지만, 멈췄다는 메일이 오면 Actions 탭에서 다시 켜면 됩니다.
- 뉴스 출처를 바꾸려면 `scripts/fetch_news.py` 맨 위 `FEEDS` 목록의 RSS 주소를 바꾸면 됩니다.

## 내 컴퓨터에서 미리 보기

```bash
python3 scripts/fetch_news.py
python3 -m http.server 8000
```
그다음 브라우저에서 http://localhost:8000 을 엽니다.
