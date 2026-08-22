import { applyLocale, LOCALES } from './i18n.mjs';

/**
 * Apply an initial locale and keep the workspace selector synchronized with it.
 *
 * The same controller is used by the shipped page and Storybook so neither
 * surface can drift into displaying translated content with a stale selector.
 *
 * @param {Document|HTMLElement} root document or detached Storybook host
 * @param {string} initialLocale requested initial locale
 * @returns {string} normalized active locale
 */
export function initializeLocale(root, initialLocale = 'en') {
  const requestedLocale = LOCALES.includes(initialLocale) ? initialLocale : 'en';
  const activeLocale = applyLocale(root, requestedLocale);
  const select = root.querySelector('#locale-select');
  if (!select) return activeLocale;

  select.value = activeLocale;
  select.addEventListener('change', () => {
    const nextLocale = applyLocale(root, select.value);
    select.value = nextLocale;
  });
  return activeLocale;
}
