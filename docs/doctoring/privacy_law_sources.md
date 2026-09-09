# Privacy sources and interpretation boundaries

The 2026-09-09 and 2026-09-10 entries below are historical reading reports.
Their precise observation instants and archived raw responses were not retained
in this repository. They are not reproducible verification receipts or fresh
legal/PR/release/deployment evidence. A reported reading date is neither a
source publication date nor an effective date. No organization-specific
applicability decision or legal approval has been established.

Advertising is not a source of requirements. Citation identifiers below are
local references, not official control catalog identifiers. This engineering
source register is not an exhaustive legal opinion or operational rule engine.

## Verification scope and missing observation evidence

For this register, `clause_text_verified=true` requires both a named text scope
and a retained observation receipt that binds a timezone-qualified ISO 8601
instant to the actual raw response and its digest. The earlier reading reports
do not satisfy that evidentiary requirement, so their flags are now false.
This does not assert that the texts were never read or are incorrect.
`applicability_reviewed=false` separately means that required entity, processing,
contract and deployment facts and authorized review remain unestablished.
These are documentary states, not a newly implemented legal decision engine.

| Source | Historically reported reading scope | Reported reading date | observed_at | raw_evidence_ref | clause_text_verified | applicability_reviewed |
| --- | --- | --- | --- | --- | --- | --- |
| L1 | Article 29 in Act No. 20897 | 2026-09-10 | null | null | false | false |
| L2 | Article 6 and effective-date header of Notice No. 2026-9 | 2026-09-10 | null | null | false | false |
| L3 | Amendment and supplementary Articles 1-2 of Act No. 21445 | 2026-09-10 | null | null | false | false |
| L4 | Article 21 in Act No. 20897 | 2026-09-10 | null | null | false | false |
| L5 | Article 28-8 in Act No. 20897 | 2026-09-10 | null | null | false | false |
| L6 | Listing only, no complete clause text | 2026-09-09 | null | null | false | false |

`null` means unavailable, not midnight and not an inferred commit timestamp.
The date 2026-09-10 remains the reported local reading date; it is not relabeled
as a future date because its UTC commit was on the preceding calendar day.
The official URLs below are citations to reacquire, not archived response URLs.
Before legal activation, a designated reviewer must reacquire the exact edition,
retain permitted source evidence, and review interpretation and applicability.
Do not activate unverified interpretations, exemptions or affirmative compliance
claims. Existing safeguards and legal duties remain in force; unknown is not
not-applicable.

The same restriction applies to historical T1-T5 access reports below. Their
`observed_at` and `raw_evidence_ref` are null and their observation-verification
state is `unverified`. Their citations identify implementation references, not
proof of a deployed control. A new timestamp must describe a new collection,
never be backfilled onto the old reading report.

## Primary legal references (APA 7)

The interpretations below preserve the earlier engineering rationale for review;
they are not independently verified legal decisions.

- **L1.** 개인정보 보호법, 법률 제20897호 (2025). 시행 2025년 10월 2일.
  [국가법령정보센터 제29조](https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=00&joNo=0029&lsiSeq=270351&urlMode=lsScJoRltInfoR).
  Establishes the technical, administrative and physical safeguard duty; it does
  not prescribe this HTTP implementation or prove that it satisfies the full duty.
