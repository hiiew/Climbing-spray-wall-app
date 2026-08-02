/**
 * upload_and_generate_route.spec.ts
 * Playwright E2E — Full user journey: upload → scan → generate → save → share
 *
 * Prerequisites:
 *   - Laravel app running at http://localhost:8000
 *   - CV service running at http://localhost:8001 (or mocked)
 *   - Test user seeded (see fixtures below)
 *
 * Run:
 *   npx playwright test e2e/upload_and_generate_route.spec.ts
 */

import { test, expect, type Page, type BrowserContext } from '@playwright/test';
import path from 'path';
import fs from 'fs';

// ---------------------------------------------------------------------------
// Test Fixtures & Helpers
// ---------------------------------------------------------------------------

const BASE_URL     = process.env.APP_URL ?? 'http://localhost:8000';
const TEST_EMAIL   = process.env.TEST_EMAIL ?? 'e2e@spraywall.test';
const TEST_PASS    = process.env.TEST_PASS  ?? 'E2ePassword!1';

/** Path to a synthetic test wall image (1200×1200 JPEG) */
const TEST_IMAGE_PATH = path.join(__dirname, 'fixtures', 'test_wall_1200x1200.jpg');

async function loginAs(page: Page, email: string, password: string): Promise<void> {
  await page.goto(`${BASE_URL}/login`);
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole('button', { name: /sign in|log in/i }).click();
  await page.waitForURL(`${BASE_URL}/dashboard`, { timeout: 10_000 });
}

async function waitForScanComplete(page: Page, timeout = 90_000): Promise<void> {
  // Either the toast fires or the status badge changes
  await Promise.race([
    page.waitForSelector('[data-testid="status-badge"][data-status="scan_complete"]', { timeout }),
    page.waitForSelector('text=holds detected', { timeout }),
  ]);
}

// ---------------------------------------------------------------------------
// Test: Full Happy Path
// ---------------------------------------------------------------------------

