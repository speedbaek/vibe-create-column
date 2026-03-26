# 블로그 자동발행 프로그램 - 새 PC 설치 가이드

## 개요

블로그 3개(윤웅채 변리사 블로그, 특허법인 테헤란 공식 블로그, 윤변리사 티스토리)에
예약된 시간에 자동으로 컬럼을 생성하고 발행하는 프로그램입니다.

**동작 구조:**
```
새 PC (24시간 가동)
├── Streamlit 웹서버 (포트 8502) - 예약 관리 + 스케줄러
├── ngrok 터널 - 외부에서 웹 접속 가능
└── 예약 시간 도래 → Claude API로 글 생성 → Playwright로 자동 발행
```

---

## STEP 1. 기본 프로그램 설치

### 1-1. Python 설치
- https://www.python.org/downloads/ 에서 **Python 3.11 이상** 다운로드
- 설치 시 반드시 **"Add Python to PATH"** 체크!
- 설치 확인:
```cmd
python --version
```

### 1-2. Git 설치
- https://git-scm.com/download/win 에서 다운로드 후 기본 설정으로 설치
- 설치 확인:
```cmd
git --version
```

### 1-3. Node.js 설치
- https://nodejs.org/ 에서 LTS 버전 다운로드 후 설치
- 설치 확인:
```cmd
node --version
```

### 1-4. ngrok 설치
- https://ngrok.com/ 에서 계정 가입 후 다운로드
- 또는 명령어로 설치:
```cmd
winget install ngrok
```
- ngrok 인증 (대표님 계정의 authtoken 필요):
```cmd
ngrok config add-authtoken YOUR_AUTH_TOKEN
```

---

## STEP 2. 프로젝트 코드 가져오기

### 2-1. 작업 폴더 생성 및 코드 클론
```cmd
mkdir C:\Users\%USERNAME%\vibe-coding
cd C:\Users\%USERNAME%\vibe-coding
git clone https://github.com/speedbaek/vibe-create-column.git
cd vibe-create-column
```

### 2-2. Python 패키지 설치
```cmd
pip install -r requirements.txt
```

### 2-3. Playwright 브라우저 설치
```cmd
playwright install chromium
```

---

## STEP 3. 환경 설정 파일 복사

### 3-1. `.env` 파일 생성
프로젝트 루트(`vibe-create-column/`)에 `.env` 파일을 만들고 아래 내용 입력:

```env
# Claude API (컬럼 생성용)
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx

# 윤웅채 변리사 블로그 (네이버)
NAVER_ID=jninsa_네이버아이디
NAVER_PW=jninsa_네이버비밀번호

# 특허법인 테헤란 공식 블로그 (네이버)
NAVER_ID_TEHERAN=gempy123_네이버아이디
NAVER_PW_TEHERAN=gempy123_네이버비밀번호

# 윤변리사 티스토리 (카카오 로그인)
KAKAO_ID=카카오아이디
KAKAO_PW=카카오비밀번호

# SSL 검증 비활성화 (사내망 환경용)
DISABLE_SSL_VERIFY=true
```

> ⚠️ `.env` 파일은 절대 Git에 올리지 마세요! (`.gitignore`에 이미 등록됨)

### 3-2. 구글 서비스 계정 파일 복사
기존 PC에서 아래 파일을 복사해서 `config/` 폴더에 넣기:
```
config/google_service_account.json
```
이 파일은 구글시트 연동용입니다. (키워드 관리 시트)

### 3-3. 페르소나 학습 데이터 복사
기존 PC에서 아래 폴더를 통째로 복사:
```
persona_db/          (약 2MB - 블로그 글 학습 데이터)
data/                (약 2.5MB - 스크래핑 데이터)
```
이 데이터가 있어야 AI가 기존 글 스타일을 따라 씁니다.

---

## STEP 4. 블로그 로그인 세션 설정

### ★ 가장 중요한 단계!

Playwright는 브라우저 세션(쿠키)을 저장해서 매번 로그인하지 않아도 되게 합니다.
**최초 1회** 수동으로 로그인해서 세션을 만들어야 합니다.

### 4-1. 네이버 블로그 세션 생성

