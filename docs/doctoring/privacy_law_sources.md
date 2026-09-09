# Privacy sources and interpretation boundaries

Verified on 2026-09-09. Advertising is not a source of requirements. Citation
identifiers below are document-local references, not invented official control
catalog identifiers. These are selected engineering sources, not an exhaustive
legal opinion or a certification.

## Primary legal references (APA 7)

- **L1.** 개인정보 보호법, 법률 제20897호 (2025). 시행 2025년 10월 2일.
  [국가법령정보센터 제29조](https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=00&joNo=0029&lsiSeq=270351&urlMode=lsScJoRltInfoR).
  Supports the duty to implement technical, administrative and physical safeguards.
- **L2.** 개인정보보호위원회. (2026년 7월 1일). *개인정보의 안전성 확보조치 기준*
  (고시 제2026-9호).
  [공식 전문](https://law.go.kr/admRulLsInfoP.do?admRulSeq=2100000281400),
  [제6조](https://www.law.go.kr/LSW/admRulSideInfoP.do?admRulSeq=2100000281400&chrClsCd=010201&dashNo=&docCls=jo&joBrNo=00&joNo=0006&urlMode=admRulScJoRltInfoR).
  The current notice, not the older 2023 notice, anchors this access-control repair.
- **L3.** 개인정보 보호법 일부개정법률, 법률 제21445호 (2026).
  [공포문 및 부칙](https://www.law.go.kr/LSW/lsRvsDocListP.do?chrClsCd=010202&lsId=011357&lsRvsGubun=all).
  Main effective date: 2026-09-11. The Article 32-2(1) proviso and Article
  75(2)(15) take effect on 2027-07-01. Article 34(1)/(4) and 34(2) transition
  on awareness after commencement; Article 34(3) uses occurrence after it.
  A single incident timestamp cannot represent all those applicability tests.
- **L4.** 개인정보 보호법 제21조.
  [공식 파기 조항](https://www.law.go.kr/LSW/lsLinkProc.do?chrClsCd=010202&datClsCd=010102&gubun=admRul&joNo=002100000%5E003700004&lsId=2073298&lsNm=%EA%B0%9C%EC%9D%B8%EC%A0%95%EB%B3%B4%EB%B3%B4%ED%98%B8%EB%B2%95&mode=10).
  Unneeded data and lawfully retained data require different disposition paths;
  append-only history is not an unlimited right to retain personal payloads.
- **L5.** 개인정보 보호법 제28조의8.
  [공식 국외이전 조항](https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1029334737).
  Check the applicable enumerated basis and transfer conditions. Do not turn
  every transfer into a consent-only requirement or infer account terms from a
  provider marketing statement.
- **L6.** 개인정보보호위원회. (2026년 8월 20일). *개인정보 처리방법에 관한 고시*
  (고시 제2026-10호).
  [공식 고시 목록](https://m.pipc.go.kr/np/cop/bbs/selectBoardList.do?bbsId=BS216&etc1=%EA%B3%A0%EC%8B%9C&mCode=G010020040).
  Existence and effective date confirmed from the official listing. Full clause
  extraction and its rights/procedure impact are **not yet verified** here;
  do not silently treat an older form/procedure as the final current rule.

## Primary implementation references (APA 7)

- **T1.** OWASP Foundation. (n.d.). *Cross-Site Request Forgery Prevention Cheat
  Sheet*. Retrieved September 9, 2026, from
  https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- **T2.** Starlette. (n.d.). *Middleware*. Retrieved September 9, 2026, from
  https://www.starlette.io/middleware/
- **T3.** ASGI. (n.d.). *HTTP & WebSocket ASGI Message Format*. Retrieved
  September 9, 2026, from https://asgi.readthedocs.io/en/latest/specs/www.html

- **T4.** WHATWG. (n.d.). *Fetch Standard, section 3.2: Origin header*. Retrieved
  September 9, 2026, from https://fetch.spec.whatwg.org/#origin-header
  Native non-CORS POSTs under `no-referrer` receive null Origin; use a compatible
  same-origin referrer policy instead of weakening null-origin rejection.

## What the evidence does not establish

L1/L2 support access protection; they do not mandate this implementation or
establish that CSRF headers alone satisfy Article 29. The legal entity,
controller/processor role, processing purpose, data classes, applicable
thresholds, contract terms and deployment facts are required separately.

The final decree implementing the September 11 amendment and all subordinate
transition provisions have not been completely verified in this execution.
Do not encode draft CPO/certification thresholds or one universal incident
notification deadline. Keep rules inactive/unverified until the exact final
source and its applicability have been reviewed. Do not assume that absence of
retrieved evidence means an obligation does not apply.
