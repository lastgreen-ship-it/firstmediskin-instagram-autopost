# 퍼스트메디스킨 인스타그램 자동 게시 — 인수인계서

> 매일 1회 @firstmediskin_ 피드를 클라우드에서 자동 게시하는 시스템.
> 퍼스트커피랩(`firstcoffeelab-instagram-autopost`)과 **같은 구조**로 복제했고, **캐러셀 게시**와 **1일 1건 보장**만 추가했습니다.

---

## 1. 개요
PC가 꺼져 있어도, 아무도 로그인하지 않아도 **GitHub 서버가 매일 자동으로** 인스타에 게시합니다.

**구조 = GitHub 저장소(콘텐츠 + 코드) + GitHub Actions(스케줄러) + Instagram Graph API(게시)**

---

## 2. 구성 요소 (한 저장소에 전부 저장)
저장소: `github.com/lastgreen-ship-it/firstmediskin-instagram-autopost` (**Public** — 커피랩과 별도 저장소)

| 파일 / 위치 | 역할 |
|---|---|
| `mediskin_YYYYMMDD_NN.jpg` (저장소 루트) | 완성된 게시물 이미지 (1080×1350) |
| `content_queue.json` | 예약 목록. 항목 = `{date, slot:"am", title, media_type, image_path 또는 image_paths, caption, posted:false}` |
| `post_log.json` | 실제 게시 기록(성공/실패) = **게시 진실 원본** |
| `instagram_post.py` | 큐에서 오늘 항목을 골라 IG API로 게시 |
| `.github/workflows/autopost.yml` | 실행 스케줄(cron) |
| `tools/` | 게시물 이미지 제작 도구 (문구·사진·템플릿) |
| GitHub Secret `IG_ACCESS_TOKEN`, `IG_USER_ID` | 인스타 토큰·계정 ID (코드에 노출되지 않음) |

`media_type`
- `"IMAGE"` 사진 1장 → `image_path: "mediskin_20260929_01.jpg"`
- `"CAROUSEL"` 사진 2~10장 → `image_paths: ["..._01.jpg", "..._02.jpg", ...]` (순서대로 게시) ← **메디스킨에서 추가**
- `"REELS"` 영상 → `image_path: "xxx.mp4"` (선택 `cover_path`)

---

## 3. 동작 방식
1. GitHub Actions가 cron으로 실행 → **UTC 00~09시 매시 :12분 = KST 09:12~18:12, 하루 10회 분산 시도**
2. **오늘 이미 게시 성공 기록(post_log)이 있으면 건너뜀** ← 메디스킨에서 추가 (밀린 항목이 같은 날 여러 건 올라가는 것 방지)
3. 큐에서 **오늘 날짜(am) 미게시 항목** 선택 (없으면 과거 미게시 폴백). 날짜는 한국시간 기준
4. 이미지 공개 URL(`raw.githubusercontent`) → IG Graph API 컨테이너 생성 → 게시(publish)
5. `posted:true` + `post_log` 자동 커밋 → **1일 1건, 중복 없음**

---

## 4. 최초 셋업 절차
1. **@firstmediskin_ 를 프로페셔널(비즈니스) 계정으로 전환**
2. **Meta 개발자(developers.facebook.com)**: 앱 생성(커피랩 앱 재사용 가능) → Instagram 연결 → 권한 `instagram_business_content_publish` → **@firstmediskin_ 로 로그인해 액세스 토큰(약 60일) 발급**, `IG_USER_ID` 확인
   - 커피랩 토큰은 커피랩 계정 전용이라 **메디스킨 계정 토큰을 새로 발급**해야 합니다
3. **새 GitHub 저장소(Public) 생성**: `firstmediskin-instagram-autopost` → 이 폴더 전체 업로드
4. **Secret 등록**: Settings → Secrets and variables → Actions
   - `IG_ACCESS_TOKEN` = 메디스킨 토큰
   - `IG_USER_ID` = 메디스킨 계정 ID (**필수** — 커피랩과 달리 스크립트에 기본값 없음)
5. **Settings → Actions → General → Workflow permissions → Read and write** (게시 상태 커밋용)
6. **Actions 탭 → "Instagram 자동 게시 (퍼스트메디스킨)" → Run workflow** 로 첫 게시 테스트

---