**윤웅채 변리사 블로그:**
```cmd
cd C:\Users\%USERNAME%\vibe-coding\vibe-create-column
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir='pw_browser_data',
        headless=False,
        viewport={'width': 1280, 'height': 800}
    )
    page = browser.pages[0] if browser.pages else browser.new_page()
    page.goto('https://nid.naver.com/nidlogin.login')
    print('=== 네이버 로그인을 수동으로 완료한 뒤 Enter를 누르세요 ===')
    input()
    browser.close()
    print('세션 저장 완료!')
"
```
→ 브라우저 창이 열리면 **수동으로 네이버 로그인** → 로그인 완료 후 터미널에서 Enter

**테헤란 공식 블로그:**
```cmd
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir='pw_browser_data_teheran_official',
        headless=False,
        viewport={'width': 1280, 'height': 800}
    )
    page = browser.pages[0] if browser.pages else browser.new_page()
    page.goto('https://nid.naver.com/nidlogin.login')
    print('=== 테헤란 공식 계정으로 로그인한 뒤 Enter를 누르세요 ===')
    input()
    browser.close()
    print('세션 저장 완료!')
"
```

### 4-2. 티스토리 세션 생성
```cmd
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir='pw_browser_data_tistory_yun',
        headless=False,
        viewport={'width': 1280, 'height': 800}
    )
    page = browser.pages[0] if browser.pages else browser.new_page()
    page.goto('https://accounts.kakao.com/login')
    print('=== 카카오 로그인 완료 후 Enter를 누르세요 ===')
    input()
    browser.close()
    print('세션 저장 완료!')
"
```

> 💡 세션은 보통 몇 주~몇 달 유지됩니다. 로그인 풀리면 위 과정 다시 하면 됩니다.

---

## STEP 5. 서버 실행 확인

### 5-1. 수동으로 먼저 테스트
```cmd
cd C:\Users\%USERNAME%\vibe-coding\vibe-create-column
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python -m streamlit run app.py --server.port 8502 --server.headless true
```
→ 브라우저에서 http://localhost:8502 접속 확인

### 5-2. 즉시발행 테스트
- 웹 UI에서 블로그 1개 선택
- 키워드 1개 입력 (예: "상표등록비용")
- "즉시 발행" 클릭
- 성공 확인 → 실제 블로그에 글이 올라갔는지 확인

### 5-3. 스마트 예약 테스트
- "스마트 예약" 탭 선택
- 내일 날짜 + 블로그 1개 + 포스팅 1건
- "키워드 미리보기" → "예약 등록"
- 예약 대기 현황에 정상 등록되는지 확인

---

## STEP 6. 자동 시작 설정 (PC 부팅 시)

### 6-1. 시작 스크립트 수정
`start_server.bat` 파일의 Python/ngrok 경로를 **새 PC의 경로**로 수정:

```bat
@echo off

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHON=C:\Users\새PC사용자명\AppData\Local\Programs\Python\Python311\python.exe
set NGROK=ngrok경로

cd /d "C:\Users\새PC사용자명\vibe-coding\vibe-create-column"

start /min "Streamlit" "%PYTHON%" -m streamlit run app.py --server.port 8502 --server.headless true

ping 127.0.0.1 -n 11 >nul

start /min "Ngrok" "%NGROK%" http 8502 --domain=harmony-porky-tory.ngrok-free.dev
```

> ⚠️ Python 경로 확인 방법: `where python` 명령어 실행

### 6-2. 시작프로그램 등록

**방법 A: 시작 폴더에 바로가기 넣기**
1. `Win + R` → `shell:startup` 입력 → Enter
2. 열린 폴더에 `start_server.bat`의 바로가기 생성

**방법 B: VBS로 숨김 실행 (창 없이)**
`start_server.vbs` 파일 생성:
```vbs
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """C:\Users\새PC사용자명\vibe-coding\vibe-create-column\start_server.bat""", 0, False
```
이 `.vbs` 파일을 시작 폴더에 복사

---

## STEP 7. PC 설정

### 7-1. 절전 모드 비활성화 (필수!)
1. `설정` → `시스템` → `전원 및 배터리`
2. `화면 끄기`: 원하는 시간 (30분 등)
3. **`절전 모드`: "안 함"** ← 반드시!

### 7-2. Windows 자동 업데이트 주의
- 자동 재시작으로 서버가 꺼질 수 있음
- `설정` → `Windows 업데이트` → `활성 시간` 설정
  - 활성 시간: 07:00 ~ 23:00 (이 시간엔 재시작 안 함)

