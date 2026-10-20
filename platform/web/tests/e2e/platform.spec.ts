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
    if (path.endsWith('/auth/me')) {
      body = {
        id: 1,
        email: 'admin@example.com',
        display_name: 'Administrator',
        role: 'ADMIN',
        active: 1,
        created_at: '2026-10-19T00:00:00Z',
      }
    }
    if (path.endsWith('/admin/summary')) body = { countries: 76, teams: 5490, audit_log: 12 }
    if (path.endsWith('/admin/deployment/preflight')) {
      body = {
        ready: false,
        environment: 'development',
        domain: null,
        database: '/data/fais.sqlite3',
        redis: '127.0.0.1:6379/0',
        issues: [],
      }
    }
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
    if (path.endsWith('/analyst/workspace/runs')) body = []
    if (path.endsWith('/analyst/workbooks')) body = []
    if (path.includes('/analyst/workspace/montecarlo/')) {
      body = {
        id: 'simulation-1',
        match_id: 1,
        result: {
          version: 'monte-carlo-poisson-v1',
          iterations: 50000,
          seed: 42,
          expected_goals: { home: 1.5, away: 1 },
          one_x_two: { home: 0.5, draw: 0.28, away: 0.22 },
          markets: { over_2_5: 0.48, btts_yes: 0.5 },
          top_scorelines: [],
        },
      }
    }
    if (path.endsWith('/odds/matches/1/value')) {
      body = {
        match_id: 1,
        prediction_id: 1,
        model_version: 'poisson-v1',
        markets: [{ id: 1, provider: 'betplay', market_key: '1X2', selection_key: 'HOME', line: null, decimal_odd: 2.2, implied_probability: 0.45, fair_implied_probability: 0.42, overround: 1.08, model_probability: 0.52, expected_value: 0.144, edge: 0.1 }],
      }
    }
    await route.fulfill({ json: body })
  })
}

test.beforeEach(async ({ page }) => {
  await mockApi(page)
  await page.addInitScript(() => window.localStorage.setItem('fais_access_token', 'test-token'))
})

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

test('administrator can access every control-plane section', async ({ page }) => {
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Administración', exact: true })).toBeVisible()
  await expect(page.getByText('5.490')).toBeVisible()
  for (const section of ['catalogo', 'ingestas', 'calidad', 'usuarios', 'modelos', 'auditoria', 'despliegue']) {
    await page.getByRole('button', { name: section }).click()
  }
  await expect(page.getByText('Preflight de producción')).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  expect(overflow).toBe(false)
  const results = await new AxeBuilder({ page }).analyze()
  const serious = results.violations.filter((violation) =>
    ['critical', 'serious'].includes(violation.impact ?? ''),
  )
  expect(serious).toEqual([])
})

test('role guard keeps a regular user out of administration', async ({ page }) => {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({
    json: {
      id: 2,
      email: 'user@example.com',
      display_name: 'Regular user',
      role: 'USER',
      active: 1,
      created_at: '2026-10-19T00:00:00Z',
    },
  }))
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { name: 'Panorama operativo' })).toBeVisible()
})

test('analyst workspace and odds terminal are interactive', async ({ page }) => {
  await page.goto('/analyst')
  await expect(page.getByRole('heading', { name: 'Mesa de análisis' })).toBeVisible()
  await page.getByLabel('Partido').selectOption('1')
  await page.getByRole('button', { name: 'Monte Carlo' }).click()
  await expect(page.getByText('50.00%').first()).toBeVisible()
  await page.goto('/odds')
  await page.getByLabel('Partido para analizar cuotas').selectOption('1')
  await expect(page.getByText('14.40%')).toBeVisible()
})

test('interactive product demo works without backend data', async ({ page }, testInfo) => {
  await page.goto('/demo')
  await expect(page.getByRole('heading', { name: 'Inteligencia de partido' })).toBeVisible()
  await expect(page.getByText('Arsenal', { exact: false }).first()).toBeVisible()

  await page.getByLabel('Filtrar liga').selectOption('Primera A')
  await expect(page.getByText('Atlético Nacional', { exact: false }).first()).toBeVisible()
  await expect(page.getByText('Real Madrid', { exact: false })).toHaveCount(0)

  await page.getByRole('button', { name: 'Simular escenario' }).click()
  await expect(page.getByRole('status')).toContainText('Simulación preparada')
  await page.getByRole('button', { name: 'Crear alerta de señal' }).click()
  await expect(page.getByRole('button', { name: 'Alerta activada' })).toBeVisible()

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  expect(overflow).toBe(false)
  const results = await new AxeBuilder({ page }).analyze()
  const serious = results.violations.filter((violation) =>
    ['critical', 'serious'].includes(violation.impact ?? ''),
  )
  expect(serious).toEqual([])
  await page.screenshot({ path: testInfo.outputPath('demo.png'), fullPage: true })
})
