import './styles.css';
import { applyLocale } from './i18n.mjs';
import pageMarkup from './index.html?raw';

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
  host.style.width = '100%';
  host.style.maxWidth = mobile ? '390px' : '1376px';
  host.style.margin = '0 auto';
  const parsedPage = new DOMParser().parseFromString(pageMarkup, 'text/html');
  const workspace = parsedPage.querySelector('main.workspace');
  if (!workspace) throw new Error('Workspace markup is missing from index.html');
  host.append(workspace);
  const freshnessNotice = workspace.querySelector('.notice');
  if (freshnessNotice) freshnessNotice.hidden = !stale;
  const accessDeniedRow = workspace.querySelector('[data-state="access_denied"]')?.closest('li');
  if (accessDeniedRow) accessDeniedRow.hidden = !accessDenied;
  applyLocale(host, locale);
  return host;
}

export const ComplianceOfficerDesktop = { render: () => renderFixture() };
export const ComplianceOfficerMobile = { render: () => renderFixture({ mobile: true }), parameters: { viewport: { defaultViewport: 'mobile1' } } };
export const AccessDenied = { render: () => renderFixture({ accessDenied: true }) };
export const StaleEvidence = { render: () => renderFixture({ stale: true }) };
export const KoreanLocale = { render: () => renderFixture({ locale: 'ko' }) };
