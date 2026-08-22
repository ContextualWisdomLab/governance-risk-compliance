import { expect, test } from '@playwright/test';

test('keyboard actions expose exact values and truthful preview boundaries', async ({ page }) => {
  await page.goto('/apps/grc-workspace/index.html');

  await expect(page.getByRole('heading', { name: 'Compliance workspace' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'View exact values' }).first()).toBeVisible();
  await expect(page.getByRole('status')).toContainText('Connect the verified GRC workflow');

  const exactValues = page.getByRole('link', { name: 'View exact values' }).first();
  await exactValues.focus();
  await expect(exactValues).toBeFocused();
  await exactValues.press('Enter');
  await expect(page).toHaveURL(/#exact-title$/);
  await expect(page.getByRole('table')).toContainText('Source version');
  await expect(page.getByRole('table')).toContainText('Confirm applicability');

  const requestAccess = page.getByRole('link', { name: 'Request access' });
  await requestAccess.focus();
  await expect(requestAccess).toBeFocused();
  await requestAccess.press('Enter');
  await expect(page).toHaveURL(/#action-feedback$/);
});

test('mobile and print fallbacks keep the page usable without false overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/apps/grc-workspace/index.html');
  expect(await page.locator('body').evaluate((node) => node.scrollWidth <= window.innerWidth)).toBe(true);
  expect(await page.locator('.table-scroll').evaluate((node) => node.scrollWidth > node.clientWidth)).toBe(true);

  for (const action of await page.locator('.button').all()) {
    await expect(action).toHaveCSS('min-height', '44px');
  }

  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('.button').first()).toBeHidden();
  await expect(page.getByRole('table')).toBeVisible();
});

test('locale switching translates labels without changing state identifiers', async ({ page }) => {
  await page.goto('/apps/grc-workspace/index.html');

  await expect(
    page.getByRole('region', { name: /Exact values Exact compliance posture values/ }),
  ).toBeVisible();

  await page.locator('#locale-select').selectOption('ko');
  await expect(page.locator('html')).toHaveAttribute('lang', 'ko');
  await expect(page.getByRole('heading', { name: '컴플라이언스 워크스페이스' })).toBeVisible();
  await expect(page.getByRole('link', { name: '증적 요청', exact: true })).toBeVisible();
  await expect(page.locator('[data-state="unknown"]').first()).toHaveText('미확정 3건');
  await expect(page.getByRole('columnheader', { name: '측정 항목' })).toBeVisible();
  await expect(
    page.getByRole('region', { name: /정확한 값 출처, 제한사항, 다음 조치를 포함한 정확한 컴플라이언스 상태 값/ }),
  ).toBeVisible();

  await page.locator('#locale-select').selectOption('en');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('heading', { name: 'Compliance workspace' })).toBeVisible();
  await expect(page.locator('[data-state="access_denied"]')).toHaveText('Access denied');
  await expect(
    page.getByRole('region', { name: /Exact values Exact compliance posture values/ }),
  ).toBeVisible();
});

test('Storybook locale story initializes and switches the real workspace selector', async ({ page }) => {
  await page.goto('/storybook-static/iframe.html?id=grc-buyer-workspace--korean-locale&viewMode=story');

  const localeSelect = page.locator('#locale-select');
  await expect(localeSelect).toHaveValue('ko');
  await expect(page.getByRole('heading', { name: '컴플라이언스 워크스페이스' })).toBeVisible();

  await localeSelect.selectOption('en');
  await expect(localeSelect).toHaveValue('en');
  await expect(page.locator('[data-locale="en"]')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Compliance workspace' })).toBeVisible();

  await localeSelect.selectOption('ko');
  await expect(page.locator('[data-locale="ko"]')).toBeVisible();
  await expect(page.getByRole('heading', { name: '컴플라이언스 워크스페이스' })).toBeVisible();
});