test.describe('Wall Upload → Hold Scan → Route Generate → Save → Share', () => {

  test.beforeEach(async ({ page }) => {
    await loginAs(page, TEST_EMAIL, TEST_PASS);
  });

  // ── Upload ──────────────────────────────────────────────────────────────

  test('should display the uploader on the dashboard', async ({ page }) => {
    await page.goto(`${BASE_URL}`);

    await expect(page.getByRole('region', { name: /wall image uploader/i })).toBeVisible();
    await expect(page.getByText(/drop your spray wall photo/i)).toBeVisible();
  });

  test('should preview the image after file selection', async ({ page }) => {
    await page.goto(`${BASE_URL}`);

    const input = page.locator('input[type="file"]#wall-image-input');
    await input.setInputFiles(TEST_IMAGE_PATH);

    // Preview image should appear
    await expect(page.getByAltText(/wall preview/i)).toBeVisible({ timeout: 5_000 });

    // Filename should display
    await expect(page.getByText(/test_wall_1200x1200/i)).toBeVisible();
  });

  test('should show upload progress bar during upload', async ({ page }) => {
    await page.goto(`${BASE_URL}`);

    const input = page.locator('input[type="file"]#wall-image-input');
    await input.setInputFiles(TEST_IMAGE_PATH);

    // Fill required form fields
    await page.getByLabel(/wall name/i).fill('E2E Test Wall');
    await page.getByLabel(/angle/i).fill('40');

    // Intercept to slow down upload
    await page.route('**/api/v1/walls', async (route) => {
      await new Promise(r => setTimeout(r, 1000));
      await route.continue();
    });

    await page.getByRole('button', { name: /upload.*scan/i }).click();

    // Progress bar should appear
    await expect(page.getByRole('progressbar')).toBeVisible({ timeout: 3_000 });
  });

  test('should complete full upload and enter scanning state', async ({ page }) => {
    await page.goto(`${BASE_URL}`);

    const input = page.locator('input[type="file"]#wall-image-input');
    await input.setInputFiles(TEST_IMAGE_PATH);

    await page.getByLabel(/wall name/i).fill('E2E Wall Upload Test');
    await page.getByLabel(/angle/i).fill('35');
    await page.getByLabel(/width/i).fill('244');
    await page.getByLabel(/height/i).fill('244');

    await page.getByRole('button', { name: /upload.*scan/i }).click();

    // Wall detail page loads with scanning state
    await expect(
      page.getByText(/scanning.*for holds/i).or(page.getByText(/queued/i))
    ).toBeVisible({ timeout: 15_000 });
  });

  // ── Hold Map ─────────────────────────────────────────────────────────────

  test('should render SVG hold overlay after scan completes', async ({ page }) => {
    // Navigate to a pre-scanned wall (seeded in test DB)
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    // SVG overlay should contain hold groups
    const holdGroups = page.locator('.hold-map-svg .hold-group');
    await expect(holdGroups.first()).toBeVisible({ timeout: 10_000 });

    const count = await holdGroups.count();
    expect(count).toBeGreaterThan(0);
  });

  test('hold count badge should display the number of holds', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    const badge = page.locator('.hold-count-badge');
    await expect(badge).toBeVisible({ timeout: 10_000 });
    await expect(badge).toContainText(/\d+ holds/);
  });

  test('clicking a hold should toggle its exclusion', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    const hold = page.locator('.hold-group').first();
    await hold.waitFor({ state: 'visible', timeout: 10_000 });

    // Initially not excluded
    await expect(hold).not.toHaveClass(/hold-excluded/);

    // Click to exclude
    await hold.click();
    await expect(hold).toHaveClass(/hold-excluded/, { timeout: 3_000 });

    // Click again to re-include
    await hold.click();
    await expect(hold).not.toHaveClass(/hold-excluded/, { timeout: 3_000 });
  });

  test('hold tooltip should appear on hover', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    const hold = page.locator('.hold-group').nth(1);
    await hold.waitFor({ state: 'visible', timeout: 10_000 });

    await hold.hover();

    const tooltip = page.locator('.hold-tooltip');
    await expect(tooltip).toBeVisible({ timeout: 2_000 });
    await expect(tooltip).toContainText(/click to/i);
  });

  test('scanning overlay should appear while CV pipeline runs', async ({ page }) => {
    // Mock the wall status as "scanning"
    await page.route('**/api/v1/walls/scan-wall-id', async (route) => {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({ data: { id: 'scan-wall-id', status: 'scanning', image_url: '/test.jpg' } }),
      });
    });

    await page.goto(`${BASE_URL}/walls/scan-wall-id`);

    await expect(page.locator('.scanning-overlay')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/scanning.*for holds/i)).toBeVisible();
  });

  // ── Route Generation ──────────────────────────────────────────────────────

  test('route generator panel should be visible after scan completes', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    const panel = page.getByRole('complementary', { name: /route generator/i });
    await expect(panel).toBeVisible({ timeout: 10_000 });
  });

  test('grade slider should update the grade label', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    const slider = page.getByLabel(/difficulty/i).or(page.locator('#grade-slider'));
    await slider.waitFor({ state: 'visible', timeout: 10_000 });

    // Initial value
    await expect(page.locator('.grade-label')).toBeVisible();

    // Move slider to minimum
    await slider.evaluate((el: HTMLInputElement) => {
      el.value = '0';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    });

    await expect(page.locator('.grade-label')).toHaveText('V0');
  });

  test('style buttons should be selectable', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    const balanceBtn = page.getByRole('radio', { name: /balance/i });
    await balanceBtn.waitFor({ state: 'visible', timeout: 10_000 });

    await balanceBtn.click();
    await expect(balanceBtn).toHaveAttribute('aria-checked', 'true');
  });

  test('generate route button should be enabled when holds are available', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    const generateBtn = page.getByRole('button', { name: /generate route/i });
    await expect(generateBtn).toBeEnabled({ timeout: 10_000 });
  });

  test('generate route should show loading state during generation', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    // Slow down the API call
    await page.route('**/api/v1/walls/*/routes/generate', async (route) => {
      await new Promise(r => setTimeout(r, 1500));
      await route.continue();
    });

    const generateBtn = page.getByRole('button', { name: /generate route/i });
    await generateBtn.click();

    await expect(generateBtn).toContainText(/generating/i, { timeout: 3_000 });
    await expect(generateBtn).toBeDisabled();
  });

  test('generated route should highlight holds with role colours', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    const generateBtn = page.getByRole('button', { name: /generate route/i });
    await generateBtn.waitFor({ state: 'visible', timeout: 10_000 });
    await generateBtn.click();

    // Wait for route to appear
    await expect(page.locator('.hold-group.hold-role-start')).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('.hold-group.hold-role-finish')).toBeVisible();

    // Legend should appear
    await expect(page.locator('.hold-map-legend')).toBeVisible();
  });

  test('route summary should display quality score and hold count', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    const generateBtn = page.getByRole('button', { name: /generate route/i });
    await generateBtn.click();

    await expect(page.locator('.current-route-summary')).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('.quality-bar')).toBeVisible();
    await expect(page.locator('.role-breakdown')).toBeVisible();
  });

  test('success toast should appear after route generation', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    await page.getByRole('button', { name: /generate route/i }).click();

    const toast = page.locator('.toast.toast-success');
    await expect(toast).toBeVisible({ timeout: 20_000 });
    await expect(toast).toContainText(/generated/i);
  });

  // ── Save Route ────────────────────────────────────────────────────────────

  test('save route modal should open after clicking Save Route', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    await page.getByRole('button', { name: /generate route/i }).click();
    await page.locator('.current-route-summary').waitFor({ timeout: 20_000 });

    await page.getByRole('button', { name: /save route/i }).click();

    const modal = page.getByRole('dialog', { name: /save route/i });
    await expect(modal).toBeVisible({ timeout: 3_000 });
  });

  test('save route modal should show validation error if name is empty', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    await page.getByRole('button', { name: /generate route/i }).click();
    await page.locator('.current-route-summary').waitFor({ timeout: 20_000 });

    await page.getByRole('button', { name: /save route/i }).click();
    await page.getByRole('dialog').waitFor({ state: 'visible' });

    // Clear the name field and submit
    await page.locator('#route-name').fill('');
    await page.getByRole('button', { name: /^save route$/i }).click();

    await expect(page.getByRole('alert')).toContainText(/required/i);
  });

  test('saving a route with a name generates a share URL', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    await page.getByRole('button', { name: /generate route/i }).click();
    await page.locator('.current-route-summary').waitFor({ timeout: 20_000 });

    await page.getByRole('button', { name: /save route/i }).click();
    await page.getByRole('dialog').waitFor({ state: 'visible' });

    await page.locator('#route-name').fill('E2E Test Route');
    await page.locator('#route-desc').fill('Playwright-generated test route');

    // Enable publish
    await page.locator('#is-public').check();

    await page.getByRole('button', { name: /^save route$/i }).click();

    // Share URL should appear
    await expect(page.locator('.share-url-input')).toBeVisible({ timeout: 10_000 });
    const shareUrl = await page.locator('.share-url-input').inputValue();
    expect(shareUrl).toMatch(/\/share\//);
  });

  test('copy button should copy share URL to clipboard', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);

    await page.goto(`${BASE_URL}/walls/seed-wall-001`);
    await page.getByRole('button', { name: /generate route/i }).click();
    await page.locator('.current-route-summary').waitFor({ timeout: 20_000 });

    await page.getByRole('button', { name: /save route/i }).click();
    await page.locator('#route-name').fill('Copy Test Route');
    await page.locator('#is-public').check();
    await page.getByRole('button', { name: /^save route$/i }).click();

    await page.locator('.share-copy-btn').waitFor({ state: 'visible', timeout: 10_000 });
    await page.locator('.share-copy-btn').click();

    await expect(page.locator('.copy-confirm')).toBeVisible();
    await expect(page.locator('.share-copy-btn')).toContainText(/copied/i);
  });

  test('escape key closes the save route modal', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    await page.getByRole('button', { name: /generate route/i }).click();
    await page.locator('.current-route-summary').waitFor({ timeout: 20_000 });

    await page.getByRole('button', { name: /save route/i }).click();
    const modal = page.getByRole('dialog');
    await modal.waitFor({ state: 'visible' });

    await page.keyboard.press('Escape');
    await expect(modal).not.toBeVisible({ timeout: 2_000 });
  });

  // ── Public Share URL ──────────────────────────────────────────────────────

  test('share URL is accessible without authentication', async ({ browser }) => {
    // Open a fresh browser context (no auth cookies)
    const incognitoContext = await browser.newContext({ storageState: undefined });
    const page = await incognitoContext.newPage();

    // Use a pre-seeded share token
    await page.goto(`${BASE_URL}/share/seed-share-token-e2e`);

    await expect(page.getByText(/seed.*route/i).or(page.getByTestId('route-name'))).toBeVisible({ timeout: 10_000 });

    await incognitoContext.close();
  });

  test('invalid share token shows 404 page', async ({ page }) => {
    await page.goto(`${BASE_URL}/share/INVALID_TOKEN_9999`);
    await expect(page.getByText(/not found|404/i)).toBeVisible({ timeout: 5_000 });
  });
});

