# 네이버 블로그 자동 발행 시스템 - Planner Memory

> 이 파일은 멀티 에이전트 시스템의 **Planner 메모리**입니다.
> Claude Code 세션마다 자동으로 읽혀서, 이전 세션의 학습 결과를 다음 세션에 전달합니다.

---

## 프로젝트 개요

- **목적**: 특허법인 테헤란 변리사 윤웅채의 네이버 블로그 자동 발행
- **블로그**: https://blog.naver.com/jninsa
- **핵심 목표**: 사람이 직접 쓴 것과 구분 불가능한 전문가 블로그 콘텐츠

## 아키텍처

```
Planner (CLAUDE.md + 메인 세션)
├── Content Writer (Sub-agent #1)
│   ├── engine.py: 콘텐츠 생성 엔진
│   ├── se_converter.py: SmartEditor JSON 변환
│   └── image_handler.py: 이미지 생성
└── Automation (Sub-agent #2)
    ├── naver_poster.py: 발행 자동화
    └── naver_uploader_sync.py: CDN 업로드
```

## 파이프라인 흐름

```
키워드 입력
→ generate_hooking_title() : 후킹 제목 3개 생성
→ generate_column_with_validation() : 본문 생성 + 유사도 검증
→ replace_link_markers() : {{LINK:철학글}} → URL 치환
→ generate_blog_images() : 소제목 → 680x200 배너 이미지
→ build_document_data() : SmartEditor JSON 구조 생성
→ post_human_like() : 휴먼 시뮬레이션 발행
```

## 품질 기준

### 필수 체크리스트
- [ ] 소제목은 quotation 컴포넌트 (가운데 정렬, 볼드)
- [ ] 문단 간격 균일 (ZWS 문단 사용)
- [ ] 중요 문장 하이라이트 (노란색 배경 #FFF9C4, 최대 6개)
- [ ] 이미지는 소제목 앞에 배치 (680x200 가로형 배너)
- [ ] 내부 링크는 OG 카드로 표시 (제목 + 설명 + 썸네일)
- [ ] 사람 행동 시뮬레이션 (불규칙 딜레이, 스크롤, 마우스 이동)

### 콘텐츠 품질 규칙
- AI 탐지 방지: 3단 구조 금지, 연결어 최소화, 섹션 길이 불균일
- 사람냄새: 자문자답, 비유, 구체적 숫자, 일화, 감정 표현
- CTA: 비공격적 스타일, 링크 마커 자동 삽입

## 개선 이력

### v4.0 (현재)
- Playwright sync API 전환 (Windows/Streamlit 호환)
- SmartEditor setDocumentData() JSON 삽입 방식
- PIL 카드형 이미지 (DALL-E 대체)
- 유사도 검증 루프 (threshold 0.3)

### v4.1 (이번 업데이트)
- 이미지 비율: 960x540 → 680x200 가로형 배너
- 휴먼 시뮬레이션 포스팅 (post_human_like)
- OG 링크 카드 썸네일/제목/설명 표시 개선
- 멀티 에이전트 오케스트레이터 도입

## 개선 가설 (다음 세션용)

### 가설 1: 문장 길이 다양성
- **현상**: AI 생성 글은 문장 길이가 균일한 경향
- **실험**: 문장 길이 표준편차를 측정하고, 짧은/긴 문장 비율 조정
- **상태**: 미검증

### 가설 2: 어미 패턴 자연화
- **현상**: ~습니다 어미 비율이 높으면 AI 느낌
- **실험**: frequency_rule 조정 (70/20/10 → 60/25/15)
- **상태**: 미검증

### 가설 3: 도입부 패턴 다양화
- **현상**: 매번 비슷한 서두로 시작
- **실험**: opening_patterns 풀 확장 + 랜덤 샘플링 비율 조정
- **상태**: 미검증

## 페르소나 설정 요약

### yun_ung_chae (윤웅채)
- **소속**: 특허법인 테헤란
- **전문**: 상표, 특허, 지식재산권
- **문체**: 전문가이면서 친근한 톤
- **맺음**: "사감합니다" (시그니처)
- **CTA 링크**: 철학글, 추천글, 상담글

## 알려진 제약사항

1. **SmartEditor 제약**: DOM 직접 조작 불가, setDocumentData()만 사용
2. **Playwright fill/type 제약**: contentEditable에 fill() 미작동
3. **이미지 컴포넌트 제약**: 커스텀 이미지 dict 사용 시 필수 필드 누락 → "존재하지 않는 이미지" 오류. 반드시 CDN 업로드 후 네이티브 dict 사용
4. **Naver 보안**: 반복 로그인 시 캡챠/기기등록 발생 가능

## 에이전트 실행 가이드

### Content Writer 에이전트 호출
```python
from src.agent_orchestrator import run_content_agent
result = run_content_agent(topic="상표등록", persona_id="yun_ung_chae")
```

### Automation 에이전트 호출
```python
from src.agent_orchestrator import run_automation_agent
result = run_automation_agent(content_result, mode="human_like")
```

### 전체 파이프라인 (Planner 주도)
```python
from src.agent_orchestrator import run_full_pipeline
result = run_full_pipeline(topic="상표등록", mode="human_like")
```