### 7-3. 방화벽 설정
- Streamlit(포트 8502)은 로컬에서만 접속
- ngrok이 터널링하므로 별도 방화벽 설정 불필요

---

## 폴더 구조 요약

```
vibe-create-column/
├── app.py                          # Streamlit 메인 앱
├── .env                            # ⚠️ 직접 생성 필요 (API키, 계정정보)
├── start_server.bat                # 서버 시작 스크립트
├── start_server.vbs                # 숨김 실행용
├── requirements.txt                # Python 패키지 목록
│
├── config/
│   ├── blogs.json                  # 블로그 3개 설정
│   ├── personas/                   # 페르소나 설정 (6명)
│   ├── google_service_account.json # ⚠️ 직접 복사 필요
│   ├── base_prompt.md              # 기본 프롬프트
│   ├── title_style.md              # 제목 스타일 가이드
│   └── image_styles.json           # 이미지 스타일 설정
│
├── src/
│   ├── engine.py                   # 컬럼 생성 엔진 (Claude API)
│   ├── naver_poster.py             # 네이버 블로그 발행
│   ├── tistory_poster.py           # 티스토리 발행
│   ├── scheduler.py                # 예약 발행 스케줄러
│   ├── job_runner.py               # subprocess 작업 실행기
│   └── sheet_manager.py            # 구글시트 연동
│
├── persona_db/                     # ⚠️ 직접 복사 필요 (학습 데이터)
├── data/                           # ⚠️ 직접 복사 필요 (스크래핑 데이터)
│
├── pw_browser_data/                # ⚠️ 로그인 세션 (STEP 4에서 생성)
├── pw_browser_data_teheran_official/
└── pw_browser_data_tistory_yun/
```

---

## 체크리스트

| # | 항목 | 확인 |
|---|------|------|
| 1 | Python 3.11+ 설치 | □ |
| 2 | Git 설치 | □ |
| 3 | Node.js 설치 | □ |
| 4 | ngrok 설치 + 인증 | □ |
| 5 | 코드 클론 (`git clone`) | □ |
| 6 | `pip install -r requirements.txt` | □ |
| 7 | `playwright install chromium` | □ |
| 8 | `.env` 파일 생성 (API키 + 계정) | □ |
| 9 | `google_service_account.json` 복사 | □ |
| 10 | `persona_db/` 폴더 복사 | □ |
| 11 | `data/` 폴더 복사 | □ |
| 12 | 네이버 로그인 세션 생성 (윤변블) | □ |
| 13 | 네이버 로그인 세션 생성 (공식블) | □ |
| 14 | 카카오 로그인 세션 생성 (티스토리) | □ |
| 15 | Streamlit 수동 실행 테스트 | □ |
| 16 | 즉시발행 테스트 (1건) | □ |
| 17 | `start_server.bat` 경로 수정 | □ |
| 18 | 시작프로그램 등록 | □ |
| 19 | 절전 모드 "안 함" 설정 | □ |
| 20 | PC 재부팅 후 자동실행 확인 | □ |

---

## 문제 해결 (FAQ)

### Q. "cp949 codec can't encode" 에러
→ `start_server.bat`에 `set PYTHONUTF8=1` 이 있는지 확인

### Q. 네이버 로그인이 풀렸을 때
→ STEP 4의 로그인 세션 생성 다시 실행

### Q. 예약 발행이 안 될 때
→ Streamlit이 실행 중인지 확인: 브라우저에서 http://localhost:8502 접속

### Q. ngrok 접속이 안 될 때
→ ngrok 프로세스 확인: 작업 관리자에서 ngrok.exe 실행 중인지 확인
→ 도메인 충돌: 기존 PC의 ngrok을 먼저 종료해야 함 (1개 도메인 = 1개 터널만 가능)

### Q. 같은 키워드로 중복 발행됨
→ 최신 코드에 중복 방지 로직 포함됨. `git pull`로 최신 코드 받기

### Q. PC 재시작 후 서버가 안 올라옴
→ `start_server.bat`을 수동 실행해서 에러 확인
→ Python/ngrok 경로가 맞는지 확인 (`where python`, `where ngrok`)
