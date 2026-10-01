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
| `build_reflow_generic.py` | **리플로우 EPUB 빌드 일반화 버전** — 콘텐츠 마커 기반으로 앞부속/목차/장 구조를 자동 탐지(10/10권 정밀 검증 + 145/145권 실험적 확장 완료, 아래 참조) |
| `batch10_export.py` / `batch10_postprocess.py` | 10권 파일럿용 InDesign raw export + 후처리 배치 |
| `batch145_reflow_export.py` / `batch145_reflow_postprocess.py` | **145권 전체 확장용** — `resolve_indd_paths.py`로 찾은 경로를 20권 단위 배치로 export+후처리(`python batch145_reflow_export.py <시작인덱스> <개수>`) |
| `fix_reflow_spine_order.py`, `fix_reflow_structure.py` | 초기 개발 단계의 부분 스크립트(참고용, `build_reflow_generic.py`에 통합됨) |

## 145권 리플로우 확장 현황 (2026-10-01)

145권 전체 빌드 성공 + epubcheck 0오류 — **단, 이건 10권 파일럿과 같은 수준의 검증이
아니다.** 오너 지시로 가볍게(epubcheck만) 돌린 실험적 확장이며, 아래는 아직 안 한 것:
- 리더 앱(교보·토리움·킨들)에서 직접 열어본 책 0권
- raw vs final 글자수 대조(콘텐츠 손실 감사) 미실시 — 10권 때 이걸로 시편44의 22KB
  분량 챕터 소실을 잡아냈었다. 145권은 이 감사를 안 거쳤으므로 유사한 숨은 손실이
  있을 수 있다.
- "6. 스펄전의 여호수아서의 복음이야기" 1권은 `chapters: 0`으로 빌드됨(원인 미조사)
- 오너가 "최종 완성본 기준으로 작업하라"고 리플로우 작업 범위를 명확히 했으므로
  (고정형만 "대충 해도 됨"), **배포 전 10권 파일럿 수준의 전체 재검증이 필요하다.**

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
- **[2026-10-01] 로마자 라벨이 원본에서 중복될 수 있다**(번역/조판 실수로 같은 장이
  두 번 "V"로 표기되는 등 — "시편44" 6장 사례). 중복 로마자 라벨을 가진 장을 무조건
  드롭하면 진짜 내용이 통째로 사라진다. 반드시 "병합된 내용 길이가 500자 미만(=인쇄용
  목차 잔재)"일 때만 드롭하고, 내용이 있으면 라벨이 중복되더라도 보존해야 한다.
- **[2026-10-01] 각주가 붙은 장은 제목+각주만 담긴 파일과 본문이 이어지는 파일로
  쪼개져서 나올 수 있다**(로마자 마커가 없는 'body' 파일로 본문이 계속됨). 'chapter'로
  병합된 파일 바로 뒤, 다음 로마자/장 전까지 있는 'body' 파일은 전부 그 장에 합쳐야
  한다. 이때 그 파일이 **자기 자신만의 각주**를 갖고 있으면(예: footnote-002가
  "-35.xhtml#footnote-002"처럼 자기 파일명을 참조) 병합 후 그 self-reference를
  대상 파일명으로 바꿔줘야 한다 — 안 그러면 epubcheck가 "존재하지 않는 리소스 참조"
  오류(RSC-007)를 낸다.
- 본문/인용문 CSS 클래스가 책마다 변형 이름을 쓸 수 있다(`본문-줄이기` vs
  `본문-간격-축소`, `인용-싯구` vs `인용-간격-축소` 등) — 스타일 강제 규칙에 발견되는
  대로 전부 추가해야 "일부 문단만 다른 폰트로 보임" 문제가 안 생긴다.
- 145권 전체 확장 전 몇 권 더 샘플 테스트 권장.

## 스타일 스펙 (오너 확정, 2026-10-01)

장제목 12pt(Adobe Myungjo Std M, 명조) / 소제목 11pt(KoPubWorldDotum Bold, 고딕,
배경색 없음) / 본문 10pt(SeoulHangang M) / 인용문 9pt(SeoulHangang B + 이탤릭 +
파란색 #0c3388). ISBN은 OPF `<dc:identifier>urn:isbn:...</dc:identifier>`로 등록
(uuid identifier는 책마다 고유해야 함 - 아래 "서점별 업로드 요구사항" 참조).

## 서점별 업로드 검증 요구사항

epubcheck 통과 ≠ 서점 업로드 통과. 각 플랫폼이 epubcheck에 없는 자체 검증을
추가로 거는 경우가 있다 — 발견되는 대로 여기 추가할 것.

- **알라딘(Aladin)** (오너 스크린샷, 2026-10-01 — 10권 리플로우 전체 업로드 거부):
  1. **내부 xhtml 파일명은 영문+숫자만, 공백·괄호·한글 금지.** InDesign이 그대로
     내보낸 `스펄전의_잠언의_복음이야기_1(294_ebook_출판용)-2.xhtml` 같은 파일명은
     거부된다. `text-NNNN.xhtml` 형태로 전부 변경하고, 책 전체에서 그 파일을
     가리키는 모든 링크(장간 이동·각주·nav.xhtml·toc.ncx·OPF 자체)를 같이
     바꿔야 한다 — 하나라도 빠지면 깨진 링크 오류가 난다.
  2. **`META-INF/encryption.xml`이 있으면 업로드 자체가 거부된다** — 즉 IDPF
     폰트 난독화(보호)를 전혀 허용하지 않는다. 이는 "어도비 폰트는 보호된
     형식으로만 임베딩 허용" 요건과 정면 충돌한다. 오너가 사용 폰트 전부
     정식 라이선스 보유를 확인(2026-10-01)했으므로, 이 시리즈는 폰트를
     평문(비보호) 그대로 임베딩하는 쪽으로 정리했다 — **다른 폰트/다른
     라이선스 상황이면 이 판단을 그대로 적용하지 말 것.**
  - **미해결**: 고정형(fixed-layout) 145권은 2026-10-01에 별도로 폰트 보호
    (encryption.xml)를 새로 추가했다(`fix_fixed_layout_full.py`) — 알라딘에
    고정형도 올릴 계획이면 이 145권도 같은 이유로 encryption.xml을 다시 빼야
    한다. 리플로우 10권처럼 아직 반영 안 됨 — 오너 확인 후 처리 필요.
    (파일명 규칙은 고정형이 원래부터 `fix_indesign_epub.py`에서 text-NNNN로
    바꾸고 있어서 1번은 이미 해당 없을 가능성이 높음, 별도 검증은 안 해봄.)
