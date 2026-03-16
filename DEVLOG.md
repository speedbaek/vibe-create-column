# 개발 로그 - Vibe Create Column

## v5.0 배치 예약 발행 + 포맷팅 복원 (2026-03-16)

### 핵심 변경사항

#### 1. 배치 & 예약 발행 시스템 (`app.py` + `scheduler.py`)
- **이전**: 키워드 리스트 → 순차 즉시 발행만 가능
- **현재**: 키워드별 즉시/예약 선택 + 시간 지정 발행
- 백그라운드 스레드 스케줄러가 예약 시간 도래 시 자동 발행
- 스케줄러 상태 모니터링 UI (시작/중지/상태 확인)
- `scheduler.py` 완전 리팩토링: async 제거 → sync threading 기반

#### 2. 이미지 배치 개선 (`se_converter.py`)
- **문제**: 이미지 4장이 본문 하단에 몰려서 표시
- **원인**: 소제목보다 이미지가 많을 때 남은 이미지를 맨 끝에 append
- **해결**:
  1. 소제목 부족 시 빈 줄 위치에 균등 분배
  2. 소제목 없을 때 전체 라인 균등 분할
  3. 남은 이미지는 끝이 아닌 2/3 지점에 삽입

#### 3. 이미지 텍스트 다양화 (`image_handler.py`)
- **문제**: 소제목 없으면 `[topic]` 반복 → 이미지 4장 모두 같은 키워드
- **해결**: `_extract_key_sentences()` 추가
  - 본문에서 10~50자 핵심 문장 추출
  - 중복 제거 + 균등 간격 선택
  - 키워드 반복 방지

#### 4. 마크다운 형식 규칙 강화 (`base_prompt.md`)
- **문제**: AI가 `## 소제목` 형식을 안 써서 소제목 가운데 정렬 + 인용구 박스 미적용
- **원인**: 프롬프트에 `## ` 형식 사용 지시 없었음
- **해결**: `# 마크다운 형식 규칙 (필수)` 섹션 추가
  - `## ` 필수 사용 + 올바른/틀린 예시 명시
  - 인용구(`"큰따옴표"`), 볼드(`**키워드**`), URL, 리스트 규칙

### 트러블슈팅

#### 소제목 포맷팅 사라짐 (가운데 정렬 + 인용구 박스)
- **증상**: 최근 발행글에서 소제목이 일반 텍스트로만 표시
- **원인**: AI가 `## ` 마크다운 없이 소제목을 생성 → `se_converter.py`가 일반 텍스트로 처리
- **연쇄 영향**: `_extract_subtitles()`도 실패 → 이미지 텍스트에 뜬금없는 문장 삽입
- **해결**: `base_prompt.md`에 마크다운 형식 규칙 명시

---

## v4.0 원클릭 자동 발행 시스템 (2026-03-16)

### 핵심 변경사항

#### 1. 아키텍처 전환: Async → Sync
- **이전**: Playwright async API + asyncio + CDP 연결
- **현재**: Playwright **sync API** + 시스템 Chrome (`channel="chrome"`)
- **이유**: Streamlit의 ThreadPoolExecutor에서 asyncio 이벤트 루프 충돌 (NotImplementedError on Windows)
- **효과**: Windows + Streamlit 환경에서 안정적 동작

#### 2. 원클릭 발행 파이프라인 (`naver_poster.py`)
```
키워드 입력 → 칼럼 생성 → 이미지 생성 → 로그인 → 에디터 이동 → CDN 업로드 → setDocumentData → 발행
```

8단계 자동 실행, `NaverPoster.one_click_post()` 메서드 하나로 통합.

| 단계 | 설명 | 핵심 기술 |
|------|------|-----------|
| 1 | 브라우저 실행 | Playwright persistent context (세션 유지) |
| 2 | 네이버 로그인 | evaluate() + nativeInputValueSetter |
| 3 | 칼럼 생성 | 2-Step AI (리서치 t=0.3 → 작성 t=0.7) |
| 4 | 이미지 다운로드 | PIL 카드형 이미지 → 로컬 파일 |
| 5 | 에디터 이동 | SmartEditor 로드 대기 |
| 6 | CDN 업로드 | 이미지 버튼 → #hidden-file → CDN URL 감지 |
| 7 | 콘텐츠 설정 | setDocumentData() JSON 삽입 |
| 8 | 발행 | 발행 버튼 + URL 변경 감지 |

