import './styles.css';
import { applyLocale } from './i18n.mjs';

const meta = {
  title: 'GRC/Buyer workspace',
  parameters: {
    a11y: { test: 'error' },
    layout: 'fullscreen',
  },
};

export default meta;

function renderFixture({ mobile = false, accessDenied = false, stale = false, locale = 'en' } = {}) {
  const host = document.createElement('div');
  host.style.maxWidth = mobile ? '390px' : '1376px';
  host.style.margin = '0 auto';
  host.innerHTML = `
    <main class="workspace" aria-labelledby="story-workspace-title">
      <header class="workspace__header">
        <div><p class="eyebrow" data-i18n="header.context">Acme Korea · Compliance officer · Evidence review purpose</p><h1 id="story-workspace-title" data-i18n="header.title">Compliance workspace</h1><p class="lede" data-i18n="header.lede">Understand what applies, what is proven, and what needs action before anything is shared.</p></div>
        <a class="button button--primary" href="#story-feedback" data-i18n="action.requestEvidence">Request evidence</a>
      </header>
      ${stale ? '<section class="notice notice--warning" aria-label="Evidence freshness"><strong>Evidence stale</strong><span>Review source versions before sharing.</span></section>' : ''}
      <section class="metric-grid" aria-label="Current posture">
        <article class="metric"><span data-i18n="metric.applicable">Applicable obligations</span><strong>18</strong><span class="status status--neutral" data-i18n="status.unknown3">3 unknown</span></article>
        <article class="metric"><span data-i18n="metric.controlsTested">Controls tested</span><strong>12 / 16</strong><span class="status status--neutral" data-i18n="status.notAssessed2">2 not assessed</span></article>
        <article class="metric"><span data-i18n="metric.evidenceFresh">Evidence fresh</span><strong>21 / 24</strong><span class="status status--warning" data-i18n="status.stale2">2 stale</span></article>
        <article class="metric"><span data-i18n="metric.deficiencies">Open deficiencies</span><strong>3</strong><span class="status status--danger" data-i18n="status.blocked1">1 blocked</span></article>
      </section>
      <section class="panel" aria-labelledby="story-next-actions"><h2 id="story-next-actions" data-i18n="actions.title">Next actions</h2><p data-i18n="${accessDenied ? 'accessDenied.description' : 'actions.description'}">${accessDenied ? 'The external-auditor package is access denied for this purpose. Request authorization instead of exposing hidden fields.' : 'Review stale evidence, assign blocked work, then confirm unknown applicability.'}</p><a class="button ${accessDenied ? 'button--secondary' : 'button--primary'}" href="#story-feedback" data-i18n="${accessDenied ? 'action.requestAccess' : 'action.openEvidenceRoom'}">${accessDenied ? 'Request access' : 'Open evidence room'}</a></section>
      <p id="story-feedback" class="limitation" role="status"><strong data-i18n="feedback.preview">Preview action:</strong> <span data-i18n="feedback.connect">Connect the verified GRC workflow before requesting or sharing evidence.</span></p>
    </main>`;
  applyLocale(host, locale);
  return host;
}

export const ComplianceOfficerDesktop = { render: () => renderFixture() };
export const ComplianceOfficerMobile = { render: () => renderFixture({ mobile: true }), parameters: { viewport: { defaultViewport: 'mobile1' } } };
export const AccessDenied = { render: () => renderFixture({ accessDenied: true }) };
export const StaleEvidence = { render: () => renderFixture({ stale: true }) };
export const KoreanLocale = { render: () => renderFixture({ locale: 'ko' }) };
