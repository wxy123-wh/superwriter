import { expect, test } from '@playwright/test';

test('renders the routed frontend shell', async ({ page }) => {
  await page.goto('/');

  await expect(page).toHaveTitle(/Superwriter/i);
  await expect(page.getByRole('heading', { name: '节点写作助手' })).toBeVisible();
  await expect(page.getByRole('button', { name: '新建小说项目' })).toBeVisible();
});