#### 3. 이미지 시스템 (`image_handler.py`)
- DALL-E 의존성 제거 → **PIL 카드형 이미지** (960x540)
- 3가지 스타일: gradient card, split card, center box
- NanumPen/NanumBrush 폰트 자동 다운로드
- 소제목 추출 → 카드 텍스트로 활용

#### 4. SmartEditor 연동 (`se_converter.py`)
- 마크다운 → SmartEditor JSON 컴포넌트 변환
- 네이티브 이미지 컴포넌트 dict 그대로 사용 (커스텀 생성 X)
- 소제목 앞에 이미지 자동 배치
- 인용구, 하이라이트, oglink 지원

#### 5. CDN 업로드 (`naver_uploader_sync.py`)
- Playwright sync API 전용
- 1장씩 순차 업로드 (다중 파일 한번에 불가)
- getDocumentData()에서 네이티브 컴포넌트 추출
- before/after 이미지 카운트로 새 이미지 감지

#### 6. Streamlit UI (`app.py`)
- Tab1: 원클릭 발행 (키워드 + 버튼 하나)
- `run_in_thread()`: ThreadPoolExecutor로 Playwright sync 실행
- 진행 상황은 콘솔 로그 (Streamlit NoSessionContext 회피)

---

### 트러블슈팅 기록

#### Windows asyncio NotImplementedError
- **원인**: Python 3.11 Windows에서 `SelectorEventLoop`는 subprocess 미지원
- **시도**: `WindowsProactorEventLoopPolicy` 설정 → Playwright 내부 충돌
- **해결**: async 완전 포기 → Playwright sync API 전환

#### Chrome 프로필 선택 화면
- **원인**: 코드가 시스템 Chrome 전체를 kill → 사용자 Chrome도 종료
- **해결**: `channel="chrome"` + `launch_persistent_context` → 별도 프로필(pw_browser_data)

#### Streamlit NoSessionContext
- **원인**: ThreadPoolExecutor 내에서 st.progress() 등 UI 업데이트 불가
- **해결**: progress_callback은 print() 로그만, UI는 st.spinner() 사용

#### 이미지 미첨부 (2가지 원인)
1. `include_images` 기본값 `False` → `True`로 변경
2. `naver_uploader_sync.py` 미존재 → sync 버전 신규 생성

#### 발행 URL 미감지
- **원인**: `PostView`/`logNo` 패턴만 체크, 신형 URL(`blog.naver.com/ID/숫자`) 미대응
- **해결**: regex 패턴 + `postwrite` 아닌 URL 감지 추가

#### JSON 파싱 에러 (yun_ung_chae.json)
- **원인**: 96번째 줄 trailing comma
- **해결**: 불필요한 쉼표 제거

---

### 유의사항 (반드시 지켜야 할 것)

1. **DOM 직접 수정 금지** → SmartEditor React 상태 미반영, 발행 시 빈 콘텐츠
2. **Playwright fill/type 사용 금지** → contentEditable=inherit에서 작동 안 함
3. **이미지 컴포넌트 커스텀 생성 금지** → 필수 필드 누락으로 "존재하지 않는 이미지" 에러
4. **이미지 반드시 1장씩 순차 업로드** → 다중 파일 한번에 전달하면 핸들러 미트리거
5. **오버레이 과도 제거 금지** → SmartEditor 자체 레이어 삭제됨
6. **async/await 사용 금지** (Streamlit 환경) → sync API만 사용
7. **시스템 Chrome kill 금지** → 사용자 브라우저 종료됨

---

### 파일 구조

```
vibe-create-column/
├── app.py                      # Streamlit 메인 (원클릭 발행 UI)
├── src/
│   ├── naver_poster.py         # 발행 엔진 (Playwright sync, 원클릭 파이프라인)
│   ├── naver_uploader_sync.py  # CDN 이미지 업로드 (sync)
│   ├── se_converter.py         # 마크다운 → SmartEditor JSON
│   ├── image_handler.py        # PIL 카드형 이미지 생성
│   ├── orchestrator.py         # 칼럼 생성 오케스트레이터
│   ├── engine.py               # AI 칼럼 생성 엔진
│   └── naver_uploader.py       # CDN 업로드 (async, 레거시)
├── config/
│   ├── base_prompt.md          # 칼럼 작성 프롬프트 (마크다운 형식 규칙 포함)
│   ├── blogs.json              # 멀티 블로그 설정
│   └── personas/
│       └── yun_ung_chae.json   # 변리사 페르소나
├── pw_browser_data/            # Playwright 브라우저 프로필 (git 제외)
├── outputs/
│   └── schedules/              # 예약 발행 작업 큐 (JSON)
└── .env                        # API 키 (git 제외)
```
