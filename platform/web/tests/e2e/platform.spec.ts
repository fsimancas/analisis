import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const overview = {
  counts: { countries: 76, competitions: 207, teams: 5490, matches: 46918 },
  open_quality_issues: 3,
}

async function mockApi(page: Page) {
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let body: unknown = []
    if (path.endsWith('/overview')) body = overview
    if (path.endsWith('/competitions')) {
      body = [{ id: 1, name: 'Primera A', country: 'Colombia', match_count: 380 }]
    }
    if (path.endsWith('/matches')) {
      body = [{
        id: 1,
        kickoff_date: '2026-10-19',
        competition: 'Primera A',
        home_team: 'Local',
        away_team: 'Visitante',
        status: 'SCHEDULED',
        home_score: null,
        away_score: null,
      }]
    }
    await route.fulfill({ json: body })
  })
}

test.beforeEach(async ({ page }) => mockApi(page))

test('dashboard is responsive and has no serious accessibility violations', async ({ page }, testInfo) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Panorama operativo' })).toBeVisible()
  await expect(page.getByText('46.918')).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  expect(overflow).toBe(false)
  const results = await new AxeBuilder({ page }).analyze()
  const serious = results.violations.filter((violation) =>
    ['critical', 'serious'].includes(violation.impact ?? ''),
  )
  expect(serious).toEqual([])
  await page.screenshot({ path: testInfo.outputPath('dashboard.png'), fullPage: true })
})

test('navigation adapts to desktop and mobile', async ({ page }, testInfo) => {
  await page.goto('/')
  const mobile = testInfo.project.name.startsWith('mobile')
  if (mobile) {
    await expect(page.getByRole('navigation', { name: 'Navegación principal móvil' })).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Navegación principal', exact: true })).toBeHidden()
    await page.getByRole('link', { name: 'Partidos' }).click()
    await expect(page.getByRole('heading', { name: 'Partidos', exact: true })).toBeVisible()
  } else {
    await expect(page.getByRole('navigation', { name: 'Navegación principal móvil' })).toBeHidden()
    await expect(page.getByRole('navigation', { name: 'Navegación principal', exact: true })).toBeVisible()
  }
})
