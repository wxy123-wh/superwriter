import { expect, test } from '@playwright/test';

test('manifest route renders without NovelManifestProvider error', async ({ page }) => {
  const errors: string[] = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });

  await page.goto('/manifest');

  // Should not have the NovelManifestProvider error
  const hasProviderError = errors.some(e => e.includes('NovelManifestProvider'));
  expect(hasProviderError).toBe(false);

  // Should show manifest tabs
  await expect(page.getByRole('button', { name: '角色 (0)' })).toBeVisible();
  await expect(page.getByRole('button', { name: '地点 (0)' })).toBeVisible();
});