import './styles.css';

const meta = {
  title: 'GRC/Buyer workspace',
  parameters: {
    a11y: { test: 'error' },
    layout: 'fullscreen',
  },
};

export default meta;

function renderFixture({ mobile = false, accessDenied = false, stale = false } = {}) {
  const host = document.createElement('div');
  host.style.maxWidth = mobile ? '390px' : '1376px';
  host.style.margin = '0 auto';
  host.innerHTML = `
    <main class="workspace" aria-labelledby="story-workspace-title">
      <header class="workspace__header">
        <div><p class="eyebrow">Acme Korea · Compliance officer · Evidence review purpose</p><h1 id="story-workspace-title">Compliance workspace</h1><p class="lede">Understand what applies, what is proven, and what needs action before anything is shared.</p></div>
        <button class="button button--primary" type="button">Request evidence</button>
      </header>
      ${stale ? '<section class="notice notice--warning" aria-label="Evidence freshness"><strong>Evidence stale</strong><span>Review source versions before sharing.</span></section>' : ''}
      <section class="metric-grid" aria-label="Current posture">
        <article class="metric"><span>Applicable obligations</span><strong>18</strong><span class="status status--neutral">3 unknown</span></article>
        <article class="metric"><span>Controls tested</span><strong>12 / 16</strong><span class="status status--neutral">2 not assessed</span></article>
        <article class="metric"><span>Evidence fresh</span><strong>21 / 24</strong><span class="status status--warning">2 stale</span></article>
        <article class="metric"><span>Open deficiencies</span><strong>3</strong><span class="status status--danger">1 blocked</span></article>
      </section>
      <section class="panel" aria-labelledby="story-next-actions"><h2 id="story-next-actions">Next actions</h2><p>${accessDenied ? 'The external-auditor package is access denied for this purpose. Request authorization instead of exposing hidden fields.' : 'Review stale evidence, assign blocked work, then confirm unknown applicability.'}</p><button class="button ${accessDenied ? 'button--secondary' : 'button--primary'}" type="button">${accessDenied ? 'Request access' : 'Open evidence room'}</button></section>
    </main>`;
  return host;
}

export const ComplianceOfficerDesktop = { render: () => renderFixture() };
export const ComplianceOfficerMobile = { render: () => renderFixture({ mobile: true }), parameters: { viewport: { defaultViewport: 'mobile1' } } };
export const AccessDenied = { render: () => renderFixture({ accessDenied: true }) };
export const StaleEvidence = { render: () => renderFixture({ stale: true }) };
