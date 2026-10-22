// End-to-end test of the whole app in a real browser (Microsoft Edge or Chrome, no download).
//
//   1. start the backend and the dev server (start_app.bat, or by hand)
//   2. npm run e2e                          (BASE_URL defaults to http://localhost:5173)
//
// Environment: BASE_URL, BROWSER_CHANNEL (msedge | chrome), E2E_LLM=1 to also exercise the
// assistant (makes one paid OpenRouter call), E2E_LIVE=0 to skip the live-meeting part,
// SCREENSHOTS=<dir> to save screenshots. Needs ffmpeg on PATH (for the fake microphone input).
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const here = dirname(fileURLToPath(import.meta.url))
const BASE = process.env.BASE_URL || 'http://localhost:5173'
const SHOTS = process.env.SCREENSHOTS
const fixture = join(here, 'fixtures', 'standup.mp4')
const work = mkdtempSync(join(tmpdir(), 'tt-e2e-'))
const wav = join(work, 'standup.wav')
execFileSync('ffmpeg', ['-v', 'error', '-y', '-i', fixture, '-vn', '-ac', '1', '-ar', '48000', wav])

let failures = 0
const step = async (name, fn) => {
  const started = Date.now()
  try {
    await fn()
    console.log(`  ✓ ${name} (${((Date.now() - started) / 1000).toFixed(1)}s)`)
  } catch (err) {
    failures++
    console.log(`  ✗ ${name}\n    ${String(err.message || err).split('\n').slice(0, 6).join('\n    ')}`)
  }
}
const expect = (cond, message) => {
  if (!cond) throw new Error(message)
}
const shot = async (page, name) => SHOTS && page.screenshot({ path: join(SHOTS, `${name}.png`) })

const browser = await chromium.launch({
  channel: process.env.BROWSER_CHANNEL || 'msedge',
  headless: process.env.HEADED !== '1',
  args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', `--use-file-for-fake-audio-capture=${wav}`],
})
const context = await browser.newContext({ viewport: { width: 1600, height: 1000 }, permissions: ['microphone'] })
const page = await context.newPage()
const errors = []
page.on('pageerror', (e) => errors.push(String(e)))
page.on('console', (m) => m.type() === 'error' && !/Failed to load resource/.test(m.text()) && errors.push(m.text()))

console.log(`TurboTranscribe e2e against ${BASE}`)
let jobUrl = ''

await step('library loads and the backend is ready', async () => {
  await page.goto(BASE)
  await page.getByRole('heading', { name: /every word/i }).waitFor()
  await page.getByText(/large|base|small|tiny|medium/).first().waitFor({ timeout: 120000 })
  await shot(page, '01-library')
})

await step('upload a meeting video and wait for processing', async () => {
  await page.setInputFiles('input[type=file]', fixture)
  const card = page.locator('article', { hasText: 'standup' }).first()
  await card.waitFor({ timeout: 30000 })
  await shot(page, '02-processing')
  await card.getByText('Scenes').waitFor({ timeout: 240000 })
  await card.getByRole('button', { name: /standup/i }).click()
  await page.waitForURL(/#\/job\//)
  jobUrl = page.url()
})

await step('recording view: stats, scene track, slide titles, speakers', async () => {
  await page.getByRole('heading', { name: 'standup', level: 1 }).waitFor()
  for (const title of ['Kubernetes Migration', 'Snowflake Costs Q3', 'Action Items']) {
    await page.getByRole('heading', { name: title }).first().waitFor()
  }
  const voices = await page.getByText('Speaker 2').count()
  expect(voices > 0, 'expected two identified speakers')
  await page.locator('video').evaluate((v) => v.readyState >= 1 || new Promise((r) => v.addEventListener('loadedmetadata', r, { once: true })))
  await shot(page, '03-timeline')
})

await step('transcript: words seek the video, speaker filter works', async () => {
  await page.getByRole('tab', { name: 'Transcript' }).click()
  const word = page.locator('[data-seg] span[title], [data-seg] p span span').filter({ hasText: /^Postgres/ }).first()
  await word.click()
  const t = await page.locator('video').evaluate((v) => v.currentTime)
  expect(t > 20 && t < 35, `clicking "Postgres" should seek to ~30 s, got ${t.toFixed(1)}`)
  await page.locator('video').evaluate((v) => v.pause())
  await page.getByRole('button', { name: 'Speaker 2' }).click()
  const lines = await page.locator('[data-seg]').count()
  expect(lines >= 3 && lines <= 6, `speaker filter should leave Speaker 2's lines, got ${lines}`)
  await page.getByRole('button', { name: 'Everyone' }).click()
  await shot(page, '04-transcript')
})

await step('speakers: rename a voice everywhere', async () => {
  await page.getByRole('tab', { name: /Speakers/ }).click()
  const name = page.getByLabel('Name for S1')
  await name.fill('Zira')
  await name.press('Enter')
  await page.getByRole('tab', { name: 'Transcript' }).click()
  await page.getByText('Zira').first().waitFor()
})

await step('cross-check tab renders', async () => {
  await page.getByRole('tab', { name: /Cross-check/ }).click()
  await page.getByText(/Suggested/).waitFor()
  await page.getByText('Spelling hints given to the speech model').waitFor()
  await shot(page, '05-crosscheck')
})

await step('assistant renders a streamed answer: table, clickable timestamps (mocked, free)', async () => {
  const chunks = ['### Action items\n\n| Task | Owner | When |\n', '|---|---|---|\n', '| Migrate Postgres | Marcus Okafor | [00:27] |\n']
  await page.route('**/api/chat', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: chunks.map((delta) => `data: ${JSON.stringify({ delta })}\n\n`).join('') + 'data: {"done": true}\n\n',
    }),
  )
  await page.locator('aside').getByRole('button', { name: 'Action items' }).first().click()
  await page.locator('aside table').first().waitFor()
  await page.locator('aside').getByRole('button', { name: '00:27' }).first().click()
  const t = await page.locator('video').evaluate((v) => v.currentTime)
  expect(Math.abs(t - 27) < 1.5, `timestamp should seek to 27 s, got ${t.toFixed(1)}`)
  await page.locator('video').evaluate((v) => v.pause())
  await page.unroute('**/api/chat')
  await shot(page, '06b-assistant-mock')
})

