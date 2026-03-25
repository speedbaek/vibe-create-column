# 블로그 컬럼 자동생성기 — 설치 및 운영 가이드

> 이 문서는 "변리사 컬럼 자동생성기"를 별도 PC에 설치하고 운영하기 위한 기술 문서입니다.
> 현재 운영 중인 시스템의 구조, 설정, 확장 방법을 포함합니다.

---

## 1. 시스템 개요

### 1.1 목적
변리사/법인 블로그에 SEO 최적화된 칼럼을 자동으로 생성하고 예약 발행하는 시스템

### 1.2 현재 운영 현황
- **3개 블로그** 동시 운영 (네이버 2개 + 티스토리 1개)
- **일 3~8건** 블로그별 자동 발행
- **웹 UI**로 어디서든 예약/관리 가능 (ngrok 터널)
- **PC 부팅 시 자동 시작** (Windows Startup 등록)

### 1.3 핵심 기술 스택
| 구분 | 기술 |
|------|------|
| AI 엔진 | Claude API (Sonnet 4.6 본문 / Haiku 4.5 제목) |
| 이미지 | PIL 배너 생성 + DALL-E 3 (선택) |
| 브라우저 자동화 | Playwright (시스템 Chrome) |
| 웹 UI | Streamlit |
| 키워드 관리 | Google Sheets API |
| 외부 접속 | ngrok (고정 도메인) |
| 언어 | Python 3.11 |

---

## 2. 전체 아키텍처

```
[사용자] ──── 웹 브라우저 ────→ [ngrok 터널]
                                    │
                                    ↓
                            [Streamlit 서버:8502]
                                    │
                ┌───────────────────┼───────────────────┐
                ↓                   ↓                   ↓
        [Tab1: 즉시발행]    [Tab2: 스마트예약]    [Tab3: 칼럼생성]
                │                   │
                ↓                   ↓
        [Subprocess 격리]    [스케줄러 스레드]
                │                   │
                ↓                   ↓
        [job_runner.py] ←──────────┘
                │
    ┌───────────┼───────────┐
    ↓           ↓           ↓
[engine.py] [image_handler] [poster]
 Claude API   PIL/DALL-E    Playwright
    │                         │
    ↓                         ↓
 칼럼 생성              블로그 자동 발행
```

---

## 3. 디렉토리 구조

```
vibe-create-column/
├── app.py                    # 메인 Streamlit 웹 UI
├── .env                      # API키, 블로그 계정 (비공개)
├── requirements.txt          # Python 패키지 목록
├── start_server.bat          # 서버 실행 스크립트
├── start_server.vbs          # 백그라운드 실행 래퍼
│
├── config/
│   ├── blogs.json            # 블로그 등록 정보 (ID, URL, 계정, 플랫폼)
│   ├── personas/             # 페르소나별 설정 (톤앤매너, CTA, 문체DNA)
│   │   ├── yun_ung_chae.json
│   │   ├── teheran_official.json
│   │   ├── kim_sin_yeon.json
│   │   └── ...
│   ├── base_prompt.md        # AI 본문 생성 마스터 프롬프트
│   ├── title_style.md        # 14가지 제목 패턴 가이드
│   ├── human_style_rules.md  # 사람처럼 쓰기 규칙
│   ├── anti_ai_detection.md  # AI탐지 회피 규칙
│   ├── image_styles.json     # 썸네일/본문 이미지 설정
│   ├── categories.json       # 카테고리-키워드 매핑
│   └── google_service_account.json  # 구글시트 인증 (비공개)
│
├── src/
│   ├── engine.py             # AI 콘텐츠 생성 엔진
│   ├── orchestrator.py       # 파이프라인 조율기
│   ├── scheduler.py          # 예약 발행 스케줄러
│   ├── job_runner.py         # subprocess 격리 실행기
│   ├── naver_poster.py       # 네이버 블로그 자동 발행
│   ├── tistory_poster.py     # 티스토리 자동 발행
│   ├── se_converter.py       # 마크다운 → 스마트에디터 JSON
│   ├── html_converter.py     # 마크다운 → HTML (티스토리용)
│   ├── image_handler.py      # 배너 이미지 생성
│   ├── naver_uploader_sync.py # 네이버 CDN 이미지 업로드
│   ├── sheet_manager.py      # 구글시트 키워드 관리
│   ├── scraper.py            # 기존 블로그 글 수집기
│   ├── similarity.py         # 유사도 검사
│   ├── category_mapper.py    # 카테고리 자동 분류
│   └── log_utils.py          # 안전한 로그 출력 유틸리티
│
├── persona_db/               # 페르소나별 학습 데이터 (스크래핑된 기존 글)
├── pw_browser_data*/         # Playwright 브라우저 프로필 (로그인 세션 유지)
├── outputs/                  # 생성된 콘텐츠, 이미지, 스케줄 데이터
└── fonts/                    # 자동 다운로드되는 한글 폰트
```

