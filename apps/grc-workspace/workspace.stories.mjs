import './styles.css';
import { expect, within } from 'storybook/test';
import { initializeLocale } from './locale-controller.mjs';
import pageMarkup from './index.html?raw';

const meta = {
  title: 'GRC/Officer workspace',
  tags: ['!autodocs'],
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

function storyRoot(context) {
  return context.canvas ?? within(context.canvasElement);
}

function workspaceHost(context) {
  return context.canvasElement.querySelector('.workspace')?.parentElement ?? context.canvasElement;
}

async function playAccessibility({ canvas, canvasElement }) {
  const root = storyRoot({ canvas, canvasElement });
  await expect(root.getByRole('main')).toHaveAttribute('aria-labelledby', 'workspace-title');
  await expect(root.getByRole('heading', { name: 'Compliance workspace' })).toBeVisible();
  const exactValues = root.getAllByRole('link', { name: 'View exact values' })[0];
  exactValues.focus();
  await expect(exactValues).toHaveFocus();
}

async function playTouchAndInteraction({ canvas, canvasElement, userEvent }) {
  const root = storyRoot({ canvas, canvasElement });
  const host = workspaceHost({ canvasElement });
  for (const action of host.querySelectorAll('.button')) {
    await expect(Number.parseFloat(getComputedStyle(action).minHeight)).toBeGreaterThanOrEqual(44);
  }
  await userEvent.click(root.getByRole('link', { name: 'Open evidence room' }));
  await expect(root.getByRole('status')).toBeVisible();
}

async function playPerformance({ canvasElement }) {
  const host = workspaceHost({ canvasElement });
  await expect(host.querySelectorAll('*').length).toBeLessThan(250);
  await expect(host.querySelectorAll('main')).toHaveLength(1);
  await expect(host.querySelectorAll('table')).toHaveLength(1);
  await expect(host.querySelectorAll('img, canvas, svg')).toHaveLength(0);
}

async function playStyleSelection({ canvas, canvasElement, userEvent }) {
  const root = storyRoot({ canvas, canvasElement });
  const localeSelect = root.getByLabelText(/Language|언어/);
  await userEvent.selectOptions(localeSelect, 'ko');
  await expect(root.getByRole('heading', { name: '컴플라이언스 워크스페이스' })).toBeVisible();
  await userEvent.selectOptions(localeSelect, 'en');
  await expect(root.getByRole('heading', { name: 'Compliance workspace' })).toBeVisible();
}

async function playLayoutAndResponsive({ canvasElement }) {
  const host = workspaceHost({ canvasElement });
  await expect(host.style.maxWidth).toBe('390px');
  await expect(host.querySelector('.workspace')).toBeTruthy();
}

async function playTypographyAndColor({ canvas, canvasElement }) {
  const root = storyRoot({ canvas, canvasElement });
  const stale = workspaceHost({ canvasElement }).querySelector('[data-state="stale"]');
  await expect(stale).toHaveTextContent(/stale/i);
  await expect(getComputedStyle(stale).color).not.toBe(getComputedStyle(root.getByRole('heading', { name: 'Compliance workspace' })).color);
  await expect(root.getByText('Prioritized by organization impact')).toBeVisible();
}

async function playAnimation({ canvasElement }) {
  const action = workspaceHost({ canvasElement }).querySelector('.button');
  await expect(getComputedStyle(action).animationName).toBe('none');
  await expect(Number.parseFloat(getComputedStyle(action).transitionDuration) || 0).toBeLessThan(0.05);
}

async function playFormsAndFeedback({ canvas, canvasElement, userEvent }) {
  const root = storyRoot({ canvas, canvasElement });
  await userEvent.click(root.getByRole('link', { name: 'Request access' }));
  await expect(root.getByRole('status')).toHaveTextContent('Connect the verified GRC workflow');
  await expect(root.getByText(/officer-facing state semantics/)).toBeVisible();
}

async function playNavigation({ canvas, canvasElement, userEvent }) {
  const root = storyRoot({ canvas, canvasElement });
  await userEvent.click(root.getByRole('link', { name: 'Review stale evidence' }));
  await expect(root.getByRole('heading', { name: 'Requirement → control → test → evidence' })).toBeVisible();
  await userEvent.click(root.getAllByRole('link', { name: 'View exact values' })[0]);
  await expect(root.getByRole('table')).toBeVisible();
}

async function playChartsAndData({ canvas, canvasElement }) {
  const root = storyRoot({ canvas, canvasElement });
  const table = root.getByRole('table');
  await expect(table).toHaveTextContent('Source version');
  await expect(table).toHaveTextContent('18 obligations');
  await expect(table).toHaveTextContent('Confirm applicability');
  await expect(table).toHaveTextContent('3 open deficiencies');
  await expect(root.getAllByRole('row')).toHaveLength(5);
}

async function playKoreanLocale({ canvas, canvasElement }) {
  const root = storyRoot({ canvas, canvasElement });
  await expect(root.getByRole('heading', { name: '컴플라이언스 워크스페이스' })).toBeVisible();
  await expect(root.getByLabelText('언어')).toHaveValue('ko');
}

export const ComplianceOfficerDesktop = {
  render: () => renderFixture(),
  play: playAccessibility,
};
export const ComplianceOfficerMobile = {
  render: () => renderFixture({ mobile: true }),
  globals: { viewport: { value: 'mobile1', isRotated: false } },
  play: playLayoutAndResponsive,
};
export const AccessDenied = {
  render: () => renderFixture({ accessDenied: true, stale: false }),
  play: playFormsAndFeedback,
};
export const StaleEvidence = {
  render: () => renderFixture({ accessDenied: false, stale: true }),
  play: playNavigation,
};
export const KoreanLocale = {
  render: () => renderFixture({ locale: 'ko' }),
  play: playKoreanLocale,
};
export const TouchAndInteraction = {
  render: () => renderFixture(),
  play: playTouchAndInteraction,
};
export const PerformanceBudget = {
  render: () => renderFixture(),
  play: playPerformance,
};
export const LocaleStyleSelection = {
  render: () => renderFixture(),
  play: playStyleSelection,
};
export const TypographyAndColor = {
  render: () => renderFixture(),
  play: playTypographyAndColor,
};
export const ReducedMotion = {
  render: () => renderFixture(),
  play: playAnimation,
};
export const ChartsAndData = {
  render: () => renderFixture(),
  play: playChartsAndData,
};
