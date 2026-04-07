import { expect, test } from '@playwright/test';

test('renders the frontend baseline shell', async ({ page }) => {
  await page.goto('/');

  await expect(page).toHaveTitle('Superwriter Frontend');
  await expect(page.getByText('Superwriter frontend baseline')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'React workspace is ready for route migration.' })).toBeVisible();
});