---

## 4. 핵심 설정 파일 상세

### 4.1 블로그 등록 (`config/blogs.json`)

```json
{
  "blogs": {
    "yun_ung_chae": {
      "display_name": "윤웅채 변리사 블로그",
      "blog_id": "jninsa",
      "blog_url": "https://blog.naver.com/jninsa",
      "env_id_key": "NAVER_ID",        // .env에서 읽을 변수명
      "env_pw_key": "NAVER_PW",
      "default_persona": "yun_ung_chae",
      "personas": ["yun_ung_chae"]
    },
    "tistory_yun": {
      "display_name": "윤변리사 티스토리",
      "platform": "tistory",           // 네이버가 아닌 경우 명시
      "blog_id": "ideas23214",
      "env_id_key": "KAKAO_ID",        // 카카오 계정
      "env_pw_key": "KAKAO_PW",
      "categories": {                   // 티스토리 카테고리 매핑
        "특허 스토리": ["특허", "발명", "명세서"],
        "상표 스토리": ["상표", "브랜드", "네이밍"]
      }
    }
  }
}
```

**새 블로그 추가 시**: 위 형식으로 항목 추가 + `.env`에 계정 정보 추가

### 4.2 페르소나 설정 (`config/personas/*.json`)

페르소나 = 글 작성자의 캐릭터 설정. AI가 이 설정을 참고하여 해당 인물의 문체로 글을 생성합니다.

```json
{
  "name": "윤웅채",
  "intro": "특허법인 테헤란 대표 변리사",
  "personality": "19년 경력의 실무 전문가. 딱딱하지 않고 솔직한 톤.",

  "writing_dna": {
    "opening_patterns": [
      "안녕하세요. {topic}에 대해 이야기해볼까 합니다.",
      "{topic}라는 키워드를 검색하셨을 정도이면..."
    ],
    "closing_patterns": [
      "도움이 되셨길 바랍니다.",
      "추가 궁금한 점은 언제든 문의해 주세요."
    ],
    "sentence_endings": {
      "frequency_rule": "70% 격식체(-습니다) / 20% 구어체(-거든요) / 10% 혼합"
    }
  },

  "strict_rules": [
    "특허법인 '테헤란' 소속임을 반드시 밝힐 것",
    "법률 조언은 일반론으로, 구체적 사건 판단은 피할 것"
  ],

  "cta_config": {
    "links": {
      "consultation": {
        "title": "[상담] 컨설팅 접수 방법",
        "url": "https://blog.naver.com/jninsa/222180460017",
        "marker": "{{LINK:상담글}}"
      }
    },
    "cta_pairs": [
      {
        "role": "consult",
        "text": "변리사 상담이 필요하시다면 아래 글을 참고해 주세요.\n{{LINK:상담글}}"
      }
    ]
  }
}
```

**새 페르소나 추가 절차**:
1. 기존 완성된 JSON(yun_ung_chae.json)을 복사
2. 이름, 소개, 톤앤매너, CTA 링크를 해당 인물에 맞게 수정
3. `config/blogs.json`의 `personas` 배열에 추가
4. 해당 인물의 기존 블로그 글을 스크래퍼로 수집 (퀄리티 향상)

### 4.3 환경변수 (`.env`)

```env
# Claude API
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI (이미지 생성용, 선택사항)
OPENAI_API_KEY=sk-...

# 네이버 블로그 계정
NAVER_ID=블로그1_아이디
NAVER_PW=블로그1_비밀번호
NAVER_ID_TEHERAN=블로그2_아이디
NAVER_PW_TEHERAN=블로그2_비밀번호

# 티스토리 (카카오 계정)
KAKAO_ID=카카오_이메일
KAKAO_PW=카카오_비밀번호

# SSL 우회 (사내 프록시 환경)
DISABLE_SSL_VERIFY=1
```

### 4.4 구글시트 키워드 풀

| 열 | 내용 | 비고 |
|----|------|------|
| A | 키워드 | 검색할 주제 |
| B | PC 검색량 | |
| C | Mobile 검색량 | |
| D | Total 검색량 | 자동 합산 |
| E | 카테고리 | 특허/상표/디자인 등 |
| F | 대상 블로그 | 공통/윤변/공식 |
| G | 발행일 | 발행 완료 시 자동 기록 |
| H | 발행 URL | 발행 완료 시 자동 기록 |

- 시트 ID: `1B-9hmCqvdu3QivCPy12z6nSeydTTqk8xnC5YONMmFSA`
- 인증: `config/google_service_account.json` (서비스 계정)

---

## 5. 콘텐츠 생성 파이프라인

