/**
 * Phase 3 AI flow end-to-end: режими, панель, схвалення/відхилення, перегенерація,
 * автозапуск, значки, дві вкладки. Бекенд — e2e/backend.py (mock Ollama, чиста БД).
 *
 * Діалоги з демо-даних: Олена Коваль, Марія Шевчук, Анна Бондар.
 * Додатково (backend.py): «Авто Один/Два/Три» — лише вихідне повідомлення, тож
 * simulate_attachment створює в них НОВЕ вхідне (для автозапуску); «Тест Запис» — pending із записом.
 */
import { expect, test, type BrowserContext, type Page } from '@playwright/test';

type Mode = 'AI авто' | 'Вручну' | 'Людина';

const panel = (page: Page) => page.locator('section[aria-label="Пропозиція AI"]');
const bubble = (page: Page) => page.getByRole('status', { name: 'AI аналізує розмову' });
const rows = (page: Page) => page.locator('ul[aria-label="Список діалогів"] > li button');
const row = (page: Page, name: string) => rows(page).filter({ hasText: name });
const messages = (page: Page) => page.locator('main p.whitespace-pre-wrap');

async function login(page: Page) {
  await page.goto('/login');
  await page.fill('input[name=identifier]', 'admin');
  await page.fill('input[name=password]', 'admin');
  await page.click('button[type=submit]');
  await page.waitForURL('/');
  await rows(page).first().waitFor();
}

