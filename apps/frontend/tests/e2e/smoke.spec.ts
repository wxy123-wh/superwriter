import { expect, test } from '@playwright/test';

test('renders the routed frontend shell', async ({ page }) => {
  await page.goto('/');

  await expect(page).toHaveTitle(/Superwriter/i);
  await expect(page.getByRole('heading', { name: '资源管理器' })).toBeVisible();
  await expect(page.getByText('打开文件夹以开始编辑')).toBeVisible();
});
