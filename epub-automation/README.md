# InDesign → EPUB 자동화 파이프라인

스펄전 시리즈(도서출판 나무와열매) 이펍 제작 자동화 스크립트 모음. InDesign COM 자동화로
고정형(fixed-layout)과 리플로우형(reflowable) EPUB을 모두 생성한다.

## 핵심 발견 (2026-09-30 ~ 10-01 세션)

- InDesign COM에서 EPUB 내보내기는 `doc.Export(FORMAT_CONST, path, False)`로 가능하다.
  - `FIXED_LAYOUT_EPUB = 1701865080`
  - `EPUB(리플로우형) = 1701868898`
- 리플로우형 세부 설정은 **문서 레벨** `doc.EpubExportPreferences` COM 객체로 제어한다
  (앱 레벨이 아님 — `app.EPubExportPreferences` 등은 존재하지 않는다):
  - `.BreakDocument = True` : 장(章) 단위로 파일 분할
  - `.ParagraphStyleName = "장 제목"` : 분할 기준 단락 스타일
  - `.TocStyleName` : **반드시 "[기본값]"이 아닌 고유 이름으로 바꿔야** 목차/책갈피가
    정상 생성된다. 기본값 그대로면 InDesign이 빈 내비게이션을 만드는 알려진 버그가 있다.
  - `.ExportOrder` : 읽기 순서(레이아웃 기준 등)
  - `.EpubCreatePageNavigation = False` : 페이지 목록 방식 대신 TOC 스타일 방식 사용
  - TOC 스타일 엔트리의 페이지번호는 `doc.TOCStyles.Item(1).TOCStyleEntries.Item(1)
    .PageNumberPosition = int.from_bytes(b'none','big')`로 제거(리플로우용 권장사항).
- **InDesign은 스레드로 연결되지 않은 독립 스토리(표지/판권/영문표지/저자소개 등)를
  본문 뒤에 순서 없이 던져버린다.** 후처리에서 반드시 내용 기반으로 위치를 재배치해야 한다.
- **[2026-10-01 중요 발견] `BreakDocument`의 `ParagraphStyleName` 매칭은 문서 최상위
  (그룹 밖) 단락 스타일만 인식하고, `ParagraphStyleGroup` 안에 중첩된 동일 이름의 스타일은
  무시한다.** 다른 프로젝트에서 스타일이 통째로 복사돼 들어온 문서(예: 스타일 그룹
  "마틴 루터의 갈라디아서 강의와 복음 V" 안에 같은 이름 "장 제목"이 중복 존재)에서, 실제
  장(章) 제목 문단들이 그룹 안의 스타일을 쓰고 있으면 `BreakDocument=True`를 줘도 전혀
  분할이 안 된다(전체가 파일 1개로 나옴). **진단 순서**: (1) `doc.ParagraphStyleGroups`를
  순회해 동일 이름의 중복 스타일이 있는지 확인 (2) `doc.Stories.Item(1).Paragraphs`를
  **인덱스 접근**(`.Item(i)`, `for i in range(1,n+1)`)으로 순회해 실제 장 제목 텍스트가
  어느 스타일 객체(`.AppliedParagraphStyle`)를 쓰는지 확인 — **Python `for p in
  collection:` 형태의 이터레이터는 대형 COM 컬렉션에서 항목을 누락시키는 버그가 있으므로
  반드시 인덱스 접근으로 재확인할 것** (3) 실제 장 제목이 최상위 스타일을 안 쓰고 있으면,
  `doc.ParagraphStyles.Item('장 제목')`(최상위) 객체를 가져와 각 장 제목 문단에
  `p.AppliedParagraphStyle = top_style`로 재적용한 뒤 export — 이렇게 하면 즉시 정상
  분할된다. (실제 사례: "스펄전의 아가서의 복음이야기 1" — 10장 전부 정상 복구.)
- 문단 클래스에 스타일을 줘도 InDesign이 실제 텍스트를 `<span class="CharOverride-N">`
  으로 감싸서 그 span이 폰트를 재정의한다 → 반드시 `.클래스, .클래스 span { ... !important }`
  형태로 강제해야 실제 적용된다.