/** Виклик API від імені залогіненого користувача (токен з localStorage сторінки). */
async function api<T = unknown>(page: Page, method: string, path: string, body?: unknown): Promise<{ status: number; data: T }> {
  return page.evaluate(
    async ({ method, path, body }) => {
      const token = JSON.parse(localStorage.getItem('mds_auth') ?? '{}').state?.token;
      const r = await fetch(path, {
        method,
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      return { status: r.status, data: await r.json().catch(() => null) };
    },
    { method, path, body },
  );
}

async function dialogueUuid(page: Page, name: string): Promise<string> {
  const { data } = await api<{ items: { uuid: string; client: { name: string } }[] }>(page, 'GET', '/api/dialogues?limit=200');
  const d = data.items.find((i) => i.client.name.startsWith(name));
  if (!d) throw new Error(`no dialogue ${name}`);
  return d.uuid;
}

/** Відхиляє pending-пропозицію діалогу на сервері (чистий старт тесту). */
async function clearServerPending(page: Page, name: string) {
  const uuid = await dialogueUuid(page, name);
  const { data } = await api<{ suggestion: { uuid: string } | null }>(page, 'GET', `/api/dialogues/${uuid}/ai/pending`);
  if (data.suggestion) await api(page, 'POST', `/api/dialogues/${uuid}/ai/${data.suggestion.uuid}/reject`, {});
}

async function openDialogue(page: Page, name: string) {
  await row(page, name).click();
  await expect(page.locator('main h2')).toContainText(name);
}

async function setAIMode(page: Page, mode: Mode) {
  await page.locator('main header [role=radiogroup]').getByRole('radio', { name: mode }).click();
}

async function expectMode(page: Page, mode: Mode) {
  await expect(page.locator('main header [role=radiogroup]').getByRole('radio', { name: mode })).toHaveAttribute('aria-checked', 'true');
}

/** Mock Ollama відповідає за ~0,5 с — щоб побачити бульбашку, затримуємо відповідь у браузері. */
async function slowRespond(target: Page | BrowserContext, ms = 1500) {
  await target.route('**/ai/respond', async (route) => {
    const response = await route.fetch();
    await new Promise((r) => setTimeout(r, ms));
    await route.fulfill({ response });
  });
}

function countRespondCalls(target: Page | BrowserContext): () => number {
  let n = 0;
  target.on('request', (r) => {
    if (r.url().includes('/ai/respond')) n += 1;
  });
  return () => n;
}

test.beforeEach(async ({ page }) => {
  await login(page);
  // режими AI — свіжі для кожного тесту
  await page.evaluate(() => {
    for (const k of Object.keys(localStorage)) if (k.startsWith('mds_ai_mode_') || k.startsWith('mds_ai_auto_')) localStorage.removeItem(k);
  });
  await page.reload();
  await rows(page).first().waitFor();
});

test.describe('Phase 3 AI flow', () => {
  test('1. AI mode toggle persists per dialogue', async ({ page }) => {
    await openDialogue(page, 'Олена');
    await expectMode(page, 'Вручну'); // типовий режим
    await setAIMode(page, 'AI авто');
    await openDialogue(page, 'Марія');
    await setAIMode(page, 'Людина');

    await page.reload();
    await openDialogue(page, 'Олена');
    await expectMode(page, 'AI авто');
    await openDialogue(page, 'Марія');
    await expectMode(page, 'Людина');
    // «Людина» синхронізована зі списком
    await expect(row(page, 'Марія').getByText('Людина', { exact: true })).toBeVisible();
  });

  test('2. Manual trigger shows panel with AI text', async ({ page }) => {
    await clearServerPending(page, 'Олена');
    await slowRespond(page);
    await openDialogue(page, 'Олена');
    await page.getByRole('button', { name: 'Запустити AI' }).click();
    await expect(bubble(page)).toBeVisible();
    await expect(panel(page)).toBeVisible();
    await expect(panel(page).locator('textarea')).toHaveValue('Тестова відповідь від AI. 😊');
    await expect(panel(page).getByRole('button', { name: 'Схвалити' })).toBeVisible();
    await expect(panel(page).getByRole('button', { name: 'Відхилити' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Вітаю! Чим можу допомогти?' })).toHaveCount(0); // швидкі відповіді сховано
    await panel(page).getByRole('button', { name: 'Відхилити' }).click();
  });

  test('3. Approve creates message in chat', async ({ page }) => {
    await clearServerPending(page, 'Олена');
    await openDialogue(page, 'Олена');
    await page.getByRole('button', { name: 'Запустити AI' }).click();
    await expect(panel(page)).toBeVisible();
    await expect(row(page, 'Олена').getByLabel('Є пропозиція AI')).toBeVisible();

    const textarea = panel(page).locator('textarea');
    await textarea.fill(`${await textarea.inputValue()} (edited)`);
    await panel(page).getByRole('button', { name: 'Схвалити' }).click();

    await expect(panel(page)).toHaveCount(0);
    await expect(page.getByText('AI-відповідь схвалено')).toBeVisible();
    const sent = messages(page).filter({ hasText: '(edited)' });
    await expect(sent).toHaveCount(1);
    // статус: у черзі → надіслано (воркер кожні 2 с)
    const meta = sent.locator('xpath=ancestor::div[contains(@class,"flex-col")][1]');
    await expect(meta.getByLabel(/У черзі|Надіслано/)).toBeVisible();
    await expect(meta.getByLabel('Надіслано')).toBeVisible({ timeout: 15_000 });
    await expect(row(page, 'Олена').getByLabel('Є пропозиція AI')).toHaveCount(0);
  });

  test('4. Reject removes panel, no message', async ({ page }) => {
    await clearServerPending(page, 'Марія');
    await openDialogue(page, 'Марія');
    await page.getByRole('button', { name: 'Запустити AI' }).click();
    await expect(panel(page)).toBeVisible();
    const before = await messages(page).count();

    await panel(page).getByRole('button', { name: 'Відхилити' }).click();
    await expect(panel(page)).toHaveCount(0);
    await expect(page.getByText('AI-відповідь відхилено')).toBeVisible();
    await page.waitForTimeout(500);
    await expect(messages(page)).toHaveCount(before);
  });

  test('5. Regenerate replaces suggestion', async ({ page }) => {
    await clearServerPending(page, 'Анна');
    await openDialogue(page, 'Анна');
    await page.getByRole('button', { name: 'Запустити AI' }).click();
    await expect(panel(page)).toBeVisible();
    const uuid = await dialogueUuid(page, 'Анна');
    const first = (await api<{ suggestion: { uuid: string } }>(page, 'GET', `/api/dialogues/${uuid}/ai/pending`)).data.suggestion.uuid;

    await slowRespond(page);
    await panel(page).locator('textarea').fill('чернетка адміністратора');
    await panel(page).getByRole('button', { name: 'Перегенерувати' }).click();
    // поки AI думає — панель лишається, кнопка зайнята (і має назву — 3.3.1)
    await expect(panel(page).getByRole('button', { name: 'Перегенерувати' })).toHaveAttribute('aria-busy', 'true');
    await expect(panel(page)).toHaveCount(1);
    await expect(panel(page).locator('textarea')).toHaveValue('Тестова відповідь від AI. 😊');

    const second = (await api<{ suggestion: { uuid: string } }>(page, 'GET', `/api/dialogues/${uuid}/ai/pending`)).data.suggestion.uuid;
    expect(second).not.toBe(first); // нова пропозиція, стара — expired
    await panel(page).getByRole('button', { name: 'Відхилити' }).click();
  });

  test('6. Close panel clears pending locally', async ({ page }) => {
    await clearServerPending(page, 'Олена');
    await openDialogue(page, 'Олена');
    await page.getByRole('button', { name: 'Запустити AI' }).click();
    await expect(panel(page)).toBeVisible();

    await panel(page).getByRole('button', { name: 'Сховати пропозицію' }).click();
    await expect(panel(page)).toHaveCount(0);
    await openDialogue(page, 'Марія');
    await openDialogue(page, 'Олена');
    await expect(panel(page)).toBeVisible(); // з сервера
    await panel(page).getByRole('button', { name: 'Відхилити' }).click();
  });

  test('7. Manual send clears pending on server', async ({ page }) => {
    await clearServerPending(page, 'Анна');
    await openDialogue(page, 'Анна');
    await page.getByRole('button', { name: 'Запустити AI' }).click();
    await expect(panel(page)).toBeVisible();

    await page.fill('input[aria-label="Повідомлення"]', 'Відповідаю сама');
    await page.keyboard.press('Enter');
    await expect(panel(page)).toHaveCount(0);
    await expect(messages(page).filter({ hasText: 'Відповідаю сама' })).toHaveCount(1);

    await expect
      .poll(async () => (await api<{ suggestion: unknown }>(page, 'GET', `/api/dialogues/${await dialogueUuid(page, 'Анна')}/ai/pending`)).data.suggestion)
      .toBeNull();
    await page.reload();
    await openDialogue(page, 'Анна');
    await page.waitForTimeout(800);
    await expect(panel(page)).toHaveCount(0);
  });

  test('8. Auto mode triggers on new inbound', async ({ page }) => {
    await openDialogue(page, 'Авто Один');
    await setAIMode(page, 'AI авто');
    await slowRespond(page);
    const calls = countRespondCalls(page);

    const r = await api(page, 'POST', '/api/_test/simulate_attachment', { dialogue_uuid: await dialogueUuid(page, 'Авто Один') });
    expect(r.status).toBe(201);
    await expect(bubble(page)).toBeVisible(); // без кліку «Запустити AI»
    await expect(panel(page)).toBeVisible();
    await expect(panel(page).getByText('Питання', { exact: true })).toBeVisible();
    expect(calls()).toBe(1);
  });

  test('9. Mode "human" shows no AI button or auto-trigger', async ({ page }) => {
    await openDialogue(page, 'Авто Два');
    await setAIMode(page, 'Людина');
    await expect(page.getByRole('button', { name: 'Запустити AI' })).toHaveCount(0);
    const calls = countRespondCalls(page);

    await api(page, 'POST', '/api/_test/simulate_attachment', { dialogue_uuid: await dialogueUuid(page, 'Авто Два') });
    await expect(page.locator('main img[src^="/api/media/"]')).toBeVisible(); // вхідне дійшло
    await page.waitForTimeout(2000);
    await expect(bubble(page)).toHaveCount(0);
    await expect(panel(page)).toHaveCount(0);
    expect(calls()).toBe(0);
  });

  test('10. Typing bubble appears during respond and disappears after', async ({ page }) => {
    await clearServerPending(page, 'Марія');
    await slowRespond(page);
    await openDialogue(page, 'Марія');
    await page.getByRole('button', { name: 'Запустити AI' }).click();
    await expect(bubble(page)).toHaveCount(1);
    await expect(bubble(page)).toContainText('AI аналізує');
    await expect(panel(page)).toBeVisible();
    await expect(bubble(page)).toHaveCount(0);
    await panel(page).getByRole('button', { name: 'Відхилити' }).click();
  });

  test('11. Booking suggestion shows booking details card', async ({ page }) => {
    // pending із записом підготовлено в backend.py (mock Ollama не викликає create_appointment)
    await expect(row(page, 'Тест Запис').getByLabel('Є пропозиція AI')).toBeVisible();
    await openDialogue(page, 'Тест Запис');
    await expect(panel(page)).toBeVisible();
    const confirmation = 'Вас записано на Манікюр 01.12.2026 о 10:00. Чекаємо вас! 😊';
    await expect(panel(page).locator('textarea')).toHaveValue(confirmation);
    await expect(panel(page).getByText('Запис', { exact: true })).toBeVisible();
    await expect(panel(page).getByText('01.12.2026 о 10:00', { exact: true })).toBeVisible();

    await panel(page).getByRole('button', { name: 'Схвалити' }).click();
    await expect(panel(page)).toHaveCount(0);
    await expect(messages(page).filter({ hasText: confirmation })).toHaveCount(1);
  });

  test('12. Two tabs: only one triggers AI on same inbound', async ({ page, context }) => {
    const tab2 = await context.newPage();
    await tab2.goto('/');
    await rows(tab2).first().waitFor();

    await openDialogue(page, 'Авто Три');
    await setAIMode(page, 'AI авто'); // localStorage спільний для вкладок
    await openDialogue(tab2, 'Авто Три');
    await expectMode(tab2, 'AI авто');
    const calls = countRespondCalls(context);

    await api(page, 'POST', '/api/_test/simulate_attachment', { dialogue_uuid: await dialogueUuid(page, 'Авто Три') });
    // панель з'являється у вкладці, яка запустила AI
    await expect.poll(async () => (await panel(page).count()) + (await panel(tab2).count()), { timeout: 8_000 }).toBeGreaterThan(0);
    await page.waitForTimeout(2000);
    expect(calls()).toBe(1); // Web Locks: одна вкладка запускає AI
  });
});
