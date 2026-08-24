const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const baseUrl = process.env.HR_DEMO_URL || 'http://127.0.0.1:8000'
const employeeNumber = process.env.HR_DEMO_USER
const password = process.env.HR_DEMO_PASSWORD

if (!employeeNumber || !password) {
  throw new Error('请通过 HR_DEMO_USER 和 HR_DEMO_PASSWORD 提供演示账号')
}

const wait = (page, milliseconds) => page.waitForTimeout(milliseconds)

async function showChapter(page, title, subtitle, milliseconds = 1500) {
  await page.evaluate(({ title, subtitle }) => {
    document.querySelector('#demo-chapter')?.remove()
    const overlay = document.createElement('div')
    overlay.id = 'demo-chapter'
    overlay.innerHTML = `<div><span>PULSE HR · PRODUCT TOUR</span><h2>${title}</h2><p>${subtitle}</p></div>`
    overlay.style.cssText = [
      'position:fixed', 'inset:0', 'z-index:99999', 'display:grid', 'place-items:center',
      'color:#fff', 'text-align:center',
      'background:radial-gradient(circle at 50% 30%,rgba(57,99,220,.58),transparent 35%),linear-gradient(145deg,rgba(12,19,34,.97),rgba(24,40,72,.97))',
      'font-family:"Segoe UI","Microsoft YaHei UI",sans-serif',
      'animation:demoFade .25s ease-out',
    ].join(';')
    const style = document.createElement('style')
    style.id = 'demo-chapter-style'
    style.textContent = `
      @keyframes demoFade { from { opacity: 0 } to { opacity: 1 } }
      #demo-chapter span { color:#9eb8ff;font-size:13px;font-weight:700;letter-spacing:.18em }
      #demo-chapter h2 { margin:18px 0 10px;font-size:48px;letter-spacing:-.04em }
      #demo-chapter p { margin:0;color:#c2cce0;font-size:18px }
    `
    document.head.appendChild(style)
    document.body.appendChild(overlay)
  }, { title, subtitle })
  await wait(page, milliseconds)
  await page.evaluate(() => {
    document.querySelector('#demo-chapter')?.remove()
    document.querySelector('#demo-chapter-style')?.remove()
  })
}

async function clickNavigation(page, label) {
  await page.getByRole('button', { name: new RegExp(label) }).click()
  await page.locator('.topbar h1').filter({ hasText: label }).waitFor()
  await wait(page, 2200)
}

async function main() {
  const outputDir = path.resolve('output', 'demo-recording')
  fs.mkdirSync(outputDir, { recursive: true })

  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  })
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    recordVideo: { dir: outputDir, size: { width: 1440, height: 900 } },
  })
  const page = await context.newPage()
  const video = page.video()

  await page.goto(baseUrl, { waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: '登录 HR 工作台' }).waitFor()
  await showChapter(page, 'PULSE HR', '企业人力资源 Agent 操作系统', 1900)
  await wait(page, 900)

  await page.getByLabel('工号').fill(employeeNumber)
  await wait(page, 500)
  await page.getByLabel('密码').fill(password)
  await wait(page, 700)
  await page.getByRole('button', { name: '安全登录' }).click()
  await page.locator('.topbar h1').filter({ hasText: '工作台' }).waitFor()
  await page.locator('.loading-state').waitFor({ state: 'hidden' })
  await wait(page, 2800)

  await showChapter(page, '智能工作台', '全局业务数据与 Agent 能力一览', 1300)
  await wait(page, 2300)

  await clickNavigation(page, '招聘管理')
  await page.getByRole('button', { name: '新建职位' }).click()
  await page.getByRole('heading', { name: '人才引进' }).waitFor()
  await wait(page, 2600)
  await page.locator('.modal-close').click()
  await wait(page, 900)
  await page.getByRole('button', { name: '录入候选人' }).click()
  await page.getByRole('heading', { name: '录入候选人' }).waitFor()
  await wait(page, 2200)
  await page.locator('.modal-close').click()

  await clickNavigation(page, '员工中心')
  await page.getByRole('button', { name: '办理新员工入职' }).click()
  await page.getByRole('heading', { name: '办理员工入职' }).waitFor()
  await wait(page, 2300)
  await page.locator('.modal-close').click()

  await clickNavigation(page, 'HR 助手')
  await page.getByRole('button', { name: '年假如何申请？' }).click()
  await wait(page, 2200)

  await clickNavigation(page, '绩效发展')
  await clickNavigation(page, '系统管理')

  await showChapter(page, '安全、清晰、可追溯', 'LangChain 驱动的人力资源智能协作平台', 2400)

  await page.close()
  await context.close()
  const recordedPath = await video.path()
  const webmPath = path.resolve('output', 'PULSE_HR_项目演示.webm')
  fs.copyFileSync(recordedPath, webmPath)
  await browser.close()

  console.log(JSON.stringify({ webmPath, durationTarget: '约40秒' }))
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