// ---------------------------------------------------------------------------
// Test: Error Paths
// ---------------------------------------------------------------------------

test.describe('Error Paths', () => {

  test.beforeEach(async ({ page }) => {
    await loginAs(page, TEST_EMAIL, TEST_PASS);
  });

  test('uploading a non-image file shows an error message', async ({ page }) => {
    await page.goto(`${BASE_URL}`);

    // Create a fake PDF file
    const fakeFile = {
      name: 'notanimage.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('fake pdf content'),
    };

    const input = page.locator('input[type="file"]#wall-image-input');
    await input.setInputFiles(fakeFile);

    await expect(page.getByText(/only jpeg|png|heic/i)).toBeVisible({ timeout: 3_000 });
  });

  test('uploading an oversized file shows a file-too-large error', async ({ page }) => {
    await page.goto(`${BASE_URL}`);

    // Simulate oversized file by mocking File.size
    await page.evaluate(() => {
      const input = document.querySelector('#wall-image-input') as HTMLInputElement;
      Object.defineProperty(input, 'files', {
        get: () => [{
          name: 'huge.jpg',
          type: 'image/jpeg',
          size: 25 * 1024 * 1024,  // 25 MB
        }],
      });
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });

    await expect(page.getByText(/too large|20 mb/i)).toBeVisible({ timeout: 3_000 });
  });

  test('scan failure shows an error banner with retry option', async ({ page }) => {
    // Mock a wall in scan_failed state
    await page.route('**/api/v1/walls/failed-wall-id', async (route) => {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          data: {
            id:        'failed-wall-id',
            status:    'scan_failed',
            name:      'Failed Wall',
            image_url: '/test.jpg',
            scan_error:'No holds detected in the image.',
          },
        }),
      });
    });

    await page.goto(`${BASE_URL}/walls/failed-wall-id`);

    await expect(page.locator('.error-banner')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/no holds detected/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /re-upload/i })).toBeVisible();
  });

  test('generate route button is disabled when fewer than 4 active holds', async ({ page }) => {
    // Mock a wall with only 3 holds
    await page.route('**/api/v1/walls/sparse-wall/holds', async (route) => {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({ data: [
          { id: 'h1', center_x: 0.2, center_y: 0.8, type: 'jug', excluded: false },
          { id: 'h2', center_x: 0.5, center_y: 0.5, type: 'sloper', excluded: false },
          { id: 'h3', center_x: 0.8, center_y: 0.2, type: 'crimp', excluded: false },
        ]}),
      });
    });

    await page.goto(`${BASE_URL}/walls/sparse-wall`);

    const generateBtn = page.getByRole('button', { name: /generate route/i });
    await generateBtn.waitFor({ state: 'visible', timeout: 10_000 });
    await expect(generateBtn).toBeDisabled();
    await expect(page.getByText(/need.*4.*active holds/i)).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Test: Accessibility
