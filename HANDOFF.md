# 블로그 자동화 시스템 - Claude Code 핸드오프

## 프로젝트 개요
특허법인 테헤란 윤웅채 변리사의 네이버 블로그(https://blog.naver.com/jninsa) 자동 포스팅 시스템.
키워드 입력 → 사람냄새 나는 칼럼 자동 생성 → 이미지 생성 → HTML 포맷팅 → 네이버 블로그 발행까지 전체 자동화.

## 현재 상태: ✅ 코드 완성, 로컬 테스트 필요

### 완성된 것
- 콘텐츠 생성 엔진 (Claude API 직접 호출, 유사도 검증 포함)
- 이미지 시스템 (썸네일 + DALL-E/플레이스홀더 본문 이미지)
- HTML 포맷터 (네이버 블로그 Smart Editor 호환, 모바일 최적화)
- 네이버 자동 포스팅 모듈 (Selenium)
- 예약 발행 스케줄러 (APScheduler)
- Streamlit 5탭 UI (app.py)

### 지금 해야 할 것
1. `pip install -r requirements.txt` 실행
2. `python test_naver_post.py --skip-generate` 로 네이버 포스팅 테스트
3. 에러 나면 수정 (Selenium 셀렉터 등 네이버 에디터 변경사항 대응)

---

## 프로젝트 구조

```
vibe-create-column/
├── app.py                    # Streamlit UI (5탭)
├── .env                      # API 키 (커밋 금지)
├── requirements.txt          # 의존성
├── setup.bat                 # 초기 설정 (Windows)
├── run.bat                   # Streamlit 실행
├── quick_test.py             # 전체 파이프라인 빠른 테스트
├── test_naver_post.py        # 네이버 포스팅 테스트 (← 지금 이거 실행해야 함)
├── test_naver_post.bat       # 포스팅 테스트 메뉴
│
├── config/
│   ├── base_prompt.md        # 기본 프롬프트 템플릿
│   ├── human_style_rules.md  # 사람냄새 규칙
│   ├── anti_ai_detection.md  # AI 탐지 방지 규칙
│   ├── image_styles.json     # 이미지 스타일 프리셋 설정
│   ├── personas/
│   │   └── yun_ung_chae.json # 윤웅채 페르소나 (30+ 규칙)
│   └── fonts/                # 나눔고딕 폰트 (Windows는 자동 감지)
│
├── src/
│   ├── engine.py             # 콘텐츠 생성 (Anthropic SDK 직접, LangChain 제거)
│   ├── similarity.py         # TF-IDF 유사도 검증 + 보일러플레이트 필터
│   ├── image_handler.py      # 썸네일 + DALL-E + 플레이스홀더 이미지
│   ├── formatter.py          # 네이버 블로그 HTML 포맷터 (이미지 포함)
│   ├── naver_poster.py       # Selenium 자동 포스팅 (← 테스트 필요)
│   ├── scheduler.py          # APScheduler 예약 발행
│   ├── orchestrator.py       # 파이프라인 통합
│   ├── scraper.py            # 블로그 스크래퍼
│   ├── extractor.py          # 텍스트 추출
│   └── db_builder.py         # 학습 데이터 빌더
│
└── outputs/                  # 생성물 (gitignore)
    ├── images/               # 썸네일, 본문 이미지
    ├── previews/             # HTML 미리보기
    └── history/              # 발행 히스토리
```

---

## .env 파일 (이미 세팅 완료)

```
ANTHROPIC_API_KEY=sk-ant-api03-... (✅ 동작 확인됨)
OPENAI_API_KEY=sk-proj-...        (✅ 세팅됨, DALL-E용)
NAVER_ID=jninsa                   (✅ 세팅됨)
NAVER_PW=sanghagi2                (✅ 세팅됨)
DISABLE_SSL_VERIFY=1              (회사 프록시 대응)
```

---

## 핵심 설계 원칙

### 콘텐츠 생성
- 페르소나 기반: 윤웅채 변리사 19년 경력, 직접 작성한 듯한 문체
- 참고 글 기간: 2020.12.17 ~ 2021.06.30 (윤웅채 직접 작성 기간만)
- AI 냄새 제거: 금지 표현 목록, 구조적 불균형, 자연스러운 불완전성
- 유사도 검증: TF-IDF 코사인 유사도 0.3 미만 통과, 보일러플레이트 필터 적용
- CTA: 비공격적 (전화번호 노출 X, 공지글 링크만)
  - 공지: https://blog.naver.com/jninsa/222180460017
  - 철학: https://blog.naver.com/jninsa/222176762007

### 이미지
- 썸네일: PIL로 그라디언트 배경 + 텍스트 오버레이, 4개 프리셋
- 본문: 3~7장, 작은 사이즈(60%/max 360px), SEO용
- DALL-E 3 사용, 없으면 플레이스홀더 자동 대체
- 사용자 이미지 있으면 AI 이미지와 혼합 배치 (우선순위 포지션 1,3,5)

### 모바일 최적화
- 나눔고딕, 16px, line-height 1.8, word-break: keep-all
- 모바일 사용자 70%+ 대응

---

## 해결했던 주요 이슈

1. **LangChain → Anthropic SDK 직접 호출**: LangChain이 httpx 커스텀 클라이언트를 지원 안 해서 SSL 프록시 우회 불가. 전면 교체.
2. **load_dotenv(override=True)**: 시스템에 빈 환경변수가 이미 있으면 .env 값이 안 먹음. override=True 필수.
3. **유사도 오탐**: "특허법인 테헤란 대표 변리사 윤웅채입니다" 같은 보일러플레이트가 1.0 유사도. EXCLUDE_PATTERNS로 필터.
4. **SSL 인증서 오류**: 회사 프록시 환경에서 `httpx.Client(verify=False)` + `DISABLE_SSL_VERIFY=1` 환경변수로 해결.

---

## 다음 할 일 (우선순위)

### 1순위: 네이버 포스팅 테스트
```bash
pip install -r requirements.txt
python test_naver_post.py --skip-generate
```
- 로그인 성공 확인 (캡차 뜨면 수동 처리)
- 에디터 HTML 삽입 확인
- 네이버 Smart Editor ONE 셀렉터가 안 맞으면 수정 필요

### 2순위: Streamlit UI 실행 확인
```bash
streamlit run app.py
```

### 3순위 (나중에):
- 콘텐츠 품질 튜닝 (프롬프트 개선)
- 예약 발행 실제 테스트
- 배치 처리 안정성 개선