- **L2.** 개인정보보호위원회. (2026년 7월 1일). *개인정보의 안전성 확보조치 기준*
  (고시 제2026-9호).
  [공식 전문](https://law.go.kr/admRulLsInfoP.do?admRulSeq=2100000281400),
  [제6조](https://www.law.go.kr/LSW/admRulSideInfoP.do?admRulSeq=2100000281400&chrClsCd=010201&dashNo=&docCls=jo&joBrNo=00&joNo=0006&urlMode=admRulScJoRltInfoR).
  Article 6 supports access protection and preventing unauthorized exposure
  through websites and other channels. The selected engineering repairs are
  controls contributing to that objective, not an exhaustive notice assessment.
- **L3.** 개인정보 보호법 일부개정법률, 법률 제21445호 (2026).
  [공포문 및 부칙](https://www.law.go.kr/LSW/lsRvsDocListP.do?chrClsCd=010202&lsId=011357&lsRvsGubun=all).
  Main effective date: 2026-09-11. The Article 32-2(1) proviso and Article
  75(2)(15) take effect on 2027-07-01. Supplementary Article 2 ties Article
  34(1)/(4) and 34(2) to awareness after commencement, and 34(3) to occurrence
  after it. These are different applicability clocks, not one incident timestamp.
- **L4.** 개인정보 보호법 제21조, 법률 제20897호 (2025).
  [공식 파기 조항](https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=00&joNo=0021&lsiSeq=270351&urlMode=lsScJoRltInfoR).
  Unneeded data and lawfully retained data require different disposition paths;
  append-only history is not an unlimited right to retain personal payloads.
- **L5.** 개인정보 보호법 제28조의8, 법률 제20897호 (2025).
  [공식 국외이전 조항](https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1029334737).
  Check the applicable enumerated basis and transfer conditions. Do not turn
  every transfer into a consent-only requirement or infer enabled account terms
  from a provider marketing statement. ZDR capability is not a legal basis.
- **L6.** 개인정보보호위원회. (2026년 8월 20일). *개인정보 처리방법에 관한 고시*
  (고시 제2026-10호).
  [공식 고시 목록](https://m.pipc.go.kr/np/cop/bbs/selectBoardList.do?bbsId=BS216&etc1=%EA%B3%A0%EC%8B%9C&mCode=G010020040).
  Bibliographic details are retained from the earlier listing observation.
  Complete clause text, rights/procedure impact and applicable transition rules
  are not verified in this register. Do not activate inferred procedures from it.

## Primary implementation references (APA 7)

- **T1.** OWASP Foundation. (n.d.). *Cross-Site Request Forgery Prevention Cheat
  Sheet*. Reported access date September 9, 2026.
  https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- **T2.** Starlette. (n.d.). *Middleware*. Reported access date September 9, 2026.
  https://www.starlette.io/middleware/
- **T3.** ASGI. (n.d.). *HTTP & WebSocket ASGI Message Format*. Reported access
  date September 9, 2026. https://asgi.readthedocs.io/en/latest/specs/www.html
- **T4.** WHATWG. (n.d.). *Fetch Standard, section 3.2: Origin header*. Reported
  access date September 9, 2026. https://fetch.spec.whatwg.org/#origin-header
  The earlier rationale is that no-referrer may null native form POST Origin;
  preserve the compatible same-origin policy rather than trust arbitrary null.
- **T5.** FastAPI. (n.d.). *Handling errors*. Reported access date September 10,
  2026. https://fastapi.tiangolo.com/tutorial/handling-errors/
  Documents RequestValidationError and the custom-handler extension point.
  The source-subset regressions separately test rejected values and dictionary
  keys; a citation alone is not execution evidence.
- **T6.** Python Software Foundation. (n.d.). *urllib.parse: URL parsing security*.
  https://docs.python.org/3/library/urllib.parse.html#url-parsing-security
- **T7.** Python Software Foundation. (n.d.). *functools.lru_cache*.
  https://docs.python.org/3/library/functools.html#functools.lru_cache
  T6-T7 support defensive parsing and cache-lifetime analysis. Their web-response
  archives are not retained here; no verified legal-source flag derives from them.

## Reproducible source-test evidence is separate

The new [header-retention execution receipt](../evidence/privacy_header_retention/verification_receipt.json)
binds actual UTC start/end instants, exact source/test Git OIDs and SHA-256
values, interpreter/package versions, commands, exit codes and retained raw
subprocess outputs. It covers component tests, including an original-source
negative control. It does not stand in for raw legal text, human applicability
review, full hosted Product, independent review, browser or deployment evidence.

## Evidence needed before legal or operational closure

The legal entity, controller/processor role, purpose, data classes, actual
contracts, appointment and staffing facts, exact released source and deployed
controls require separate evidence. The final decree implementing the
September 11 amendment and every subordinate transition rule have not been
completely verified here. Do not encode draft CPO/certification thresholds or
one universal incident deadline. Preserve scope-specific `unverified` states;
absence of a retrieved source never proves that an obligation does not apply.