```
키워드 입력
    │
    ▼
[1] 제목 생성 (Claude Haiku — 저비용)
    ├── title_style.md의 14가지 패턴 참고
    ├── 기존 발행 제목 30개 샘플링 (스타일 일관성)
    ├── 최근 10개 제목과 중복 방지
    └── 5개 후보 생성 → 1개 자동 선택
    │
    ▼
[2] 본문 생성 (Claude Sonnet — 고품질)
    ├── Prompt Caching 적용 (시스템 프롬프트 캐싱 → 비용 90% 절감)
    ├── 페르소나 DNA 주입 (문체, 톤, 종결어미 비율)
    ├── persona_db 기존 글 참고 (RAG)
    ├── 유사도 검사 (0.3 이상이면 재생성, 최대 3회)
    └── CTA 마커 자동 삽입 ({{LINK:상담글}} → 실제 URL)
    │
    ▼
[3] 이미지 생성
    ├── 썸네일: PIL 그라데이션 배너 (800×450)
    │   └── 4가지 프리셋: 다크/라이트/웜/블루
    └── 본문 이미지: 소제목별 배너 (680×340)
        └── DALL-E 3 사용 가능 (OpenAI 키 있을 때)
    │
    ▼
[4] 포맷 변환
    ├── 네이버: 마크다운 → SmartEditor ONE JSON
    │   └── 굵은 글씨 → 빨간색, URL → OG링크카드
    └── 티스토리: 마크다운 → 스타일 HTML
    │
    ▼
[5] 자동 발행 (Playwright)
    ├── 로그인 (최초 1회, 이후 세션 유지)
    ├── 이미지 CDN 업로드 (네이버)
    ├── 콘텐츠 삽입 (JS evaluate)
    ├── 카테고리 선택
    └── 발행 버튼 클릭 → URL 수집
    │
    ▼
[6] 후처리
    ├── 발행 히스토리 기록 (outputs/history.json)
    └── 구글시트 발행일+URL 기록
```

---

## 6. 스케줄러 동작 방식

### 6.1 구조
- **JSON 파일 기반** 작업 큐 (`outputs/schedules/jobs.json`)
- **백그라운드 스레드**로 30초마다 체크
- **subprocess 격리**: Playwright의 asyncio와 Streamlit 이벤트 루프 충돌 방지

### 6.2 발행 규칙
| 규칙 | 값 |
|------|-----|
| 발행 가능 시간 | 07:00 ~ 22:00 |
| 같은 블로그 연속 발행 간격 | 60초 |
| 블로그 전환 시 대기 | 30초 |
| 작업당 최대 시간 | 10분 |
| 좀비 작업 자동 정리 | 15분 초과 publishing → failed |
| 중복 발행 방지 | 같은 키워드+블로그 체크 |
| 오늘 예약 시 | 현재 시간 + 10분 이후부터 배정 |

### 6.3 순차 실행 보장
```
윤변블 #1 발행 → 60초 대기
윤변블 #2 발행 → 60초 대기
윤변블 #3 발행 → 30초 대기 (블로그 전환)
공식블 #1 발행 → 60초 대기
공식블 #2 발행 → 완료
```

---

## 7. 웹 UI 기능 (6개 탭)

| 탭 | 기능 |
|----|------|
| **자동 생성 & 발행** | 즉시 발행, 추천 키워드 발행, 예약 관리, 스케줄러 제어 |
| **스마트 예약** | 날짜+블로그+수량 → 키워드 자동선정 → 시간 분배 → 일괄 예약 |
| **단건 칼럼 생성** | 키워드 입력 → 실시간 스트리밍 생성 → 복사/발행 |
| **프롬프트 설정** | 마스터 프롬프트, 문체 규칙, AI탐지 회피 규칙 편집 |
| **블로그 스크래퍼** | 기존 블로그 글 수집 → persona_db 구축 |
| **발행 히스토리** | 최근 발행 이력 조회 (날짜, 키워드, URL) |

---

## 8. 새 PC 설치 절차

### 8.1 사전 준비
| 항목 | 요구사항 |
|------|----------|
| OS | Windows 10/11 |
| Python | 3.11 (3.13과 호환 문제 있음 — 반드시 3.11) |
| Chrome | 시스템에 Google Chrome 설치 필요 |
| RAM | 8GB 이상 (16GB 권장) |
| 네트워크 | 유선 LAN 권장 (안정성) |
| 전원 설정 | **절전 모드 해제** 필수 |

### 8.2 설치 순서

