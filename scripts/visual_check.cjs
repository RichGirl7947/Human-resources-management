const { chromium } = require('playwright')
const path = require('path')

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1050 }, deviceScaleFactor: 1 })
  const errors = []
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  page.on('pageerror', (error) => errors.push(error.message))

  await page.goto('http://127.0.0.1:8000', { waitUntil: 'networkidle' })
  await page.locator('h1').filter({ hasText: '工作台' }).waitFor()
  await page.screenshot({ path: path.resolve('output/hr_agent_dashboard.png'), fullPage: true })

  await page.getByRole('button', { name: /招聘管理/ }).click()
  await page.getByText('从需求到 Offer，全程可解释').waitFor()
  await page.getByRole('button', { name: '新建职位' }).click()
  await page.getByText('新建招聘需求').waitFor()

  console.log(JSON.stringify({
    title: await page.title(),
    dashboardVisible: true,
    recruitmentInteraction: true,
    consoleErrors: errors,
    screenshot: path.resolve('output/hr_agent_dashboard.png'),
  }))
  await browser.close()
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
