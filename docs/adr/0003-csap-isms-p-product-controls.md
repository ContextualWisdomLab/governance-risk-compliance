# ADR 0003: CSAP and ISMS-P as product controls

- Status: Draft
- Date: 2026-08-18

## Context

The customer README already names CSAP, SOC 2, and ISMS-P as product controls of
this leaf. SOC 2 examinations rest on the AICPA Trust Services Criteria (see
ADR 0002). CSAP and ISMS-P are Korean public programs. They belong here only if
official KISA or government catalog pages can be cited. Unofficial blogs and
invented control numbers are not enough.

These official pages were opened:

- Korea Internet & Security Agency (KISA), *클라우드서비스 보안인증(CSAP)*,
  https://www.kisa.or.kr/1050603
- Personal Information Protection Commission (PIPC), *인증제도(ISMS-P)*,
  https://www.pipc.go.kr/np/default/page.do?mCode=D040020000
- Korean Law Information Center, *개인정보 보호법*, Act No. 20897,
  https://www.law.go.kr/lsInfoR.do?chrClsCd=010202&efYd=20251002&lsiSeq=270351&urlMode=lsInfoP
- Korean Law Information Center catalog title *클라우드컴퓨팅 발전 및 이용자
  보호에 관한 법률*,
  https://www.law.go.kr/lsInfoP.do?ancYnChk=0&lsId=012266

KISA’s CSAP page states that the program evaluates whether a cloud computing
service meets information-protection criteria, cites 클라우드컴퓨팅 발전 및
이용자 보호에 관한 법률 제23조의2 as the legal basis, and cites 클라우드컴퓨팅서비스
보안인증에 관한 고시 제15조 as the criteria article. It also points operators to
https://isms-p.or.kr for application forms.

PIPC’s ISMS-P page names the program 정보보호 및 개인정보보호 관리체계 인증
(ISMS-P: Personal information & Information Security Management System),
describes the 2018-11-07 merger of ISMS and PIMS, and cites 개인정보 보호법
제32조의2. The same PIPC page publishes the official review-area structure:
management-system establishment and operation (16), safeguard requirements (64),
and personal-information processing-stage requirements (21). Article 32-2 of
Act No. 20897 was read on the Law Information Center text
(effective 2025-10-02).

The Cloud Computing Act catalog title was confirmed on law.go.kr. The article
body of 제23조의2 was not extracted from that HTML page in this environment;
the article citation used here is the one printed on the KISA CSAP page.

Individual CSAP control identifiers were not copied from an official downloadable
criteria book in this draft. They are therefore not listed.

## Decision

CSAP and ISMS-P are product controls of this GRC leaf. They are not owned by
naruon, gyeot, or CWL Security scanning lanes.

1. Officers treat CSAP (클라우드컴퓨팅서비스 보안인증 / Cloud Security
   Assurance Program) as the cloud-service certification catalog cited by KISA.
2. Officers treat ISMS-P (정보보호 및 개인정보보호 관리체계 인증) as the
   integrated information-security and personal-information management
   certification catalog cited by PIPC and KISA.
3. This draft does not invent, renumber, or store CSAP or ISMS-P control items.
   A later slice may import identifiers only from the official catalogs linked
   above.
4. Personal data collected for those controls follows ADR 0002: access control,
   encryption, and audit. Masking is not prescribed.

## Consequences

- Product copy may keep saying “CSAP, SOC 2, and ISMS-P are this product’s
  controls.”
- Empty CSAP or ISMS-P coverage remains a visible gap.
- Unofficial counts, blog “v2.2” item lists, and guessed identifiers such as
  invented clause numbers are out of scope until an official catalog file is
  attached by a later, cited change.
- This draft adds no catalog database.

## References

Korea Internet & Security Agency. (n.d.). *클라우드서비스 보안인증(CSAP)*
[Cloud Security Assurance Program]. https://www.kisa.or.kr/1050603

Ministry of Government Legislation. (n.d.). *클라우드컴퓨팅 발전 및 이용자 보호에
관한 법률* [Act on the Development of Cloud Computing and Protection of its
Users]. Korean Law Information Center.
https://www.law.go.kr/lsInfoP.do?ancYnChk=0&lsId=012266

Personal Information Protection Commission. (n.d.). *인증제도(ISMS-P)*
[Personal information & Information Security Management System].
https://www.pipc.go.kr/np/default/page.do?mCode=D040020000

Republic of Korea. (2025). *개인정보 보호법* [Personal Information Protection
Act] (Act No. 20897, art. 32-2). Korean Law Information Center.
https://www.law.go.kr/lsInfoR.do?chrClsCd=010202&efYd=20251002&lsiSeq=270351&urlMode=lsInfoP
