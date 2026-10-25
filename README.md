# economicissue

3040 네이버 블로그용 이슈 글 제작. **제목 1개 + 자연스러운 분량의 원고 + 이미지 총 3~4장**을 만든다. 2천자를 강제하지 않는다. 네이버 게시는 사용자가 한다.

## 작성 방향

- 월급·저축·자산·생활비·결혼 비용·부모 노후처럼 자기 상황과 비교할 수 있는 주제.
- 생활 상황 → 자료·사연 → 숫자 풀이 → 해석 → 짧은 생각의 흐름.
- 사실·해석·전망 구분. 실제 체험, 가짜 인용, 통계 범위 변경, 중복 설명 금지.
- 참고 블로그에서는 구조만 참고하며 문장·이미지를 복사하지 않는다.
- 제목은 3040이 자기 상황과 비교하고 싶은 실제 쟁점·숫자·차이·질문으로 호기심을 유도한다
- 원고는 문장마다 줄을 바꾸고 긴 줄은 32자 기준으로 나눈다
- 문단 사이는 빈 줄을 두며 문장 끝 마침표는 생략한다
- 소수점과 URL은 유지하며 수동 원고와 API 원고 모두 같은 후처리를 적용한다

## 설치·실행

Python 3.11 이상. 저장소 루트에서:

```sh
pip install .
economicissue prepare --url https://example.com/actual-report
```

위 URL은 형식 예시다. 실제 공개 원문으로 교체한다. 기관 보고서 PDF를 지원하며 로그인·차단 페이지는 우회하지 않는다. PDF 다운로드를 위해 `python -m playwright install chromium`을 먼저 실행한다.

기본 직접 수집에는 네이버 키가 필요 없다. 자동 원고 작성에는 아래 환경 변수를 설정한다. `.env.example`은 설명용이며 자동으로 읽지 않는다.

```sh
export OPENAI_API_KEY=...
export OPENAI_MODEL=gpt-4.1-mini
economicissue run
```

Windows PowerShell은 `$env:변수명="값"`으로 설정한다. 키를 코드·커밋·원고에 넣지 않는다. 모델 이름은 변경 가능하다. 호출은 유료이며 코드 설치나 테스트만으로 API를 호출하지 않는다.

키 없이 ChatGPT에서 작성하려면 `prepare --url 실제원문`으로 만든 `output/brief.json`, `instructions.txt`, `schema.json`을 함께 전달한다. 받은 JSON을 `draft.json`에 저장한 후:

```sh
economicissue build --draft draft.json
```

## 자료 수집

`policy.json`의 `direct_sources` 목록을 직접 확인한다. 각 목록 첫 페이지의 제한된 수만큼 읽는다. 제목·검색 요약만으로 원고를 생성하지 않는다. 사이트가 수집을 허용하지 않으면 실패로 기록한다.

| 출처 | 자동 수집 경로 | 범위 |
|---|---|---|
| 블라인드 | 주식·투자 / 결혼생활 공개 게시판 | 실제 공개 원문, 익명 주장으로 표시 |
| 하나금융연구소 | 금융소비트렌드 보고서 목록 | 상세 설명 + 다운로드 가능한 첨부 PDF |
| KB경영연구소 | 연구보고서 / 브랜드보고서 목록 | 상세 설명 + 다운로드 가능한 첨부 PDF |
| KOSIS | 최근수록자료 공식 RSS | 갱신 자료 알림과 원문 상세 |
| 국가데이터처 | 공식 보도자료 RSS | 소득·자산·물가·가계 관련 발표 원문 |

KOSIS와 국가데이터처의 원문 URL·본문 해시로 중복을 제거한다. RSS 알림 자체는 통계 수치의 근거로 사용하지 않는다. RSS 알림과 통계 수치 조회는 다르다. 수치 API를 쓰려면 `KOSIS_API_KEY`와 KOSIS에서 발급한 통계자료 명세를 `kosis_series`에 등록한다.

```json
[{"title":"운영자가 선택한 통계명","source_url":"실제 KOSIS 통계표 URL","userStatsId":"KOSIS에서 발급한 값","prdSe":"Y","newEstPrdCnt":2}]
```

