import { expect, test } from '@playwright/test';

test('keyboard actions expose exact values and truthful preview boundaries', async ({ page }) => {
  await page.goto('/apps/grc-workspace/index.html');

  await expect(page.getByRole('heading', { name: 'Compliance workspace' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'View exact values' }).first()).toBeVisible();
  await expect(page.getByRole('status')).toContainText('Connect the verified GRC workflow');
  await expect(page.getByText('Prioritized by organization impact')).toBeVisible();
  await expect(page.getByText('officer-facing state semantics')).toBeVisible();
  await expect(page.getByText(/buyer/i)).toHaveCount(0);

  const metricStates = async (name) => {
    const card = page.locator('.metric', { hasText: name });
    return (await card.locator('[data-i18n^="status."]').allInnerTexts()).map((text) => text.trim());
  };
  expect(await metricStates('Controls tested')).toEqual(['2 not assessed', '2 scheduled']);
  expect(await metricStates('Evidence fresh')).toEqual(['2 stale', '1 awaiting collection']);
  await expect(page.getByRole('row', { name: /Controls tested/ })).toContainText(
    '2 not assessed, 2 scheduled',
  );
  await expect(page.getByRole('row', { name: /Evidence fresh/ })).toContainText(
    '2 stale, 1 awaiting collection',
  );

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
  const table = page.getByRole('table');
  await expect(table).toBeVisible();

  await expect(page.getByText('Period: 2026 Q3')).toBeVisible();
  for (const column of ['Measure', 'Value', 'Status', 'Source version', 'Limitation', 'Next action']) {
    await expect(page.getByRole('columnheader', { name: column })).toBeVisible();
  }
  await expect(table).toContainText('control-test-2026-q3');
  await expect(table).toContainText('evidence-index-2026-08-20');
  await expect(table).toContainText('No effectiveness claim is made for unassessed or scheduled controls.');
  await expect(table).toContainText('Schedule tests');

  const scrollRegion = page.locator('.table-scroll');
  await expect(scrollRegion).toHaveCSS('overflow-x', 'visible');
  const headers = page.getByRole('columnheader');
  await expect(headers).toHaveCount(6);
  for (const header of await headers.all()) {
    const box = await header.boundingBox();
    expect(box.width).toBeGreaterThan(0);
    expect(box.x).toBeGreaterThanOrEqual(0);
  }
  const bodyCells = page.locator('table tbody tr').first().locator('th, td');
  await expect(bodyCells).toHaveCount(6);
  for (const cell of await bodyCells.all()) {
    const text = (await cell.innerText()).trim();
    expect(text.length).toBeGreaterThan(0);
    expect(await cell.evaluate((node) => node.scrollWidth > node.clientWidth + 1)).toBe(false);
  }
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
  await page.goto('/storybook-static/iframe.html?id=grc-officer-workspace--korean-locale&viewMode=story');

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

test('reduced motion emulation clamps every transition and animation', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/apps/grc-workspace/index.html');

  for (const action of await page.locator('.button').all()) {
    const styles = await action.evaluate((node) => {
      const computed = getComputedStyle(node);
      return {
        animationName: computed.animationName,
        animationDuration: Number.parseFloat(computed.animationDuration) || 0,
        transitionDuration: Math.max(
          ...computed.transitionDuration.split(',').map((value) => Number.parseFloat(value) || 0),
        ),
      };
    });
    expect(styles.animationDuration).toBeLessThanOrEqual(0.02);
    expect(styles.transitionDuration).toBeLessThanOrEqual(0.02);
  }
});

test('reduced motion keeps the exact-values table reachable by keyboard', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/apps/grc-workspace/index.html');

  const exactValues = page.getByRole('link', { name: 'View exact values' }).first();
  await exactValues.focus();
  await expect(exactValues).toBeFocused();
  await exactValues.press('Enter');
  await expect(page).toHaveURL(/#exact-title$/);
  await expect(page.getByRole('table')).toContainText('Source version');
});