- epubcheck(공식 검증기) 필수 체크리스트:
  1. OPF에 `<meta property="dcterms:modified">타임스탬프</meta>` 필수
  2. `<spine toc="ncx">` 속성 필수(NCX 포함 시)
  3. 모든 xhtml DOCTYPE을 `<!DOCTYPE html>`(HTML5)로 통일 — InDesign 원본은 XHTML1.1 DOCTYPE
  4. CSS 파일을 OPF manifest에 `<item>`으로 반드시 등록(빠지면 일부 리더가 CSS 전체 무시)
  5. `META-INF/container.xml`을 반드시 복사할 것(빠뜨리기 쉬운 치명적 버그)
  6. 표지 itemref에 `linear="no"`를 달지 말 것(관련 매니페스트 링크 오류 유발)
- Java 없는 환경에서 epubcheck 실행: `pip install epubcheck`로 jar만 설치되고 시스템에
  JRE가 있어야 동작한다. StackOverflowError 방지를 위해 `-Xss8m` 옵션 필수:
  ```
  java -Xss8m -jar <epubcheck.jar경로> <epub경로>
  ```
- InDesign 크래시 대응: `app.ActiveWindow`/`ActivePage`를 직접 조작하지 말 것(크래시 유발
  확인됨). 순수 문서 모델 호출(Open/Export/Close, 속성 설정)은 안전하다. 크래시 복구
  대화상자가 뜨면 재실행 후 "취소" 클릭으로 넘긴다.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `resolve_indd_paths.py` | 책 제목 → 원본 .indd 파일 경로 탐색 |
| `batch_indesign_to_epub.py` | 고정형 EPUB 배치 변환(검증됨, 145권 전량 성공) |
| `fix_indesign_epub.py` | 공통 후처리: 파일명 정규화, IDPF 폰트 복호화(encryption.xml 제거), dc:title/language 통일, 표지 이미지 교체 |
| `build_reflow_final.py` | 리플로우 EPUB 빌드(1권 전용, 구조가 하드코딩됨 — 참고용 예제) |
| `build_reflow_generic.py` | **리플로우 EPUB 빌드 일반화 버전** — 콘텐츠 마커 기반으로 앞부속/목차/장 구조를 자동 탐지(9/10권 검증 완료) |
| `batch10_export.py` | InDesign COM으로 여러 책을 순회하며 리플로우 raw export |
| `batch10_postprocess.py` | raw export에 `build_reflow_generic.py` 적용 + epubcheck 검증 배치 실행 |
| `fix_reflow_spine_order.py`, `fix_reflow_structure.py` | 초기 개발 단계의 부분 스크립트(참고용, `build_reflow_generic.py`에 통합됨) |

## 알려진 한계 / 향후 개선 필요

- `build_reflow_generic.py`는 "출판사소개/판권/영문표지" 등을 **본문 텍스트 마커**(예:
  "도서출판", "ISBN_", "Copyright")로 탐지한다. 번역서마다 문구가 다르면(출판사명이
  다르거나 판권 형식이 다르면) 마커를 재조정해야 한다.
- 인쇄용 목차 페이지가 두 가지 패턴으로 나타날 수 있다: (a) 빈 링크(`href=""`)만 있는
  로마자 전용 페이지 (b) 실제 파일로 연결되는 하이퍼링크가 있는 목차 페이지. 둘 다 탐지해서
  제거해야 epubcheck에서 깨진 링크 오류(RSC-007)가 안 난다.
- 원본 .indd 문서에 "장 제목" 스타일이 있어도 실제로 어떤 단락에도 적용 안 되어 있으면
  (조판 실수) `BreakDocument`가 전혀 분할을 못 한다 — 이 경우는 자동화로 감지만 가능하고
  수정은 InDesign에서 수동으로 해야 한다(2026-10-01 "아가서1" 사례).
- 145권 전체 확장 전 몇 권 더 샘플 테스트 권장.

## 스타일 스펙 (오너 확정, 2026-10-01)

장제목 12pt(Adobe Myungjo Std M, 명조) / 소제목 11pt(KoPubWorldDotum Bold, 고딕,
배경색 없음) / 본문 10pt(SeoulHangang M) / 인용문 9pt(SeoulHangang B + 이탤릭 +
파란색 #0c3388). ISBN은 OPF `<dc:identifier>urn:isbn:...</dc:identifier>`로 등록
(uuid identifier는 폰트 복호화 키라서 별도 유지).
