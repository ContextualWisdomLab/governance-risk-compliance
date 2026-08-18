"""Official first-slice control catalog seeds and listing."""

from __future__ import annotations

from enum import StrEnum
from typing import assert_never
from uuid import uuid4

from sqlalchemy.orm import Session

from cwl_grc.models import ControlFramework, ControlItem


class FrameworkCode(StrEnum):
    """Catalog editions seeded in this slice."""

    SOC2_TSC_2017 = "soc2_tsc_2017"
    ISMS_P_2023 = "isms_p_2023"
    CSAP_2026 = "csap_2026"
    ISO27001_2022 = "iso27001_2022"
    NIST_SP_800_53_R5 = "nist_sp_800_53_r5"
    COSO_IC_2013 = "coso_ic_2013"
    COSO_ERM_2017 = "coso_erm_2017"


def framework_label(code: FrameworkCode) -> str:
    """Return the officer-facing catalog label."""
    match code:
        case FrameworkCode.SOC2_TSC_2017:
            return "AICPA SOC 2 Trust Services Criteria (2017, 2022 points of focus)"
        case FrameworkCode.ISMS_P_2023:
            return "KISA ISMS-P certification criteria (2023.11)"
        case FrameworkCode.CSAP_2026:
            return "Korea CSAP cloud security certification (2026 commentary)"
        case FrameworkCode.ISO27001_2022:
            return "ISO/IEC 27001:2022 Annex A"
        case FrameworkCode.NIST_SP_800_53_R5:
            return "NIST SP 800-53 Revision 5"
        case FrameworkCode.COSO_IC_2013:
            return "COSO Internal Control — Integrated Framework (2013)"
        case FrameworkCode.COSO_ERM_2017:
            return "COSO Enterprise Risk Management (2017)"
        case _ as unreachable:  # pragma: no cover
            assert_never(unreachable)


def framework_source_url(code: FrameworkCode) -> str:
    """Return the official source URL cited for a catalog edition."""
    match code:
        case FrameworkCode.SOC2_TSC_2017:
            return (
                "https://www.aicpa-cima.com/resources/download/"
                "2017-trust-services-criteria-with-revised-points-of-focus-2022"
            )
        case FrameworkCode.ISMS_P_2023:
            return (
                "https://isms.kisa.or.kr/main/ispims/notice/"
                "?boardId=bbs_0000000000000014&mode=view&cntId=21"
            )
        case FrameworkCode.CSAP_2026:
            return "https://isms.kisa.or.kr/main/csap/intro/"
        case FrameworkCode.ISO27001_2022:
            return "https://www.iso.org/standard/27001"
        case FrameworkCode.NIST_SP_800_53_R5:
            return "https://doi.org/10.6028/NIST.SP.800-53r5"
        case FrameworkCode.COSO_IC_2013:
            return "https://www.coso.org/guidance-on-ic"
        case FrameworkCode.COSO_ERM_2017:
            return "https://www.coso.org/_files/ugd/3059fc_61ea5985b03c4293960642fdce408eaa.pdf"
        case _ as unreachable:  # pragma: no cover
            assert_never(unreachable)


