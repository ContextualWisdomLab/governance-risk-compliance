import './styles.css';
import { initializeLocale } from './locale-controller.mjs';
import pageMarkup from './index.html?raw';

const meta = {
  title: 'GRC/Buyer workspace',
  parameters: {
    a11y: { test: 'error' },
    layout: 'fullscreen',
  },
};

export default meta;

function renderFixture({ mobile = false, accessDenied = true, stale = true, locale = 'en' } = {}) {
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
  initializeLocale(host, locale);
  return host;
}

export const ComplianceOfficerDesktop = { render: () => renderFixture() };
export const ComplianceOfficerMobile = {
  render: () => renderFixture({ mobile: true }),
  globals: { viewport: { value: 'mobile1', isRotated: false } },
};
export const AccessDenied = { render: () => renderFixture({ accessDenied: true, stale: false }) };
export const StaleEvidence = { render: () => renderFixture({ accessDenied: false, stale: true }) };
export const KoreanLocale = { render: () => renderFixture({ locale: 'ko' }) };
