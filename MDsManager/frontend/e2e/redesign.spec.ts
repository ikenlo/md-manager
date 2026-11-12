/**
 * Знімки всіх сторінок у дизайні MDS Connect → MDsManager/docs/screenshots/redesign-*.png
 *
 *   npm run capture        (лише знімки; у `npm run test:e2e` вони пропускаються)
 *
 * Світла й темна тема, ПК (1440×900) і телефон (390×844). Дані — з e2e/backend.py.
 */
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';

const OUT = path.resolve(process.cwd(), '../docs/screenshots');
type Theme = 'light' | 'dark';
const shot = (name: string, theme: Theme) => path.join(OUT, `redesign-${name}-${theme}.png`);

const MOBILE = { width: 390, height: 844 };
const panel = (page: Page) => page.locator('section[aria-label="Пропозиція AI"]');
const rows = (page: Page) => page.locator('ul[aria-label="Список діалогів"] > li button');
const row = (page: Page, name: string) => rows(page).filter({ hasText: name });

async function setTheme(page: Page, theme: Theme) {
  await page.addInitScript((t) => localStorage.setItem('mds_theme', t), theme);
}

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
}

/** Без курсора, dev-панелі й анімацій — знімки однакові від запуску до запуску. */
async function snap(page: Page, file: string) {
  await page.addStyleTag({
    content:
      '*,*::before,*::after{caret-color:transparent!important;animation-duration:0s!important;animation-delay:0s!important;transition:none!important}' +
      'button[aria-label="Dev-панель"]{display:none!important}',
  });
  await page.waitForTimeout(250);
  await page.screenshot({ path: file });
}

const SECTIONS = [
  ['/appointments', 'appointments'],
  ['/clients', 'clients'],
  ['/agents', 'agents'],
  ['/marketing', 'marketing'],
  ['/analytics', 'analytics'],
  ['/settings', 'settings'],
] as const;

test.describe.configure({ mode: 'serial' });

for (const theme of ['light', 'dark'] as const) {
  test.describe(`Redesign ${theme} @screenshots`, () => {
    test.beforeEach(async ({ page }) => setTheme(page, theme));

    test('login', async ({ page }) => {
      await page.goto('/login');
      await page.locator('input[name=identifier]').fill('admin');
      await snap(page, shot('login', theme));
      await page.setViewportSize(MOBILE);
      await snap(page, shot('mobile-login', theme));
    });

    test('inbox', async ({ page }) => {
      await login(page);
      await snap(page, shot('inbox', theme));
      await openDialogue(page, 'Тест Запис');
      await expect(panel(page).locator('textarea')).toHaveValue(/^Вас записано/);
      await snap(page, shot('chat-ai-booking', theme));
      await openDialogue(page, 'Олена Коваль');
      await snap(page, shot('chat', theme));
      await page.getByRole('button', { name: 'Запустити AI' }).click();
      await expect(panel(page).getByRole('button', { name: 'Схвалити' })).toBeVisible();
      await snap(page, shot('chat-ai-panel', theme));
      await panel(page).getByRole('button', { name: 'Відхилити' }).click(); // наступний запуск — з чистого стану
      await expect(panel(page)).toHaveCount(0);
    });

    test('sections', async ({ page }) => {
      await login(page);
      for (const [url, name] of SECTIONS) {
        await page.goto(url);
        await page.locator('h1').first().waitFor();
        await snap(page, shot(name, theme));
      }
    });

    test('mobile', async ({ page }) => {
      await page.setViewportSize(MOBILE);
      await login(page);
      await snap(page, shot('mobile-inbox', theme));
      await openDialogue(page, 'Тест Запис');
      await expect(panel(page)).toBeVisible();
      await snap(page, shot('mobile-chat-ai', theme));
      await page.getByRole('button', { name: 'Назад до списку' }).click();
      for (const [url, name] of [['/more', 'more'], ['/appointments', 'appointments'], ['/settings', 'settings']] as const) {
        await page.goto(url);
        await page.waitForTimeout(150);
        await snap(page, shot(`mobile-${name}`, theme));
      }
    });
  });
}