def _seed_rows() -> list[tuple[FrameworkCode, str, str, str, str]]:
    """Return official first-slice control rows: code, edition, id, title, statement."""
    return [
        (
            FrameworkCode.SOC2_TSC_2017,
            "TSP 100 2017/2022",
            "CC1.1",
            "COSO Principle 1",
            "The entity demonstrates a commitment to integrity and ethical values.",
        ),
        (
            FrameworkCode.SOC2_TSC_2017,
            "TSP 100 2017/2022",
            "CC5.1",
            "COSO Principle 10",
            (
                "The entity selects and develops control activities that contribute to "
                "the mitigation of risks to the achievement of objectives to acceptable levels."
            ),
        ),
        (
            FrameworkCode.SOC2_TSC_2017,
            "TSP 100 2017/2022",
            "CC6.1",
            "Logical access security",
            (
                "The entity implements logical access security software, infrastructure, "
                "and architectures over protected information assets to protect them from "
                "security events to meet the entity's objectives."
            ),
        ),
        (
            FrameworkCode.SOC2_TSC_2017,
            "TSP 100 2017/2022",
            "CC6.2",
            "User registration and credential removal",
            (
                "Prior to issuing system credentials and granting system access, the entity "
                "registers and authorizes new internal and external users whose access is "
                "administered by the entity."
            ),
        ),
        (
            FrameworkCode.SOC2_TSC_2017,
            "TSP 100 2017/2022",
            "CC6.3",
            "Access authorization and least privilege",
            (
                "The entity authorizes, modifies, or removes access to data, software, "
                "functions, and other protected information assets based on roles, "
                "responsibilities, or the system design and changes."
            ),
        ),
        (
            FrameworkCode.SOC2_TSC_2017,
            "TSP 100 2017/2022",
            "CC7.2",
            "System monitoring for anomalies",
            (
                "The entity monitors system components and the operation of those components "
                "for anomalies that are indicative of malicious acts, natural disasters, and errors."
            ),
        ),
        (
            FrameworkCode.SOC2_TSC_2017,
            "TSP 100 2017/2022",
            "A1.2",
            "Recovery infrastructure",
            (
                "The entity authorizes, designs, develops or acquires, implements, operates, "
                "approves, maintains, and monitors environmental protections, software, data "
                "backup processes, and recovery infrastructure to meet its objectives."
            ),
        ),
        (
            FrameworkCode.SOC2_TSC_2017,
            "TSP 100 2017/2022",
            "C1.1",
            "Confidential information inventory",
            (
                "The entity identifies and maintains confidential information to meet the "
                "entity’s objectives related to confidentiality."
            ),
        ),
        (
            FrameworkCode.SOC2_TSC_2017,
            "TSP 100 2017/2022",
            "P3.1",
            "Personal information collection",
            "Personal information is collected consistent with the entity’s objectives related to privacy.",
        ),
        (
            FrameworkCode.ISMS_P_2023,
            "2023.11",
            "1.1.1",
            "경영진의 참여",
            "최고경영자는 관리체계 수립과 운영 전반에 경영진이 참여하도록 보고 및 의사결정 체계를 운영하여야 한다.",
        ),
        (
            FrameworkCode.ISMS_P_2023,
            "2023.11",
            "1.1.5",
            "정책 수립",
            "정보보호와 개인정보보호 정책 및 시행문서를 수립하고 경영진 승인을 받아 전달하여야 한다.",
        ),
        (
            FrameworkCode.ISMS_P_2023,
            "2023.11",
            "2.5.1",
            "사용자 계정 관리",
            "사용자 등록·해지 및 접근권한 부여·변경·말소 절차를 수립·이행하고 최소 권한만 부여하여야 한다.",
        ),
        (
            FrameworkCode.ISMS_P_2023,
            "2023.11",
            "2.5.3",
            "사용자 인증",
            "정보시스템 접근은 안전한 인증절차와 필요 시 강화된 인증방식을 적용하여야 한다.",
        ),
        (
            FrameworkCode.ISMS_P_2023,
            "2023.11",
            "2.5.6",
            "접근권한 검토",
            "계정 및 접근권한의 부여·변경·삭제 이력을 남기고 주기적으로 적정성을 점검하여야 한다.",
        ),
        (
            FrameworkCode.ISMS_P_2023,
            "2023.11",
            "2.7.1",
            "암호정책 적용",
            "개인정보 및 주요정보 암호화 시 법적 요구사항과 안전한 암호 강도를 적용하여야 한다.",
        ),
        (
            FrameworkCode.ISMS_P_2023,
            "2023.11",
            "2.9.4",
            "로그 및 접속기록 관리",
            "로그와 개인정보처리시스템 접속기록을 안전하게 보관하고 법적 보관기간을 준수하여야 한다.",
        ),
        (
            FrameworkCode.ISMS_P_2023,
            "2023.11",
            "3.1.1",
            "개인정보 수집∙이용",
            "개인정보는 적법하고 정당하게 수집·이용하여야 하며 동의가 필요한 경우 적법한 동의를 받아야 한다.",
        ),
        (
            FrameworkCode.ISMS_P_2023,
            "2023.11",
            "3.1.2",
            "개인정보 수집 제한",
            "처리 목적에 필요한 최소한의 개인정보만 수집하여야 하며 선택 동의 거부를 이유로 서비스를 거부하지 않아야 한다.",
        ),
        (
            FrameworkCode.CSAP_2026,
            "2026.07",
            "1.1.1",
            "정보보호 정책 수립",
            "클라우드서비스 제공자는 정보보호 정책을 수립·문서화하고 최고경영자 승인을 받아야 한다.",
        ),
        (
            FrameworkCode.CSAP_2026,
            "2026.07",
            "10.1.1",
            "접근통제 정책 수립",
            "클라우드 자원에 대한 접근통제 정책을 수립하고 업무 필요에 따라 적용하여야 한다.",
        ),
        (
            FrameworkCode.CSAP_2026,
            "2026.07",
            "10.2.1",
            "사용자 등록 및 권한 부여",
            "공식적인 사용자 등록·해지 절차를 두고 접근권한을 최소한으로 부여하여야 한다.",
        ),
        (
            FrameworkCode.CSAP_2026,
            "2026.07",
            "10.2.2",
            "관리자 및 특수권한 관리",
            "특수 목적 계정과 권한을 식별하고 별도로 통제하여야 한다.",
        ),
        (
            FrameworkCode.CSAP_2026,
            "2026.07",
            "10.3.1",
            "사용자 식별",
            "사용자를 유일하게 구분할 수 있는 식별자를 할당하고 추측 가능한 식별자 사용을 제한하여야 한다.",
        ),
        (
            FrameworkCode.CSAP_2026,
            "2026.07",
            "10.3.2",
            "사용자 인증",
            "클라우드서비스 접근을 안전한 사용자 인증 절차로 통제하여야 한다.",
        ),
        (
            FrameworkCode.CSAP_2026,
            "2026.07",
            "12.3.1",
            "암호 정책 수립",
            "전송 및 저장 데이터에 대한 암호화 대상, 암호 강도, 키 관리 정책을 수립하여야 한다.",
        ),
        (
            FrameworkCode.CSAP_2026,
            "2026.07",
            "12.3.2",
            "암호키 관리",
            "암호키의 생성·이용·보관·배포·파기 절차를 수립하고 안전하게 보관하여야 한다.",
        ),
        (
            FrameworkCode.ISO27001_2022,
            "2022",
            "A.5.1",
            "Policies for information security",
            "Information security policy and topic-specific policies shall be defined, approved, published, and reviewed.",
        ),
        (
            FrameworkCode.ISO27001_2022,
            "2022",
            "A.5.15",
            "Access control",
            "Rules to control physical and logical access to information and other associated assets shall be established.",
        ),
        (
            FrameworkCode.ISO27001_2022,
            "2022",
            "A.5.18",
            "Access rights",
            "Access rights to information and other associated assets shall be provisioned, reviewed, modified and removed.",
        ),
        (
            FrameworkCode.ISO27001_2022,
            "2022",
            "A.8.2",
            "Privileged access rights",
            "The allocation and use of privileged access rights shall be restricted and managed.",
        ),
        (
            FrameworkCode.ISO27001_2022,
            "2022",
            "A.8.5",
            "Secure authentication",
            "Secure authentication technologies and procedures shall be implemented based on access restrictions and the topic-specific policy on access control.",
        ),
        (
            FrameworkCode.ISO27001_2022,
            "2022",
            "A.8.15",
            "Logging",
            "Logs that record activities, exceptions, faults and other relevant events shall be produced, stored, protected and analysed.",
        ),
        (
            FrameworkCode.ISO27001_2022,
            "2022",
            "A.8.24",
            "Use of cryptography",
            "Rules for the effective use of cryptography, including cryptographic key management, shall be defined and implemented.",
        ),
        (
            FrameworkCode.NIST_SP_800_53_R5,
            "Rev. 5",
            "AC-2",
            "Account Management",
            "The organization manages system accounts, including establishing, activating, modifying, disabling, and removing accounts.",
        ),
        (
            FrameworkCode.NIST_SP_800_53_R5,
            "Rev. 5",
            "AC-3",
            "Access Enforcement",
            "The system enforces approved authorizations for logical access to information and system resources.",
        ),
        (
            FrameworkCode.NIST_SP_800_53_R5,
            "Rev. 5",
            "AU-2",
            "Event Logging",
            "The organization determines that the system is capable of auditing selected events and specifies those events.",
        ),
        (
            FrameworkCode.NIST_SP_800_53_R5,
            "Rev. 5",
            "IA-2",
            "Identification and Authentication (Organizational Users)",
            "The system uniquely identifies and authenticates organizational users and associated processes.",
        ),
        (
            FrameworkCode.NIST_SP_800_53_R5,
            "Rev. 5",
            "CM-6",
            "Configuration Settings",
            "The organization establishes, documents, and implements configuration settings for information technology products.",
        ),
        (
            FrameworkCode.NIST_SP_800_53_R5,
            "Rev. 5",
            "SC-12",
            "Cryptographic Key Establishment and Management",
            "The organization establishes and manages cryptographic keys when cryptography is employed.",
        ),
        (
            FrameworkCode.NIST_SP_800_53_R5,
            "Rev. 5",
            "SI-4",
            "System Monitoring",
            "The organization monitors the system to detect attacks and indicators of potential attacks.",
        ),
        (
            FrameworkCode.COSO_IC_2013,
            "2013",
            "Principle 1",
            "Demonstrates commitment to integrity and ethical values",
            "The organization demonstrates a commitment to integrity and ethical values.",
        ),
        (
            FrameworkCode.COSO_IC_2013,
            "2013",
            "Principle 7",
            "Identifies and analyzes risk",
            "The organization identifies risks to the achievement of its objectives and analyzes risks as a basis for determining how the risks should be managed.",
        ),
        (
            FrameworkCode.COSO_IC_2013,
            "2013",
            "Principle 10",
            "Selects and develops control activities",
            "The organization selects and develops control activities that contribute to the mitigation of risks to the achievement of objectives to acceptable levels.",
        ),
        (
            FrameworkCode.COSO_IC_2013,
            "2013",
            "Principle 13",
            "Uses relevant information",
            "The organization obtains or generates and uses relevant, quality information to support the functioning of internal control.",
        ),
        (
            FrameworkCode.COSO_IC_2013,
            "2013",
            "Principle 16",
            "Conducts ongoing and/or separate evaluations",
            "The organization selects, develops, and performs ongoing and/or separate evaluations to ascertain whether the components of internal control are present and functioning.",
        ),
        (
            FrameworkCode.COSO_ERM_2017,
            "2017",
            "Principle 1",
            "Exercises board risk oversight",
            "The board of directors exercises risk oversight.",
        ),
        (
            FrameworkCode.COSO_ERM_2017,
            "2017",
            "Principle 10",
            "Identifies risk",
            "The organization identifies risk that impacts the performance of strategy and business objectives.",
        ),
        (
            FrameworkCode.COSO_ERM_2017,
            "2017",
            "Principle 13",
            "Implements risk responses",
            "The organization identifies and selects risk responses.",
        ),
        (
            FrameworkCode.COSO_ERM_2017,
            "2017",
            "Principle 20",
            "Reports on risk, culture, and performance",
            "The organization reports on risk, culture, and performance at multiple levels and across the entity.",
        ),
    ]


