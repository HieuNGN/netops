import { test, expect } from '@playwright/test';

test.describe('Smoke Tests', () => {
  test('dashboard loads with title and navigation', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h1:has-text("Dashboard")')).toBeVisible();
    await expect(page.locator('nav')).toBeVisible();
  });

  test('navigation to Devices page works', async ({ page }) => {
    await page.goto('/');
    await page.locator('nav a[href="/devices"], nav button:has-text("Devices")').first().click();
    await expect(page.locator('h1:has-text("Devices")')).toBeVisible();
  });

  test('navigation to Topology page works', async ({ page }) => {
    await page.goto('/');
    await page.locator('nav a[href="/topology"], nav button:has-text("Topology")').first().click();
    await expect(page.locator('h1:has-text("Topology")')).toBeVisible();
  });

  test('navigation to Alerts page works', async ({ page }) => {
    await page.goto('/');
    await page.locator('nav a[href="/alerts"], nav button:has-text("Alerts")').first().click();
    await expect(page.locator('h1:has-text("Alerts")')).toBeVisible();
  });

  test('dark mode toggle switches data-theme', async ({ page }) => {
    await page.goto('/');
    const html = page.locator('html');
    // Ensure we start in light mode by explicitly setting it via page.evaluate
    await page.evaluate(() => {
      localStorage.setItem('theme', 'light');
      document.documentElement.classList.remove('dark');
      document.documentElement.setAttribute('data-theme', 'light');
    });
    await page.reload();
    await expect(html).toHaveAttribute('data-theme', 'light');

    // Click the theme toggle button
    await page.locator('button:has-text("Toggle theme")').first().click();
    await expect(html).toHaveAttribute('data-theme', 'dark');
  });
});
