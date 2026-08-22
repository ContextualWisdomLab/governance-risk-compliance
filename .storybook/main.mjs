/** @type { import('@storybook/web-components-vite').StorybookConfig } */
const config = {
  stories: ['../apps/grc-workspace/**/*.stories.mjs'],
  framework: '@storybook/web-components-vite',
  addons: ['@storybook/addon-a11y'],
};

export default config;