## 5. 운영 규칙 (필수)
### 콘텐츠 추가
1. 미드저니 폴더에서 쓸 사진을 `tools/assets/photos/` 에 복사
2. `tools/posts.json` 에 날짜별 게시물 추가 (기존 항목 복사 → 문구·사진 이름만 변경)
   - 템플릿: `mood`(사진+아이보리 패널 손글씨) / `cover`·`list`·`cta`(정보형 캐러셀)
   - 캡션 하단 공통 문구·해시태그는 맨 위 `config` 한 곳만 수정 (현재: 1:1 맞춤 상담 · 가까운 지점 예약 안내)
3. `python tools/make_posts.py` → 루트에 이미지 생성 + `content_queue.json` 에 **신규 날짜만 추가**
4. 커밋·푸시

⚠️ **업로드 전 저장소의 최신 `content_queue.json`·`post_log.json` 을 먼저 받아서(pull)** 작업할 것.
통째로 덮어쓰면 이미 올린 게시물이 `posted:false` 로 돌아가 다시 올라갑니다.
(`make_posts.py` 는 기존 항목을 건드리지 않고 신규만 추가하도록 되어 있음)

### 토큰 관리
- 약 60일마다 만료 → 만료 전 `refresh_access_token` 으로 갱신 후 Secret 교체
- 🔒 **토큰 값은 채팅·문서·코드에 절대 노출 금지** (GitHub Secret 에만 보관)
- 확인: `python instagram_post.py --check` (로컬 `.env` 에 토큰 넣고 실행)

### 검증
- 커밋 직후 raw 는 기존 파일을 ~5분 캐시 (신규 이미지는 즉시 반영)
- `content_queue.json?v=타임스탬프` 캐시버스터 또는 github.com blob(커밋 SHA)로 확인

---

## 6. 주의점
- **GitHub 무료 예약은 지연·누락이 있음** → 10회 분산으로 완화 (100% 보장은 아님)
- **이미지는 JPEG만**, 비율 4:5~1.91:1. 제작 도구 출력(1080×1350)은 규격에 맞음
- **post_log = 게시 진실 원본.** 큐 상태가 어긋나면 post_log 기준으로 복구
- **게시 실패 감지**: 매일 저녁 그날 `posted` 여부를 확인하는 점검 알림 세팅 권장
- **그리드 배열 주의**: 본계정 피드는 여러 칸을 이어 붙인 퍼즐형 그리드입니다. 새 게시물이 올라갈 때마다 기존 칸이 한 칸씩 밀려 퍼즐 그림이 어긋납니다. 퍼즐을 유지하려면 그리드 게시물을 고정(핀)하거나, 한 줄(3칸) 단위로 올리는 방식을 검토하세요.
- 피부관리샵 광고 표현 주의: 치료·완치·재생 보장 등 의료행위 연상 표현, 비포·애프터 사진은 피할 것

---

## 7. 체크리스트
- [ ] @firstmediskin_ 비즈니스 계정 전환
- [ ] Meta 앱 + `instagram_business_content_publish` 권한 + 메디스킨 토큰 발급
- [ ] GitHub 저장소 `firstmediskin-instagram-autopost` (Public) 생성 + 파일 업로드
- [ ] Secret `IG_ACCESS_TOKEN`, `IG_USER_ID` 등록
- [ ] Workflow permissions → Read and write
- [ ] Actions 수동 실행으로 첫 게시 확인
- [ ] 점검 알림 세팅
- [ ] 토큰 만료일 캘린더 등록

---

## 현재 예약 (2026-09-29 ~ 10-05)
| 날짜 | 형식 | 제목 |
|---|---|---|
| 9/29 | 단일 | 피부에도 쉼표가 필요해요 |
| 9/30 | 캐러셀 5장 | 겉보습만으론 부족한 속건조 |
| 10/1 | 단일 | 당신의 피부를 먼저 듣습니다 |
| 10/2 | 캐러셀 5장 | 막힌 모공, 결부터 매끈하게 |
| 10/3 | 단일 | 오늘의 나에게, 작은 선물 |
| 10/4 | 캐러셀 5장 | 칙칙한 안색, 맑게 톤업 |
| 10/5 | 단일 | 처음이라면, 진단부터 |

셋업이 9/29 이후에 끝나면 지난 날짜 항목은 "오늘 항목이 없는 날" 폴백으로 하루 1건씩 올라갑니다.
날짜를 다시 잡고 싶으면 `content_queue.json` 의 `date` 만 수정하세요.

*문서 작성일: 2026-09-28*