// ---------------------------------------------------------------------------

test.describe('Accessibility', () => {

  test.beforeEach(async ({ page }) => {
    await loginAs(page, TEST_EMAIL, TEST_PASS);
  });

  test('uploader drop zone is keyboard focusable and activatable', async ({ page }) => {
    await page.goto(`${BASE_URL}`);

    const dropZone = page.locator('.uploader-dropzone');
    await dropZone.focus();
    await expect(dropZone).toBeFocused();

    // Should be reachable via Tab
    await expect(dropZone).toHaveAttribute('tabindex', '0');
    await expect(dropZone).toHaveAttribute('role', 'button');
  });

  test('save route modal traps focus correctly', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    await page.getByRole('button', { name: /generate route/i }).click();
    await page.locator('.current-route-summary').waitFor({ timeout: 20_000 });

    await page.getByRole('button', { name: /save route/i }).click();
    const modal = page.getByRole('dialog');
    await modal.waitFor({ state: 'visible' });

    // Tab through all focusable elements — should stay inside modal
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press('Tab');
      const focused = await page.evaluate(() => document.activeElement?.closest('[role="dialog"]') !== null);
      expect(focused).toBe(true);
    }
  });

  test('hold groups have aria-label and aria-pressed attributes', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    const hold = page.locator('.hold-group').first();
    await hold.waitFor({ state: 'visible', timeout: 10_000 });

    await expect(hold).toHaveAttribute('aria-label');
    await expect(hold).toHaveAttribute('aria-pressed');
    await expect(hold).toHaveAttribute('role', 'button');
  });

  test('toast notifications have correct aria-live attribute', async ({ page }) => {
    await page.goto(`${BASE_URL}/walls/seed-wall-001`);

    // Trigger a success notification
    await page.getByRole('button', { name: /generate route/i }).click();
    await page.locator('.toast').waitFor({ state: 'visible', timeout: 20_000 });

    const toast = page.locator('.toast-success').first();
    await expect(toast).toHaveAttribute('aria-live', 'polite');
  });
});
