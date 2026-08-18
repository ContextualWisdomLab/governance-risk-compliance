# Governance, Risk & Compliance

ContextualWisdomLab GRC는 정책, 통제, 리스크, 증거, 컴플라이언스 감사 진실을 소유합니다. 다른 CWL 서비스는 통제·증거 계약만 소비하고, 이 진실은 가져가지 않습니다.

이 저장소는 잎(leaf)입니다. 단독으로 운영되고, [naruon](https://github.com/ContextualWisdomLab/naruon)과 [gyeot](https://github.com/ContextualWisdomLab/gyeot) 같은 구성 허브가 호출할 수 있습니다. 허브에 GRC를 접어 넣지 않습니다. 형제 저장소를 같이 받아 두지 않아도 됩니다.

통제가 비어 있으면 어떤 증거가 없는지 보고, 다음에 붙일 증거를 직접 열 수 있어야 합니다.

CSAP, SOC 2, ISMS-P는 이 제품의 통제입니다. SAST/Strix/CodeQL/Semgrep은 CWL Security 레인입니다. PII는 마스킹하지 않고, 목적 한정 인가·암호화·감사로 다룹니다.

## 제품 경계

| 이 저장소가 소유 | 다른 CWL 홈이 소유 (여기는 소비만) |
| --- | --- |
| 정책, 통제, 리스크, 증거, 컴플라이언스 감사 진실 | Orgmetra 고용, Keyverse 신원, AIS 장부, Billing 상업 과금 |
| | naruon·gyeot는 구성 허브로 이 잎을 호출할 수 있음. EA는 아키텍처를 소비만 함 |

## 지금 할 수 있는 일

채 증거가 없는 CSAP / SOC 2 / ISMS-P 통제를 보고, 증거를 붙이세요. 첫 제품 슬라이스가 올라오면 이 문단을 갱신합니다.

## 문서

- 제품·권한 경계, 통제·증거 모델, 한국 제품 통제, 미구현 범위: [`docs/adr/`](docs/adr/README.md)
- 확인된 공식 출처: [`docs/REFERENCES.md`](docs/REFERENCES.md)

의사결정 기록은 초안이며 최종이 아닙니다.