위 값은 형식 예시이며 실제 발급값으로 바꿔야 한다. 키는 환경 변수에 넣는다. 응답의 기간·항목·단위와 값을 근거에 남긴다. 표별 조회 조건은 추정하지 않는다. API 명세: [KOSIS 통계자료](https://kosis.kr/openapi/devGuide/devGuide_0201List.do).

뉴스·커뮤니티는 최근 7일, 보고서·통계는 최근 120일이 기본 후보 범위다. 날짜 미확인 자료는 `date_verified=false`로 표시하며 최신이라고 단정하지 않는다. 키워드 점수는 관심도의 추정치다. 출처별 후보를 번갈아 선정해 특정 게시판이 후보를 독점하지 않게 한다. `output/collection_status.json`에 출처별 목록 탐색 성공/실패와 원문 추출 오류를 기록한다. 목록 탐색 성공이 본문 수집 성공을 뜻하지는 않는다.

PDF는 실제 링크로 다운로드하고 최대 40페이지까지 읽으며 페이지 번호를 남긴다. JavaScript 다운로드는 별도 Chromium에서 실제 링크를 클릭한다. 스캔 PDF OCR·비공개 첨부·외부 도메인 다운로드는 지원하지 않는다. 첨부를 읽지 못해도 HTML 설명이 충분한 경우만 사용하고 실패 사실을 기록한다. PDF 전용 수치를 추측하지 않는다.

네이버 검색은 선택적 보완 경로다. `queries` 또는 `official_queries`를 설정할 경우에만 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`을 사용한다.

## 토큰 절약

1. 검색·중복 제거·접속 확인은 코드가 처리한다.
2. 후보 최대 12개, 본문 최대 4개, 입력 근거 합계 6,400자로 제한한다.
3. 원문 전체 대신 첫 문맥과 주제 관련 단락을 전달한다.
4. 짧은 고정 지침과 JSON Schema로 **원고·제목·카드 문구를 한 번에** 생성한다.
5. 동일 근거·지침·모델의 응답을 캐시하며 오류 때 자동 재호출하지 않는다.
6. 이미지는 Pillow로 렌더링하므로 별도 이미지 모델 호출이 없다.
7. `review.json`에 실제 API 토큰 사용량을 저장한다. 문자 제한은 정확한 토큰 제한이 아니다.

## 이미지

기본은 썸네일 1장 + 출처가 연결된 설명 카드 2장이다. `image_count`를 4로 바꿀 수 있다. 사진을 가져왔다고 표시하지 않으며 기본 썸네일은 색상 배경과 텍스트다. 한글 폰트는 Windows 맑은 고딕 또는 Linux 나눔고딕을 사용한다. 다른 환경에서는 `KOREAN_FONT`를 지정한다.

이용 가능한 원문을 실제 캡처하려면 `pip install '.[capture]'`와 `python -m playwright install chromium`을 실행한다. `policy.json`의 `capture`를 true로 설정하고 다음 명세를 `captures.json`으로 저장한다.

```json
[{"card":2,"source_id":"s1","selector":"#article-content","highlights":["원문에 실제로 있는 핵심 문장"],"rights":"운영자가 확인한 구체적인 이용 허락 또는 이용 조건"}]
```

`economicissue build --draft draft.json --captures captures.json`으로 지정 카드를 캡처로 대체한다. selector는 실제 원문에서 지정해야 한다. 자동으로 허락을 판정하지 않으며 실패 시 완성본을 만들지 않는다. 원문 전체보다 필요한 본문·도표를 좁게 캡처한다. 게시판명·작성 시점이 이미지에 보일 필요는 없다. 대체 이미지 텍스트는 사용자가 별도로 작성한다. 출처 기록은 sources.json에 유지한다. 모든 사이트가 지원되는 것은 아니다.

본문 캡처에는 `highlights`로 핵심 문장을 지정한다. DOM에서 실제 문장의 위치를 찾아 빨간 밑줄을 그리며 여러 줄이나 인라인 태그로 나뉜 문장도 지원한다. 해당 문장이 없거나 여러 번 나타나거나 캡처 밖에 있으면 제작을 중단해 잘못된 강조를 방지한다. 사진을 썸네일 배경으로 쓰는 `card: 1`은 밑줄 문장 없이 사용할 수 있다.

`card: 1`로 지정하면 해당 영역을 썸네일 배경으로 사용하고 어둡게 처리한 뒤 제목을 얹는다. `card: 2`부터는 본문 이미지다. 사용 가능한 사진 영역 또는 도표를 운영자가 실제 페이지에서 지정해야 한다.

## 결과·검토

`output/<주제해시>/`에 `post.txt`, PNG 3~4장, `manifest.json`, `sources.json`, `review.json`, `draft.json`, `delivery.json`, `gallery.html`이 생성된다. post.txt의 이미지 표시 위치에 PNG를 삽입한다. 설명 카드에는 축약 출처를 넣고 원문 링크는 sources.json과 원고 하단에 남긴다. 캡처에는 출처·게시 시점 표시를 덧씌우지 않는다. 중간 자료는 완성 이미지와 다른 폴더에 저장한다.

완성 폴더는 이미지까지 모두 생성한 뒤 한 번에 확정한다. 형식·출처 ID·이미지 개수·삽입 위치·중복 문단을 자동 검사한다. **내용의 의미와 근거가 맞는지, 캡처 이용 조건은 게시 전 사람이 검토해야 한다.** URL·본문 해시·topic_key로 재사용을 막지만 유사 사건을 완벽히 식별하지는 못한다. 제작 이력은 게시 완료 이력이 아니다.

## 이미지 전달 방식

`delivery.json`은 **썸네일 먼저 → 본문 이미지 순서**로 최종 PNG만 지정한다. 전달하는 에이전트·앱은 이 파일들을 한 번에 네이티브 멀티 이미지 갤러리로 첨부해야 한다. 대체 이미지 텍스트는 사용자가 작성하므로 자동 작성하지 않는다. 이미지 파일 생성만으로 채팅 표시 성공을 주장하지 않는다.

저장소 코드는 ChatGPT/iOS의 갤러리 UI를 직접 제어할 수 없다. `delivery.json` 자체가 갤러리를 띄우지는 않으며 받는 앱의 실제 이미지 첨부 기능이 필요하다. 채팅에 네이티브 갤러리를 제공할 때 ZIP·Library 링크·개별 파일 링크로 대체하지 않는다.

함께 생성하는 `gallery.html`은 이미지가 내장된 별도 갤러리다. 파일을 열면 큰 이미지와 아래 썸네일 목록이 보이고, 각 이미지를 선택해 다운로드할 수 있다. 채팅 앱의 네이티브 갤러리와는 별개이며 한 파일만 옮겨도 동작한다.

## GitHub Actions

Actions의 `Build issue package`에서 `prepare`를 선택하면 API 키 없이 직접 자료만 수집한다. `run`은 유료 모델로 원고까지 만들며 Repository Secret `OPENAI_API_KEY`가 필요하다. KOSIS 수치 조회는 선택적으로 `KOSIS_API_KEY`를 등록한다. 모델은 Repository Variable `OPENAI_MODEL`로 지정한다. 결과는 Actions Artifact로 받는다. 일정은 아직 지정하지 않았으므로 예약 실행은 설정하지 않았다. `Check pipeline`은 커밋·PR에서 의존성을 설치하고 오프라인 테스트를 실행한다.

수집 캐시·제작 이력·산출물은 Actions 캐시에 보존한다. 캐시는 만료·삭제될 수 있어 영구 이력 저장소는 아니다. 공개 저장소의 Artifact에 원문이나 개인정보가 들어가지 않도록 주의한다. 게시용 파일만 올릴 때는 `output/<주제해시>/`를 사용한다.

## 검증

```sh
python -m unittest discover -s tests -v
```

오프라인으로 근거 예산, 출처 검증, 실패 시 부분 결과 제거, 이미지 수와 패키지 생성 등을 확인한다. 실제 검색·유료 모델 호출 성공을 보증하는 테스트는 아니다.

API 명세: [네이버 뉴스](https://developers.naver.com/docs/serviceapi/search/news/news.md), [네이버 웹문서](https://developers.naver.com/docs/serviceapi/search/web/web.md), [OpenAI Responses](https://developers.openai.com/api/reference/resources/responses/methods/create).

