import { applyLocale, LOCALES } from './i18n.mjs';

const select = document.querySelector('#locale-select');
const initialLocale = document.documentElement.lang;
const locale = LOCALES.includes(initialLocale) ? initialLocale : 'en';

applyLocale(document, locale);
if (select) {
  select.value = locale;
  select.addEventListener('change', () => applyLocale(document, select.value));
}