await step('dropping a file anywhere uploads it once', async () => {
  await page.goto(BASE)
  await page.getByRole('heading', { name: /every word/i }).waitFor()
  await page.locator('article', { hasText: 'standup' }).first().waitFor() // the library has loaded
  const before = await page.locator('article').count()
  const bytes = [...readFileSync(fixture)]
  const transfer = await page.evaluateHandle((data) => {
    const dt = new DataTransfer()
    dt.items.add(new File([new Uint8Array(data)], 'dropped.mp4', { type: 'video/mp4' }))
    return dt
  }, bytes)
  const target = page.getByRole('heading', { name: /every word/i })
  await target.dispatchEvent('dragenter', { dataTransfer: transfer })
  await page.getByText('Drop to').waitFor()
  await target.dispatchEvent('drop', { dataTransfer: transfer })
  await page.getByText('Drop to').waitFor({ state: 'hidden' })
  await page.locator('article', { hasText: 'dropped' }).first().waitFor({ timeout: 30000 })
  await page.waitForTimeout(1500)
  const after = await page.locator('article').count()
  expect(after === before + 1, `expected exactly one new recording, got ${after - before}`)
})

await step('library search finds a phrase and jumps to it', async () => {
  await page.goto(BASE)
  await page.getByLabel('Search every transcript and slide').fill('terraform review')
  const hit = page.getByRole('button', { name: /Terraform/ }).first()
  await hit.waitFor()
  await shot(page, '06-search')
  await hit.click()
  await page.waitForURL(/\?t=/)
})

if (process.env.E2E_LLM === '1') {
  await step('assistant streams an answer with clickable timestamps', async () => {
    await page.goto(jobUrl)
    await page.getByRole('button', { name: 'Action items' }).first().click()
    const answer = page.locator('aside .prose').last()
    await answer.waitFor()
    await page.waitForFunction(() => !document.querySelector('aside .stream-caret'), null, { timeout: 120000 })
    const text = await answer.innerText()
    expect(/postgres/i.test(text), 'answer should mention the Postgres action item')
    await shot(page, '07-assistant')
  })
}

await step('dark theme and mobile layout render', async () => {
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.goto(jobUrl || BASE)
  await page.waitForTimeout(800)
  await shot(page, '08-dark')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(500)
  await shot(page, '09-mobile')
  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.emulateMedia({ colorScheme: 'light' })
})

if (process.env.E2E_LIVE !== '0') {
  await step('live meeting from the microphone is saved and reprocessed', async () => {
    await page.goto(`${BASE}/#/live`)
    await page.getByRole('tab', { name: 'Microphone' }).click()
    await page.getByLabel('Meeting title').fill('E2E live check')
    await page.getByRole('button', { name: /Start listening/ }).click()
    await page.getByText('Recording').first().waitFor({ timeout: 30000 })
    await page.locator('p', { hasText: /migration|services|Snowflake/i }).first().waitFor({ timeout: 60000 })
    await shot(page, '10-live')
    await page.getByRole('button', { name: /End meeting/ }).click()
    await page.getByText('Saved to the library.').waitFor({ timeout: 60000 })
    await page.getByRole('button', { name: 'Open' }).click()
    await page.getByRole('heading', { name: 'E2E live check', level: 1 }).waitFor({ timeout: 240000 })
    await page.getByRole('tab', { name: 'Transcript' }).waitFor({ timeout: 240000 })
    await shot(page, '11-live-result')
  })
}

await step('no uncaught errors in the page', async () => {
  expect(errors.length === 0, errors.join('\n'))
})

await browser.close()
console.log(failures ? `\n${failures} step(s) failed` : '\nAll steps passed')
process.exit(failures ? 1 : 0)
