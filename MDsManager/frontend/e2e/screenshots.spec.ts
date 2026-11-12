/**
 * Знімки екрана Phase 3 для документації → MDsManager/docs/screenshots/phase3-*.png
 *
 *   npm run capture        (лише ці тести; у `npm run test:e2e` вони пропускаються)
 *
 * Дані — з e2e/backend.py (чиста БД, mock Ollama). Тести йдуть по черзі й спираються на стан
 * попередніх (пропозиції, створені раніше), тому serial.
 */
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';

const OUT = path.resolve(process.cwd(), '../docs/screenshots');
const shot = (name: string) => path.join(OUT, `phase3-${name}.png`);

const panel = (page: Page) => page.locator('section[aria-label="Пропозиція AI"]');
const rows = (page: Page) => page.locator('ul[aria-label="Список діалогів"] > li button');
const row = (page: Page, name: string) => rows(page).filter({ hasText: name });

async function login(page: Page) {
  await page.goto('/login');
  await page.fill('input[name=identifier]', 'admin');
  await page.fill('input[name=password]', 'admin');
  await page.click('button[type=submit]');
  await page.waitForURL('/');
  await rows(page).first().waitFor();
}

async function openDialogue(page: Page, name: string) {
  await row(page, name).click();
  await expect(page.locator('main h2')).toContainText(name);
  await page.waitForTimeout(300); // завершити анімації появи
}

/** Знімки детерміновані: без курсора введення і без dev-панелі (у production її немає). */
async function stabilize(page: Page) {
  await page.addStyleTag({
    content: '*{caret-color:transparent!important} button[aria-label="Dev-панель"]{display:none!important}',
  });
}

test.describe.configure({ mode: 'serial' });

test.describe('Phase 3 screenshots @screenshots', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('toggle', async ({ page }) => {
    await login(page);
    await openDialogue(page, 'Олена Коваль');
    await expect(page.locator('main header [role=radio][aria-checked=true]')).toHaveText(/Вручну/);
    await stabilize(page);
    await page.screenshot({ path: shot('ai-toggle') });
  });

  test('panel-question', async ({ page }) => {
    await login(page);
    await openDialogue(page, 'Олена Коваль');
    await page.getByRole('button', { name: 'Запустити AI' }).click();
    await expect(panel(page)).toBeVisible();
    await expect(panel(page).getByRole('button', { name: 'Перегенерувати' })).toBeVisible();
    await stabilize(page);
    await page.screenshot({ path: shot('ai-panel-question') });
  });

  test('panel-booking', async ({ page }) => {
    await login(page);
    await openDialogue(page, 'Тест Запис'); // pending із записом — з backend.py
    await expect(panel(page).locator('textarea')).toHaveValue(/^Вас записано на Манікюр/);
    await stabilize(page);
    await page.screenshot({ path: shot('ai-panel-booking') });
  });

  test('typing-bubble', async ({ page }) => {
    await login(page);
    await page.route('**/ai/respond', async (route) => {
      const response = await route.fetch();
      await new Promise((r) => setTimeout(r, 2500));
      await route.fulfill({ response });
    });
    await openDialogue(page, 'Марія Шевчук');
    await page.getByRole('button', { name: 'Запустити AI' }).click();
    await expect(page.getByRole('status', { name: 'AI аналізує розмову' })).toBeVisible();
    await page.emulateMedia({ reducedMotion: 'reduce' }); // точки не стрибають на знімку
    await stabilize(page);
    await page.screenshot({ path: shot('ai-typing-bubble') });
    await expect(panel(page)).toBeVisible(); // дочекатися — пропозиція знадобиться для значків
  });

  test('chatlist-badge', async ({ page }) => {
    await login(page); // масове завантаження pending при відкритті інбоксу
    for (const name of ['Олена Коваль', 'Марія Шевчук', 'Тест Запис']) {
      await expect(row(page, name).getByLabel('Є пропозиція AI')).toBeVisible();
    }
    await stabilize(page);
    await page.screenshot({ path: shot('chatlist-badge') });
  });

  test('mobile-panel', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page);
    await openDialogue(page, 'Олена Коваль');
    await expect(panel(page)).toBeVisible();
    await stabilize(page);
    await page.screenshot({ path: shot('mobile-panel') });
  });
});
