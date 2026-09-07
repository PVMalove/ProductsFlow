import { test, expect } from '@playwright/test';

test('has title', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/Create Next App/);
});

test('proxies API to Gateway', async ({ request }) => {
  const response = await request.get('/api/v1/products');
  expect(response.status()).not.toBe(404);
});