def seed_control_catalog(session: Session) -> None:
    """Insert official first-slice controls once per catalog edition."""
    for code, edition, identifier, title, statement in _seed_rows():
        framework = session.get(ControlFramework, code.value)
        if framework is None:
            framework = ControlFramework(
                framework_key=code.value,
                official_title=framework_label(code),
                edition_label=edition,
                source_url=framework_source_url(code),
            )
            session.add(framework)
            session.flush()
        exists = (
            session.query(ControlItem)
            .filter_by(framework_key=code.value, catalog_identifier=identifier)
            .one_or_none()
        )
        if exists is not None:
            continue
        session.add(
            ControlItem(
                control_item_id=uuid4().hex,
                framework_key=code.value,
                catalog_identifier=identifier,
                control_title=title,
                control_statement=statement,
            )
        )


def list_control_items(session: Session, framework: FrameworkCode | None) -> list[ControlItem]:
    """List catalog rows, optionally limited to one official edition."""
    query = session.query(ControlItem).order_by(ControlItem.framework_key, ControlItem.catalog_identifier)
    if framework is not None:
        query = query.filter(ControlItem.framework_key == framework.value)
    return list(query.all())


def get_control_item(session: Session, framework: FrameworkCode, catalog_identifier: str) -> ControlItem | None:
    """Return one official control row or None."""
    return (
        session.query(ControlItem)
        .filter_by(framework_key=framework.value, catalog_identifier=catalog_identifier)
        .one_or_none()
    )
