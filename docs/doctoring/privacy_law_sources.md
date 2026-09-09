# Privacy sources and interpretation boundaries

Source and date observations are partial. Selected clause text was re-read on
2026-09-10; no organization-specific applicability decision or legal approval
has been established. Advertising is not a source of requirements. Citation
identifiers below are document-local references, not official control catalog
identifiers. This is an engineering source register, not an exhaustive legal
opinion, operational rule engine or certification.

## Verification scope

`clause_text_verified=true` applies **only to the named scope**, not the entire
instrument, subordinate regulations or its applicability to a legal entity.
`applicability_reviewed=false` means the required entity/processing/deployment
facts and authorized review have not been established. These are documentary
states; this change does not implement or activate a legal decision engine.

| Source | Text scope checked | clause_text_verified | applicability_reviewed | Observation |
| --- | --- | --- | --- | --- |
| L1 | Article 29 in the pinned Act No. 20897 edition | true | false | Official clause text read 2026-09-10. |
| L2 | Article 6 of Notice No. 2026-9; not every notice clause | true | false | Official clause page and effective-date header read 2026-09-10. |
| L3 | Amendment text and supplementary Articles 1–2 of Act No. 21445 | true | false | Official promulgation text read 2026-09-10; implementing-decree thresholds are not verified here. |
| L4 | Article 21 in the pinned Act No. 20897 edition | true | false | Official clause text read 2026-09-10. |
| L5 | Article 28-8 in the official Act No. 20897 page | true | false | Official clause text read 2026-09-10; account contracts and transfer circumstances are not established. |
| L6 | No complete clause text checked | false | false | Earlier 2026-09-09 listing observation only; not a fresh clause/effective-date verification. |

Do not activate an unverified automatic interpretation, exemption or affirmative
compliance decision. A designated legal/compliance reviewer must establish the
exact rule and applicable facts first. This does **not** suspend legal duties,
disable existing safeguards or make unknown applicability equal to exemption.
Protective controls remain active while uncertain obligations stay open for
review. Neither a document check nor a test pass grants a legal authorization.

## Primary legal references (APA 7)

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
- **T5.** FastAPI. (n.d.). *Handling errors*. Retrieved September 10, 2026, from
  https://fastapi.tiangolo.com/tutorial/handling-errors/
  Documents RequestValidationError and the custom-handler extension point.
  Local regressions separately reproduce rejected values in `input` and
  caller-supplied dictionary keys in `loc`; removing only `input` is insufficient.

## Evidence needed before legal or operational closure

The legal entity, controller/processor role, purpose, data classes, actual
contracts, appointment and staffing facts, exact released source and deployed
controls require separate evidence. The final decree implementing the
September 11 amendment and every subordinate transition rule have not been
completely verified here. Do not encode draft CPO/certification thresholds or
one universal incident deadline. Preserve scope-specific `unverified` states;
absence of a retrieved source never proves that an obligation does not apply.