```bash
# 1. 저장소 클론
git clone https://github.com/speedbaek/vibe-create-column.git
cd vibe-create-column

# 2. 패키지 설치
pip install -r requirements.txt
pip install gspread          # requirements.txt에 누락되어 있음

# 3. Playwright 브라우저 드라이버 설치
playwright install

# 4. 환경변수 설정
# .env 파일 복사 (기존 PC에서)

# 5. 비공개 파일 복사 (기존 PC에서)
# - config/google_service_account.json
# - persona_db/ 폴더 전체 (학습 데이터)

# 6. ngrok 설치 및 인증
winget install ngrok
ngrok config add-authtoken <YOUR_TOKEN>

# 7. start_server.bat에서 Python/ngrok 경로 수정
# 새 PC의 실제 설치 경로로 변경

# 8. 서버 실행
start_server.bat

# 9. 자동 시작 등록
# start_server.vbs를 Windows Startup 폴더에 복사:
# C:\Users\{사용자}\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\
```

### 8.3 최초 실행 시 주의사항
1. **첫 네이버 로그인**: Chrome이 열리면서 로그인 진행 → CAPTCHA나 기기등록이 뜰 수 있음 → **수동으로 한 번 완료** 필요
2. 이후에는 `pw_browser_data*/` 에 세션이 저장되어 자동 로그인
3. 한글 폰트(나눔펜, 프리텐다드)는 **첫 이미지 생성 시 자동 다운로드**

---

## 9. 확장 가이드

### 9.1 새 블로그 추가
1. `config/blogs.json`에 블로그 정보 추가
2. `.env`에 로그인 계정 추가
3. `config/personas/`에 페르소나 JSON 생성
4. 스크래퍼로 기존 글 수집
5. 웹 UI에서 선택 → 테스트 발행

### 9.2 새 플랫폼 추가 (예: 워드프레스, 홈페이지)
1. `src/`에 새 poster 파일 생성 (예: `wordpress_poster.py`)
2. Playwright로 로그인 → 에디터 접근 → 콘텐츠 삽입 → 발행 구현
3. `config/blogs.json`에 `"platform": "wordpress"` 추가
4. `src/job_runner.py`의 플랫폼 분기에 새 platform 추가

### 9.3 새 페르소나 추가
1. `config/personas/new_person.json` 생성 (기존 파일 복사 → 수정)
2. 필수 항목: `name`, `intro`, `personality`, `writing_dna`, `cta_config`
3. `config/blogs.json`에서 해당 블로그의 `personas` 배열에 추가
4. 해당 인물의 블로그 글 스크래핑 → `persona_db/new_person/` 구축

### 9.4 자동화 확장 (동일 PC에 추가 가능)
| 자동화 | 추가 방식 |
|--------|----------|
| 홈페이지 컬럼 발행 | 관리자 Playwright 자동화 + poster 추가 |
| 이슈 모니터링 | 크롤링 + Claude API 요약 + 발송 스크립트 |
| CRM 보고서 | CRM 데이터 수집 + Claude API + 메일/웍스 발송 |
| 통장문자 분류 | Google Sheets API + NaverWorks API (별도 프로젝트) |

---

## 10. 비용 구조

### 10.1 API 비용 (종량제)
| 항목 | 모델 | 비용/건 (추정) |
|------|------|--------------|
| 본문 생성 | Sonnet 4.6 (Prompt Caching) | ~$0.05 |
| 제목 생성 | Haiku 4.5 | ~$0.001 |
| 이미지 | DALL-E 3 (선택) | ~$0.04/장 |
| 컨텍스트 | 20,000자 제한 적용 중 | 33% 절감 |

### 10.2 고정 비용
| 항목 | 비용 |
|------|------|
| Claude Code 구독 | $100/월 (Max 5x) — 개발/세팅용 |
| ngrok | 무료 (고정 도메인 1개) |
| Google Sheets API | 무료 |

---

## 11. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| cp949 인코딩 에러 | Windows 한글 환경 stdout | `PYTHONUTF8=1` 환경변수 + `log_utils.safe_log` |
| 발행 성공인데 실패 표시 | subprocess 결과 파싱 실패 | job_runner.py의 UnicodeEncodeError 예외 처리 |
| 중복 발행 | 실패 판정 → 재시도 | retry 로직 제거 + 중복 체크 |
| 로그인 실패 | 세션 만료 또는 CAPTCHA | pw_browser_data 삭제 → 수동 로그인 1회 |
| 스케줄러 미동작 | Streamlit 프로세스 종료 | start_server.bat 재실행 또는 Startup 확인 |
| 제목에 메타텍스트 | LLM 응답 파싱 미비 | 마크다운 헤더 + 메타 패턴 필터링 적용 완료 |

---

## 12. 주요 연락처 및 참고

| 항목 | 정보 |
|------|------|
| GitHub | `https://github.com/speedbaek/vibe-create-column` |
| 웹 관리 URL | `https://harmony-porky-tory.ngrok-free.dev` |
| 로컬 URL | `http://localhost:8502` |
| 구글시트 | 시트 ID: `1B-9hmCqvdu3QivCPy12z6nSeydTTqk8xnC5YONMmFSA` |
