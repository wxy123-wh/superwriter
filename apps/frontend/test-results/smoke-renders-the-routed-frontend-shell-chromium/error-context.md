# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: smoke.spec.ts >> renders the routed frontend shell
- Location: tests\e2e\smoke.spec.ts:3:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByRole('heading', { name: '节点写作助手' })
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for getByRole('heading', { name: '节点写作助手' })

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - paragraph [ref=e4]: Contract drift
  - heading "接口契约与前端预期不一致" [level=2] [ref=e5]
  - paragraph [ref=e6]: /api/startup
  - paragraph [ref=e7]: Expected JSON from /api/startup
```

# Test source

```ts
  1  | import { expect, test } from '@playwright/test';
  2  | 
  3  | test('renders the routed frontend shell', async ({ page }) => {
  4  |   await page.goto('/');
  5  | 
  6  |   await expect(page).toHaveTitle(/Superwriter/i);
> 7  |   await expect(page.getByRole('heading', { name: '节点写作助手' })).toBeVisible();
     |                                                               ^ Error: expect(locator).toBeVisible() failed
  8  |   await expect(page.getByRole('button', { name: '新建小说项目' })).toBeVisible();
  9  | });
  10 | 
```