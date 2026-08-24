<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api, clearAccessToken, getAccessToken, setAccessToken } from './api'
import type {
  AgentInfo,
  AuditLog,
  AuthResponse,
  AuthUser,
  Candidate,
  DashboardData,
  Employee,
  HRRequest,
  InterviewNotification,
  Job,
  LangChainChatResponse,
  LangChainStatus,
  OffboardingCase,
  PerformanceReview,
  UserRole,
} from './types'

type ViewKey = 'dashboard' | 'recruitment' | 'employees' | 'assistant' | 'performance' | 'offboarding' | 'admin'
type ModalKey = 'profile' | 'job' | 'candidate' | 'employee' | 'workflow' | 'review' | 'offboarding' | 'user' | null

const navItems: Array<{ key: ViewKey; label: string; mark: string; description: string }> = [
  { key: 'dashboard', label: '工作台', mark: '概', description: '全局经营视图' },
  { key: 'recruitment', label: '招聘管理', mark: '招', description: '需求与候选人' },
  { key: 'employees', label: '员工中心', mark: '员', description: '入职与档案' },
  { key: 'assistant', label: 'HR 助手', mark: '问', description: '问答与流程' },
  { key: 'performance', label: '绩效发展', mark: '绩', description: '评审与成长' },
  { key: 'offboarding', label: '离职管理', mark: '离', description: '审批与交接' },
  { key: 'admin', label: '系统管理', mark: '管', description: '账号与审计' },
]

const authReady = ref(false)
const authBusy = ref(false)
const authError = ref('')
const bootstrapRequired = ref(false)
const bootstrapTokenRequired = ref(false)
const currentUser = ref<AuthUser | null>(null)
const activeView = ref<ViewKey>('dashboard')
const modal = ref<ModalKey>(null)
const loading = ref(true)
const busy = ref(false)
const toast = ref('')
const toastError = ref(false)

const dashboard = reactive<DashboardData>({
  requisitions: 0,
  candidates: 0,
  employees: 0,
  hr_requests: 0,
  pending_human_actions: 0,
  performance_reviews: 0,
  offboarding_cases: 0,
})
const langchain = reactive<LangChainStatus>({
  framework: 'LangChain', version: '', runtime: 'LCEL', supervisor_enabled: false,
  provider: null, model: null, base_url: null, api_key_configured: false, tools: [],
})
const agents = ref<AgentInfo[]>([])
const jobs = ref<Job[]>([])
const candidates = ref<Candidate[]>([])
const interviewNotifications = ref<InterviewNotification[]>([])
const employees = ref<Employee[]>([])
const requests = ref<HRRequest[]>([])
const reviews = ref<PerformanceReview[]>([])
const offboardingCases = ref<OffboardingCase[]>([])
const systemUsers = ref<AuthUser[]>([])
const auditLogs = ref<AuditLog[]>([])

const loginForm = reactive({ email: '', password: '' })
const bootstrapForm = reactive({
  full_name: '', email: '', password: '', bootstrap_token: '', role: 'admin' as UserRole,
})
const userForm = reactive({
  full_name: '', email: '', password: '', role: 'viewer' as UserRole,
})

const jobForm = reactive({
  title: 'Python 后端工程师',
  department: '研发中心',
  headcount: 1,
  salary: '15K-25K·14薪',
  education: '本科',
  experience: '3-5年',
  responsibilities: '开发 HR Agent API\n维护数据服务\n编写自动化测试',
  skills: 'Python, FastAPI, SQLAlchemy, pytest',
})
const candidateForm = reactive({ job_id: 0, name: '', email: '', phone: '', resume_text: '' })
const employeeForm = reactive({ name: '', email: '', department: '', position: '', start_date: today() })
const workflowForm = reactive({ employee_id: 0, content: '' })
const reviewForm = reactive({ employee_id: 0, cycle: '2026-H2', goals: '', score: 3.5, manager_feedback: '' })
const offboardingForm = reactive({ employee_id: 0, reason: '', last_working_day: '' })

const chatInput = ref('')
const chatEmployeeId = ref(0)
const messages = ref<Array<{ role: 'assistant' | 'user'; text: string; source?: string }>>([
  { role: 'assistant', text: '你好，我是 HR 政策助手。你可以问我年假、病假、加班、报销、入职或离职相关问题。' },
])

const visibleNavItems = computed(() => navItems.filter((item) => item.key !== 'admin' || currentUser.value?.role === 'admin'))
const currentNav = computed(() => visibleNavItems.value.find((item) => item.key === activeView.value) ?? visibleNavItems.value[0])
const isAdmin = computed(() => currentUser.value?.role === 'admin')
const canRecruit = computed(() => ['admin', 'hr', 'recruiter'].includes(currentUser.value?.role ?? ''))
const canManageHR = computed(() => ['admin', 'hr'].includes(currentUser.value?.role ?? ''))
const activeEmployees = computed(() => employees.value.filter((item) => ['active', 'onboarding', 'improvement'].includes(item.status)))
const currentEmployee = computed(() => activeEmployees.value[0] ?? employees.value[0] ?? null)
const selectedCandidates = computed(() => candidates.value
  .filter((item) => item.selection_rank !== null)
  .sort((a, b) => (a.selection_rank ?? 99) - (b.selection_rank ?? 99)))
const maxFlowCount = computed(() => Math.max(dashboard.requisitions, dashboard.candidates, dashboard.employees, dashboard.performance_reviews, dashboard.offboarding_cases, 1))
const pendingItems = computed(() => {
  const items: Array<{ type: string; title: string; meta: string; action: () => Promise<unknown> }> = []
  if (canRecruit.value) {
    items.push(...jobs.value.filter((item) => item.status === 'pending_approval').map((item) => ({ type: '用人审批', title: item.title, meta: item.department, action: () => approveJob(item.id) })))
    items.push(...candidates.value.filter((item) => ['interview', 'human_review'].includes(item.status)).map((item) => ({ type: '录用决策', title: item.name, meta: item.recommendation, action: () => decideCandidate(item.id, true) })))
  }
  if (canManageHR.value) {
    items.push(...requests.value.filter((item) => ['pending_approval', 'pending_review'].includes(item.status)).map((item) => ({ type: 'HR 审批', title: requestTypeLabel(item.request_type), meta: item.content, action: () => decideRequest(item.id, true) })))
    items.push(...offboardingCases.value.filter((item) => item.status === 'pending_approval').map((item) => ({ type: '离职审批', title: employeeName(item.employee_id), meta: item.reason, action: () => decideOffboarding(item.id, true) })))
  }
  return items.slice(0, 6)
})

const flowMetrics = computed(() => [
  { label: '招聘需求', value: dashboard.requisitions, color: '#2563eb' },
  { label: '候选人才', value: dashboard.candidates, color: '#7c3aed' },
  { label: '员工档案', value: dashboard.employees, color: '#0f9f8f' },
  { label: '绩效评审', value: dashboard.performance_reviews, color: '#e69a17' },
  { label: '离职流程', value: dashboard.offboarding_cases, color: '#e45f44' },
])

function today() {
  return new Date().toISOString().slice(0, 10)
}

function employeeNumber(id: number) {
  return `HR-${String(id).padStart(6, '0')}`
}

function tenureLabel(startDate: string) {
  const start = new Date(`${startDate}T00:00:00`)
  const now = new Date()
  let months = (now.getFullYear() - start.getFullYear()) * 12 + now.getMonth() - start.getMonth()
  if (now.getDate() < start.getDate()) months -= 1
  if (months < 0) return '尚未入职'
  const years = Math.floor(months / 12)
  const remainingMonths = months % 12
  if (!years) return `${remainingMonths} 个月`
  return remainingMonths ? `${years} 年 ${remainingMonths} 个月` : `${years} 年`
}

function showToast(message: string, isError = false) {
  toast.value = message
  toastError.value = isError
  window.setTimeout(() => {
    if (toast.value === message) toast.value = ''
  }, 3200)
}

async function initializeAuth() {
  authReady.value = false
  try {
    const bootstrap = await api.get<{ required: boolean; token_required: boolean }>('/api/v1/auth/bootstrap-status')
    bootstrapRequired.value = bootstrap.required
    bootstrapTokenRequired.value = bootstrap.token_required
    if (getAccessToken()) {
      currentUser.value = await api.get<AuthUser>('/api/v1/auth/me')
      await loadAll()
    }
  } catch {
    clearAccessToken()
    currentUser.value = null
  } finally {
    authReady.value = true
  }
}

async function submitLogin() {
  authBusy.value = true
  authError.value = ''
  try {
    const response = await api.post<AuthResponse>('/api/v1/auth/login', loginForm)
    setAccessToken(response.access_token)
    currentUser.value = response.user
    await loadAll()
  } catch (error) {
    authError.value = error instanceof Error ? error.message : '登录失败'
  } finally {
    authBusy.value = false
  }
}

async function submitBootstrap() {
  authBusy.value = true
  authError.value = ''
  try {
    const response = await api.post<AuthResponse>('/api/v1/auth/bootstrap', bootstrapForm)
    setAccessToken(response.access_token)
    currentUser.value = response.user
    bootstrapRequired.value = false
    await loadAll()
  } catch (error) {
    const message = error instanceof Error ? error.message : '初始化失败'
    if (message === '系统已经完成管理员初始化') {
      loginForm.email = bootstrapForm.email
      bootstrapRequired.value = false
      authError.value = '管理员初始化已完成，请使用工号和密码登录。'
    } else {
      authError.value = message
    }
  } finally {
    authBusy.value = false
  }
}

function logout() {
  clearAccessToken()
  currentUser.value = null
  activeView.value = 'dashboard'
  systemUsers.value = []
  auditLogs.value = []
}

function handleAuthExpired() {
  currentUser.value = null
  authError.value = '登录已过期，请重新登录'
}

async function loadAll() {
  loading.value = true
  try {
    const [metrics, chainStatus, agentList, jobList, candidateList, notificationList, employeeList, requestList, reviewList, offboardingList] = await Promise.all([
      api.get<DashboardData>('/api/v1/dashboard'),
      api.get<LangChainStatus>('/api/v1/langchain/status'),
      api.get<AgentInfo[]>('/api/v1/agents'),
      api.get<Job[]>('/api/v1/recruitment/requisitions'),
      api.get<Candidate[]>('/api/v1/recruitment/candidates'),
      api.get<InterviewNotification[]>('/api/v1/recruitment/interview-notifications'),
      api.get<Employee[]>('/api/v1/employees'),
      api.get<HRRequest[]>('/api/v1/hr/requests'),
      api.get<PerformanceReview[]>('/api/v1/performance/reviews'),
      api.get<OffboardingCase[]>('/api/v1/offboarding'),
    ])
    Object.assign(dashboard, metrics)
    Object.assign(langchain, chainStatus)
    agents.value = agentList
    jobs.value = jobList
    candidates.value = candidateList
    interviewNotifications.value = notificationList
    employees.value = employeeList
    requests.value = requestList
    reviews.value = reviewList
    offboardingCases.value = offboardingList
    if (currentUser.value?.role === 'admin') {
      const [userList, logs] = await Promise.all([
        api.get<AuthUser[]>('/api/v1/admin/users'),
        api.get<AuditLog[]>('/api/v1/admin/audit-logs?limit=100'),
      ])
      systemUsers.value = userList
      auditLogs.value = logs
    }
    if (!candidateForm.job_id && jobList[0]) candidateForm.job_id = jobList[0].id
    const firstEmployee = activeEmployees.value[0]
    if (firstEmployee) {
      if (!workflowForm.employee_id) workflowForm.employee_id = firstEmployee.id
      if (!reviewForm.employee_id) reviewForm.employee_id = firstEmployee.id
      if (!offboardingForm.employee_id) offboardingForm.employee_id = firstEmployee.id
      if (!chatEmployeeId.value) chatEmployeeId.value = firstEmployee.id
    }
  } catch (error) {
    showToast(error instanceof Error ? error.message : '数据加载失败', true)
  } finally {
    loading.value = false
  }
}

async function runAction(action: () => Promise<unknown>, success: string) {
  busy.value = true
  try {
    await action()
    modal.value = null
    showToast(success)
    await loadAll()
  } catch (error) {
    showToast(error instanceof Error ? error.message : '操作失败', true)
  } finally {
    busy.value = false
  }
}

function openModal(kind: ModalKey) {
  modal.value = kind
}

function splitLines(value: string) {
  return value.split(/\n+/).map((item) => item.trim()).filter(Boolean)
}

function splitSkills(value: string) {
  return value.split(/[,，、]+/).map((item) => item.trim()).filter(Boolean)
}

function createJob() {
  return runAction(
    () => api.post('/api/v1/recruitment/requisitions', {
      title: jobForm.title,
      department: jobForm.department,
      headcount: jobForm.headcount,
      salary: jobForm.salary,
      education: jobForm.education,
      experience: jobForm.experience,
      responsibilities: splitLines(jobForm.responsibilities),
      required_skills: splitSkills(jobForm.skills),
    }),
    '职位画像已生成，等待审批',
  )
}

function approveJob(id: number) {
  return runAction(() => api.post(`/api/v1/recruitment/requisitions/${id}/approve`), '招聘需求已批准并发布')
}

function createCandidate() {
  return runAction(
    () => api.post(`/api/v1/recruitment/requisitions/${candidateForm.job_id}/candidates`, {
      name: candidateForm.name,
      email: candidateForm.email,
      phone: candidateForm.phone,
      resume_text: candidateForm.resume_text,
    }),
    '简历筛选完成',
  )
}

function finalizeScreening(jobId: number) {
  return runAction(
    () => api.post(`/api/v1/recruitment/requisitions/${jobId}/finalize-screening`),
    'AI 已选出匹配度最高的候选人，面试通知已进入两天内发送队列',
  )
}

function decideCandidate(id: number, approved: boolean) {
  return runAction(
    () => api.post(`/api/v1/recruitment/candidates/${id}/decision`, { approved, comment: approved ? '确认录用' : '进入人才库' }),
    approved ? '已确认录用' : '候选人已进入人才库',
  )
}

function createEmployee() {
  return runAction(() => api.post('/api/v1/onboarding/employees', employeeForm), '员工档案与入职任务已创建')
}

function createSystemUser() {
  return runAction(() => api.post('/api/v1/admin/users', userForm), '系统账号已创建')
}

function toggleSystemUser(id: number) {
  return runAction(() => api.post(`/api/v1/admin/users/${id}/toggle`), '账号状态已更新')
}

function completeOnboarding(id: number) {
  return runAction(() => api.post(`/api/v1/onboarding/employees/${id}/complete`), '入职流程已完成')
}

async function sendQuestion() {
  const question = chatInput.value.trim()
  if (!question || busy.value) return
  messages.value.push({ role: 'user', text: question })
  chatInput.value = ''
  busy.value = true
  try {
    if (langchain.supervisor_enabled) {
      const response = await api.post<LangChainChatResponse>('/api/v1/langchain/chat', {
        message: question,
        thread_id: `web-${chatEmployeeId.value || 'guest'}`,
      })
      messages.value.push({ role: 'assistant', text: response.answer, source: `LangChain Supervisor · ${response.model}` })
    } else {
      const response = await api.post<HRRequest>('/api/v1/hr/ask', {
        employee_id: chatEmployeeId.value || null,
        question,
      })
      messages.value.push({
        role: 'assistant',
        text: response.result.data.answer ?? response.result.summary,
        source: response.result.data.source ?? 'LangChain LCEL',
      })
    }
    await loadAll()
  } catch (error) {
    messages.value.push({ role: 'assistant', text: error instanceof Error ? error.message : '暂时无法回答，请稍后再试。' })
  } finally {
    busy.value = false
  }
}

function createWorkflow() {
  return runAction(() => api.post('/api/v1/hr/workflows', {
    employee_id: workflowForm.employee_id || null,
    content: workflowForm.content,
  }), 'HR 流程已识别并发起')
}

function decideRequest(id: number, approved: boolean) {
  return runAction(
    () => api.post(`/api/v1/hr/requests/${id}/decision`, { approved, comment: approved ? '审批通过' : '审批退回' }),
    approved ? '流程审批通过' : '流程已退回',
  )
}

function createReview() {
  return runAction(() => api.post('/api/v1/performance/reviews', {
    employee_id: reviewForm.employee_id,
    cycle: reviewForm.cycle,
    goals: splitLines(reviewForm.goals),
    score: reviewForm.score,
    manager_feedback: reviewForm.manager_feedback,
  }), '绩效发展建议已生成')
}

function createOffboarding() {
  return runAction(() => api.post('/api/v1/offboarding', {
    employee_id: offboardingForm.employee_id,
    reason: offboardingForm.reason,
    last_working_day: offboardingForm.last_working_day || null,
  }), '离职交接清单已生成')
}

function decideOffboarding(id: number, approved: boolean) {
  return runAction(
    () => api.post(`/api/v1/offboarding/${id}/decision`, { approved, comment: approved ? '批准离职' : '退回申请' }),
    approved ? '离职申请已批准' : '离职申请已退回',
  )
}

function completeOffboarding(id: number) {
  return runAction(() => api.post(`/api/v1/offboarding/${id}/complete`), '交接完成，员工档案已归档')
}

function employeeName(id: number | null) {
  if (!id) return '访客'
  return employees.value.find((item) => item.id === id)?.name ?? `员工 #${id}`
}

function jobTitle(id: number) {
  return jobs.value.find((item) => item.id === id)?.title ?? `职位 #${id}`
}

function candidateCount(jobId: number) {
  return candidates.value.filter((item) => item.job_id === jobId).length
}

function jobScreeningFinalized(jobId: number) {
  return interviewNotifications.value.some((item) => item.job_id === jobId)
}

function notificationSummary(candidateId: number) {
  const items = interviewNotifications.value.filter((item) => item.candidate_id === candidateId)
  if (items.length && items.every((item) => item.status === 'sent')) return '邮件和短信已发送'
  if (items.some((item) => item.status === 'failed')) return '存在发送失败'
  if (items.some((item) => item.status === 'pending_configuration')) return '等待配置通知通道'
  if (items.length) return '两天内自动发送'
  return '通知待生成'
}

function notificationClass(candidateId: number) {
  const summary = notificationSummary(candidateId)
  if (summary.includes('已发送')) return 'success'
  if (summary.includes('失败')) return 'danger'
  return 'warning'
}

function formatDateTime(value: string | null) {
  if (!value) return '待定'
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}

function formatDate(value: string | null) {
  if (!value) return '待定'
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' }).format(new Date(value))
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    pending_approval: '待审批', published: '招聘中', interviewing: '面试中', offered: '已录用', talent_pool: '人才库',
    interview: '进入面试', human_review: '待复核', rejected: '已拒绝', screened: 'AI已评分',
    onboarding: '入职中', active: '在职', improvement: '改进期', offboarding: '离职中', exited: '已离职',
    completed: '已完成', pending_review: '待复核', approved: '已通过',
  }
  return labels[status] ?? status
}

function statusClass(status: string) {
  if (['active', 'completed', 'approved', 'published', 'offered'].includes(status)) return 'success'
  if (['rejected', 'exited'].includes(status)) return 'danger'
  if (['pending_approval', 'pending_review', 'human_review', 'interview', 'onboarding', 'improvement', 'offboarding'].includes(status)) return 'warning'
  return 'neutral'
}

function requestTypeLabel(type: string) {
  const labels: Record<string, string> = {
    policy_question: '政策咨询', leave: '请假', expense: '报销', transfer: '调岗', overtime: '加班',
    offboarding: '离职', certificate: '证明申请', general: '综合服务',
  }
  return labels[type] ?? type
}

function roleLabel(role: string) {
  const labels: Record<string, string> = {
    admin: '管理员', hr: 'HR', recruiter: '招聘人员', viewer: '只读人员', anonymous: '未登录',
  }
  return labels[role] ?? role
}

function navTo(view: ViewKey) {
  activeView.value = view
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

onMounted(() => {
  window.addEventListener('hr-auth-expired', handleAuthExpired)
  initializeAuth()
})
onBeforeUnmount(() => window.removeEventListener('hr-auth-expired', handleAuthExpired))
</script>

<template>
  <div v-if="!authReady" class="auth-loading"><div class="loader"></div><span>正在验证安全会话...</span></div>
  <div v-else-if="!currentUser" class="login-page">
    <section class="login-brand-panel"><div class="brand-mark large"><span></span><span></span><span></span></div><p>PULSE HR</p><h1>让每一次人才决策<br />安全、清晰、可追溯</h1></section>
    <section class="login-form-panel">
      <form v-if="bootstrapRequired" class="auth-form" @submit.prevent="submitBootstrap">
        <span class="section-kicker">FIRST-TIME SETUP</span><h2>初始化管理员</h2><p>系统尚未创建账号，请设置首位管理员。</p>
        <label>姓名<input v-model="bootstrapForm.full_name" required autocomplete="name" /></label>
        <label>工号<input v-model="bootstrapForm.email" type="text" required minlength="2" maxlength="64" autocomplete="username" /></label>
        <label>密码<input v-model="bootstrapForm.password" type="password" required minlength="12" autocomplete="new-password" /><small>密码至少12位，并包含大小写字母和数字。</small></label>
        <label v-if="bootstrapTokenRequired">生产初始化令牌<input v-model="bootstrapForm.bootstrap_token" type="password" required autocomplete="off" /></label>
        <p v-if="authError" class="auth-error">{{ authError }}</p><button class="button button-primary full" :disabled="authBusy">{{ authBusy ? '正在初始化...' : '创建管理员并进入系统' }}</button>
      </form>
      <form v-else class="auth-form" @submit.prevent="submitLogin">
        <h2>登录 HR 工作台</h2>
        <input v-model="loginForm.email" type="text" required autocomplete="username" aria-label="工号" />
        <label>密码<input v-model="loginForm.password" type="password" required autocomplete="current-password" /></label>
        <p v-if="authError" class="auth-error">{{ authError }}</p><button class="button button-primary full" :disabled="authBusy">{{ authBusy ? '正在验证...' : '安全登录' }}</button>
      </form>
    </section>
  </div>
  <div v-else class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark"><span></span><span></span><span></span></div>
        <div><strong>PULSE HR</strong><small>AGENT OPERATING SYSTEM</small></div>
      </div>

      <nav class="nav-list">
        <button
          v-for="item in visibleNavItems"
          :key="item.key"
          class="nav-item"
          :class="{ active: activeView === item.key }"
          @click="navTo(item.key)"
        >
          <span class="nav-mark">{{ item.mark }}</span>
          <span><strong>{{ item.label }}</strong><small>{{ item.description }}</small></span>
        </button>
      </nav>

      <button class="sidebar-agent-card" @click="openModal('profile')">
        <div class="avatar sidebar-avatar">HR</div>
        <div><strong>{{ currentEmployee?.name || '员工个人信息' }}</strong><span>{{ currentEmployee ? employeeNumber(currentEmployee.id) : '暂未关联员工档案' }}</span></div>
      </button>
    </aside>

    <main class="main-content">
      <header class="topbar">
        <div>
          <p class="eyebrow">HR AGENT PLATFORM</p>
          <h1>{{ currentNav.label }}</h1>
        </div>
          <div class="topbar-actions">
            <button class="icon-button" title="刷新数据" @click="loadAll">↻</button>
            <button class="topbar-consult" @click="navTo('assistant')">咨询</button>
            <div class="signed-user"><strong>{{ currentUser.full_name }}</strong><span>{{ roleLabel(currentUser.role) }}</span></div><button class="logout-button" @click="logout">退出</button>
          </div>
      </header>

      <div v-if="loading" class="loading-state">
        <div class="loader"></div><span>正在同步 HR 数据...</span>
      </div>

      <template v-else>
        <section v-if="activeView === 'dashboard'" class="view-stack">
          <article class="hero-card">
            <div class="hero-copy">
              <span class="hero-label">LANGCHAIN HR AGENT ORCHESTRATION</span>
              <h2>早上好，HR 团队</h2>
              <p>今天有 <b>{{ dashboard.pending_human_actions }}</b> 项事务等待人工确认，Agent 已完成前置分析与流程编排。</p>
            </div>
            <div class="hero-orbit" aria-hidden="true">
              <div class="orbit orbit-one"></div><div class="orbit orbit-two"></div>
              <div class="core"><span>AI</span><small>{{ agents.length }} AGENTS</small></div>
            </div>
          </article>

          <div class="metric-grid">
            <article class="metric-card blue"><span class="metric-icon">招</span><div><small>人才引进</small><strong>{{ dashboard.requisitions }}</strong><p>{{ dashboard.candidates }} 位候选人</p></div></article>
            <article class="metric-card teal"><span class="metric-icon">员</span><div><small>员工总数</small><strong>{{ dashboard.employees }}</strong><p>{{ activeEmployees.length }} 人在岗/入职</p></div></article>
            <article class="metric-card amber"><span class="metric-icon">审</span><div><small>待人工处理</small><strong>{{ dashboard.pending_human_actions }}</strong><p>Agent 已完成预处理</p></div></article>
            <article class="metric-card violet"><span class="metric-icon">问</span><div><small>HR 服务</small><strong>{{ dashboard.hr_requests }}</strong><p>政策问答与流程</p></div></article>
          </div>

          <div class="dashboard-grid">
            <article class="panel flow-panel">
              <div class="panel-heading"><div><span class="section-kicker">LIFECYCLE</span><h3>员工全生命周期</h3></div><span class="muted">实时业务数据</span></div>
              <div class="flow-chart">
                <div v-for="metric in flowMetrics" :key="metric.label" class="flow-row">
                  <span>{{ metric.label }}</span>
                  <div class="flow-track"><i :style="{ width: `${Math.max(metric.value / maxFlowCount * 100, metric.value ? 12 : 2)}%`, background: metric.color }"></i></div>
                  <b>{{ metric.value }}</b>
                </div>
              </div>
              <div class="lifecycle-strip">
                <template v-for="(step, index) in ['招聘', '入职', '在职服务', '绩效发展', '离职']" :key="step">
                  <span>{{ step }}</span><i v-if="index < 4">→</i>
                </template>
              </div>
            </article>

            <article class="panel pending-panel">
              <div class="panel-heading"><div><span class="section-kicker">HUMAN IN THE LOOP</span><h3>待确认事项</h3></div><span class="count-badge">{{ pendingItems.length }}</span></div>
              <div v-if="pendingItems.length" class="pending-list">
                <div v-for="(item, index) in pendingItems" :key="`${item.type}-${index}`" class="pending-item">
                  <span class="pending-index">{{ String(index + 1).padStart(2, '0') }}</span>
                  <div><small>{{ item.type }}</small><strong>{{ item.title }}</strong><p>{{ item.meta }}</p></div>
                  <button :disabled="busy" @click="item.action">处理</button>
                </div>
              </div>
              <div v-else class="empty-mini"><span>✓</span><p>暂无待确认事项</p></div>
            </article>
          </div>

          <article class="panel agent-panel">
              <div class="panel-heading"><div><span class="section-kicker">AGENT NETWORK</span><h3>Agent 能力矩阵</h3></div><span class="online-label"><i></i> {{ langchain.runtime }}</span></div>
            <div class="agent-grid">
              <div v-for="(agent, index) in agents" :key="agent.name" class="agent-item">
                <span class="agent-number">A{{ String(index + 1).padStart(2, '0') }}</span>
                <div><strong>{{ agent.name }}</strong><p>{{ agent.description }}</p></div><i class="agent-live"></i>
              </div>
            </div>
          </article>
        </section>

        <section v-else-if="activeView === 'recruitment'" class="view-stack">
          <div class="view-intro actions-only">
            <div v-if="canRecruit" class="button-group"><button class="button button-secondary" @click="openModal('candidate')">录入候选人</button><button class="button button-primary" @click="openModal('job')">新建职位</button></div><span v-else class="muted">当前账号为只读权限</span>
          </div>
          <article class="panel">
            <div class="panel-heading"><h3>招聘需求</h3><span class="muted">{{ jobs.length }} 个职位</span></div>
            <div v-if="jobs.length" class="record-grid">
              <div v-for="job in jobs" :key="job.id" class="record-card">
                <div class="record-top"><span class="record-icon blue">{{ job.title.slice(0, 1) }}</span><span class="status-pill" :class="statusClass(job.status)">{{ statusLabel(job.status) }}</span></div>
                <h3>{{ job.title }}</h3><p>{{ job.department }} · {{ job.headcount }} 个 HC</p>
                <dl class="job-requirements"><div><dt>薪资</dt><dd>{{ job.salary }}</dd></div><div><dt>学历</dt><dd>{{ job.education }}</dd></div><div><dt>经验</dt><dd>{{ job.experience }}</dd></div></dl>
                <div class="tag-row"><span v-for="skill in job.required_skills.slice(0, 4)" :key="skill">{{ skill }}</span></div>
                <div class="record-footer"><small>{{ candidateCount(job.id) }} 份简历 · {{ formatDate(job.created_at) }} 创建</small><div v-if="canRecruit" class="job-card-actions"><button v-if="job.status === 'pending_approval'" :disabled="busy" @click="approveJob(job.id)">批准并发布</button><button class="finalize-screening-button" :disabled="busy || job.status === 'pending_approval' || !candidateCount(job.id) || jobScreeningFinalized(job.id)" :title="job.status === 'pending_approval' ? '请先批准并发布职位' : !candidateCount(job.id) ? '请先录入候选人简历' : jobScreeningFinalized(job.id) ? '该职位已完成筛选' : '按匹配度完成筛选'" @click="finalizeScreening(job.id)">{{ jobScreeningFinalized(job.id) ? '筛选已完成' : '完成筛选' }}</button></div><span v-else>只读</span></div>
              </div>
            </div>
            <div v-else class="empty-state"><span>招</span><h3>还没有招聘需求</h3><p>创建第一个职位，Agent 会自动生成职位画像。</p><button class="button button-primary" @click="openModal('job')">创建职位</button></div>
          </article>
          <article v-if="selectedCandidates.length" class="panel selection-panel">
            <div class="panel-heading"><div><span class="section-kicker">AI SHORTLIST</span><h3>进入面试的前五名</h3></div><span class="muted">HR 已同步 · 通知将在筛选完成后两天内自动发送</span></div>
            <div class="shortlist-grid">
              <div v-for="candidate in selectedCandidates" :key="candidate.id" class="shortlist-card">
                <span class="shortlist-rank">#{{ candidate.selection_rank }}</span>
                <div class="shortlist-person"><span>{{ candidate.name.slice(0, 1) }}</span><div><strong>{{ candidate.name }}</strong><small>{{ jobTitle(candidate.job_id) }}</small></div></div>
                <div class="shortlist-score"><strong>{{ candidate.score }}</strong><span>匹配度</span></div>
                <div class="shortlist-contact"><span>{{ candidate.email }}</span><span>{{ candidate.phone }}</span></div>
                <div class="shortlist-notice"><span class="status-pill" :class="notificationClass(candidate.id)">{{ notificationSummary(candidate.id) }}</span><small>{{ formatDateTime(interviewNotifications.find(item => item.candidate_id === candidate.id)?.scheduled_for ?? null) }}</small></div>
              </div>
            </div>
          </article>
          <article class="panel">
            <div class="panel-heading"><h3>候选人池</h3><span class="muted">{{ candidates.length }} 位候选人</span></div>
            <div class="table-wrap">
              <table v-if="candidates.length">
                <thead><tr><th>候选人</th><th>目标职位</th><th>匹配度</th><th>优势技能</th><th>状态</th><th>操作</th></tr></thead>
                <tbody><tr v-for="candidate in candidates" :key="candidate.id">
                  <td><div class="person-cell"><span>{{ candidate.name.slice(0, 1) }}</span><div><strong>{{ candidate.name }}</strong><small>{{ candidate.email }} · {{ candidate.phone }}</small></div></div></td>
                  <td>{{ jobTitle(candidate.job_id) }}</td>
                  <td><div class="score-cell"><b>{{ candidate.score }}</b><i><span :style="{ width: `${candidate.score}%` }"></span></i></div></td>
                  <td><div class="tag-row compact"><span v-for="skill in candidate.strengths.slice(0, 3)" :key="skill">{{ skill }}</span></div></td>
                  <td><span class="status-pill" :class="statusClass(candidate.status)">{{ statusLabel(candidate.status) }}</span></td>
                  <td><div v-if="canRecruit && ['interview', 'human_review'].includes(candidate.status)" class="row-actions"><button @click="decideCandidate(candidate.id, true)">录用</button><button class="text-danger" @click="decideCandidate(candidate.id, false)">人才库</button></div><span v-else class="muted">{{ canRecruit ? '已处理' : '只读' }}</span></td>
                </tr></tbody>
              </table>
              <div v-else class="empty-state small"><p>暂无候选人，请录入简历进行 Agent 筛选。</p></div>
            </div>
          </article>
        </section>

        <section v-else-if="activeView === 'employees'" class="view-stack">
          <div class="view-intro"><div><span class="section-kicker">PEOPLE DIRECTORY</span><h2>员工档案与入职旅程</h2></div><button v-if="canManageHR" class="button button-primary" @click="openModal('employee')">办理新员工入职</button></div>
          <div class="mini-stat-row"><div><strong>{{ employees.length }}</strong><span>员工档案</span></div><div><strong>{{ employees.filter(e => e.status === 'onboarding').length }}</strong><span>入职进行中</span></div><div><strong>{{ employees.filter(e => e.status === 'active').length }}</strong><span>正式在职</span></div><div><strong>{{ new Set(employees.map(e => e.department)).size }}</strong><span>业务部门</span></div></div>
          <article class="panel">
            <div class="employee-grid" v-if="employees.length">
              <div v-for="employee in employees" :key="employee.id" class="employee-card">
                <div class="employee-head"><div class="large-avatar">{{ employee.name.slice(-2) }}</div><span class="status-pill" :class="statusClass(employee.status)">{{ statusLabel(employee.status) }}</span></div>
                <h3>{{ employee.name }}</h3><p class="role">{{ employee.position }}</p>
                <dl><div><dt>部门</dt><dd>{{ employee.department }}</dd></div><div><dt>入职日期</dt><dd>{{ employee.start_date }}</dd></div><div><dt>邮箱</dt><dd>{{ employee.email }}</dd></div></dl>
                <div v-if="employee.status === 'onboarding'" class="onboarding-progress"><div><span>入职任务</span><b>0 / {{ employee.onboarding_tasks.length }}</b></div><i><span></span></i><button v-if="canManageHR" @click="completeOnboarding(employee.id)">确认资料已核验，完成入职</button></div>
              </div>
            </div>
            <div v-else class="empty-state"><span>员</span><h3>员工目录为空</h3><p>办理首位员工入职，系统会生成跨部门任务。</p><button class="button button-primary" @click="openModal('employee')">办理入职</button></div>
          </article>
        </section>

        <section v-else-if="activeView === 'assistant'" class="view-stack">
          <div class="view-intro"><div><span class="section-kicker">EMPLOYEE SERVICE</span><h2>HR 智能服务台</h2></div><button v-if="canManageHR" class="button button-primary" @click="openModal('workflow')">发起 HR 流程</button></div>
          <div class="assistant-layout">
            <article class="chat-panel panel">
              <div class="chat-header"><div class="bot-avatar">HR</div><div><strong>HR 智能助手</strong></div><select v-model.number="chatEmployeeId"><option :value="0">访客咨询</option><option v-for="employee in activeEmployees" :key="employee.id" :value="employee.id">{{ employee.name }}</option></select></div>
              <div class="chat-messages">
                <div v-for="(message, index) in messages" :key="index" class="message" :class="message.role"><div class="message-avatar">{{ message.role === 'assistant' ? 'AI' : '我' }}</div><div><p>{{ message.text }}</p><small v-if="message.source">依据：{{ message.source }}</small></div></div>
              </div>
              <div class="quick-prompts"><button v-for="prompt in ['年假如何申请？', '加班可以调休吗？', '报销需要哪些材料？']" :key="prompt" @click="chatInput = prompt">{{ prompt }}</button></div>
              <form v-if="canManageHR" class="chat-input" @submit.prevent="sendQuestion"><input v-model="chatInput" placeholder="输入你的 HR 政策问题..." /><button :disabled="busy || !chatInput.trim()">发送</button></form><p v-else class="readonly-hint">当前账号为只读权限，不能发起咨询。</p>
            </article>
            <article class="panel request-panel">
              <div class="panel-heading"><div><span class="section-kicker">REQUESTS</span><h3>历史记录</h3></div><span class="count-badge">{{ requests.length }}</span></div>
              <div v-if="requests.length" class="request-list">
                <div v-for="request in requests.slice(0, 8)" :key="request.id" class="request-item"><div class="request-line"><span>{{ requestTypeLabel(request.request_type) }}</span><span class="status-pill" :class="statusClass(request.status)">{{ statusLabel(request.status) }}</span></div><p>{{ request.content }}</p><small>{{ employeeName(request.employee_id) }} · {{ formatDate(request.created_at) }}</small><div v-if="['pending_approval', 'pending_review'].includes(request.status)" class="approval-actions"><button @click="decideRequest(request.id, true)">批准</button><button @click="decideRequest(request.id, false)">退回</button></div></div>
              </div>
              <div v-else class="empty-state small"><p>暂无服务记录</p></div>
            </article>
          </div>
        </section>

        <section v-else-if="activeView === 'performance'" class="view-stack">
          <div class="view-intro"><div><span class="section-kicker">PERFORMANCE & GROWTH</span><h2>让每次评审都指向成长</h2></div><button v-if="canManageHR" class="button button-primary" @click="openModal('review')">创建绩效评审</button></div>
          <div class="performance-hero"><div><span>平均绩效分</span><strong>{{ reviews.length ? (reviews.reduce((sum, item) => sum + item.score, 0) / reviews.length).toFixed(1) : '—' }}</strong><small>满分 5.0</small></div><div class="performance-ring" :style="{ '--score': reviews.length ? `${reviews.reduce((sum, item) => sum + item.score, 0) / reviews.length / 5 * 100}%` : '0%' }"><span>{{ reviews.length }}</span><small>次评审</small></div></div>
          <article class="panel">
            <div class="review-grid" v-if="reviews.length"><div v-for="review in reviews" :key="review.id" class="review-card"><div class="review-card-head"><div><span>{{ review.cycle }}</span><h3>{{ employeeName(review.employee_id) }}</h3></div><b>{{ review.score.toFixed(1) }}</b></div><p>{{ review.manager_feedback || '暂无经理评语' }}</p><div class="plan-box"><small>AGENT 建议</small><strong>{{ review.development_plan.category === 'high_performance' ? '高潜发展计划' : review.development_plan.category === 'improvement' ? '绩效改进计划' : '能力巩固计划' }}</strong><ul><li v-for="action in review.development_plan.actions" :key="action">{{ action }}</li></ul></div></div></div>
            <div v-else class="empty-state"><span>绩</span><h3>暂无绩效记录</h3><p>完成一次评审，Agent 将生成个性化发展建议。</p><button class="button button-primary" @click="openModal('review')">创建评审</button></div>
          </article>
        </section>

        <section v-else-if="activeView === 'offboarding'" class="view-stack">
          <div class="view-intro"><div><span class="section-kicker">OFFBOARDING</span><h2>有序交接，体面离场</h2></div><button v-if="canManageHR" class="button button-primary danger-button" @click="openModal('offboarding')">发起离职流程</button></div>
          <article class="panel">
            <div class="offboarding-list" v-if="offboardingCases.length"><div v-for="item in offboardingCases" :key="item.id" class="offboarding-card"><div class="offboarding-person"><span>{{ employeeName(item.employee_id).slice(-2) }}</span><div><h3>{{ employeeName(item.employee_id) }}</h3><p>最后工作日：{{ item.last_working_day || '待确定' }}</p></div></div><div class="offboarding-reason"><small>离职原因</small><p>{{ item.reason }}</p></div><div class="handover-count"><strong>{{ item.handover_items.length }}</strong><span>项交接任务</span></div><span class="status-pill" :class="statusClass(item.status)">{{ statusLabel(item.status) }}</span><div class="row-actions"><template v-if="item.status === 'pending_approval'"><button @click="decideOffboarding(item.id, true)">批准</button><button class="text-danger" @click="decideOffboarding(item.id, false)">退回</button></template><button v-else-if="item.status === 'approved'" @click="completeOffboarding(item.id)">完成归档</button></div></div></div>
            <div v-else class="empty-state"><span>离</span><h3>暂无离职流程</h3><p>当前没有需要处理的离职和交接事项。</p></div>
          </article>
        </section>
        <section v-else class="view-stack">
          <div class="view-intro actions-only"><button class="button button-primary" @click="openModal('user')">创建系统账号</button></div>
          <div class="mini-stat-row"><div><strong>{{ systemUsers.length }}</strong><span>系统账号</span></div><div><strong>{{ systemUsers.filter(item => item.is_active).length }}</strong><span>启用账号</span></div><div><strong>{{ new Set(systemUsers.map(item => item.role)).size }}</strong><span>已分配角色</span></div><div><strong>{{ auditLogs.length }}</strong><span>最近审计事件</span></div></div>
          <article class="panel"><div class="panel-heading"><h3>账号与角色</h3><span class="muted">只有管理员可以管理</span></div><div class="table-wrap"><table><thead><tr><th>用户</th><th>角色</th><th>状态</th><th>最近登录</th><th>操作</th></tr></thead><tbody><tr v-for="user in systemUsers" :key="user.id"><td><div class="person-cell"><span>{{ user.full_name.slice(0, 1) }}</span><div><strong>{{ user.full_name }}</strong><small>{{ user.email }}</small></div></div></td><td>{{ roleLabel(user.role) }}</td><td><span class="status-pill" :class="user.is_active ? 'success' : 'danger'">{{ user.is_active ? '已启用' : '已停用' }}</span></td><td>{{ formatDateTime(user.last_login_at) }}</td><td><button class="table-action" :disabled="user.id === currentUser.id" @click="toggleSystemUser(user.id)">{{ user.is_active ? '停用' : '启用' }}</button></td></tr></tbody></table></div></article>
          <article class="panel"><div class="panel-heading"><h3>审计日志</h3><span class="muted">最近 {{ auditLogs.length }} 条</span></div><div class="table-wrap"><table><thead><tr><th>时间</th><th>角色</th><th>操作</th><th>状态码</th><th>来源 IP</th></tr></thead><tbody><tr v-for="log in auditLogs" :key="log.id"><td>{{ formatDateTime(log.created_at) }}</td><td>{{ roleLabel(log.actor_role) }}</td><td>{{ log.action }}</td><td>{{ log.status_code }}</td><td>{{ log.ip_address || '—' }}</td></tr></tbody></table></div></article>
        </section>
      </template>
    </main>

    <div v-if="modal" class="modal-backdrop" @click.self="modal = null">
      <section class="modal-card">
        <button class="modal-close" @click="modal = null">×</button>
        <template v-if="modal === 'profile'"><div class="modal-heading"><span>EMPLOYEE PROFILE</span><h2>个人信息</h2><p>员工个人档案与当前任职信息。</p></div><div v-if="currentEmployee"><div class="profile-summary"><div class="profile-avatar">{{ currentEmployee.name.slice(-1) }}</div><div><h3>{{ currentEmployee.name }}</h3><p>{{ currentEmployee.position }} · {{ currentEmployee.department }}</p></div></div><dl class="profile-details"><div><dt>个人编号</dt><dd>{{ employeeNumber(currentEmployee.id) }}</dd></div><div><dt>姓名</dt><dd>{{ currentEmployee.name }}</dd></div><div><dt>工龄</dt><dd>{{ tenureLabel(currentEmployee.start_date) }}</dd></div><div><dt>所属部门</dt><dd>{{ currentEmployee.department }}</dd></div><div><dt>职位</dt><dd>{{ currentEmployee.position }}</dd></div><div><dt>工作邮箱</dt><dd>{{ currentEmployee.email }}</dd></div><div><dt>入职日期</dt><dd>{{ currentEmployee.start_date }}</dd></div><div><dt>当前状态</dt><dd><span class="status-pill" :class="statusClass(currentEmployee.status)">{{ statusLabel(currentEmployee.status) }}</span></dd></div></dl></div><div v-else class="profile-empty"><div class="profile-avatar">HR</div><h3>暂未关联员工档案</h3><p>请先在“员工中心”中创建员工档案，个人编号、姓名、工龄等信息会自动显示在这里。</p><button class="button button-primary" @click="modal = null; navTo('employees')">前往员工中心</button></div></template>
        <template v-else-if="modal === 'job'"><div class="modal-heading"><span>TALENT ACQUISITION AGENT</span><h2>人才引进</h2><p>填写岗位需求，Agent 将生成职位画像和面试问题。</p></div><form @submit.prevent="createJob"><div class="form-row"><label>职位名称<input v-model="jobForm.title" required /></label><label>所属部门<input v-model="jobForm.department" required /></label></div><div class="form-row"><label>招聘人数<input v-model.number="jobForm.headcount" type="number" min="1" max="100" required /></label><label>薪资范围<input v-model="jobForm.salary" required placeholder="例如：15K-25K·14薪" /></label></div><div class="form-row"><label>学历要求<select v-model="jobForm.education" required><option>不限</option><option>大专</option><option>本科</option><option>硕士</option><option>博士</option></select></label><label>经验要求<select v-model="jobForm.experience" required><option>不限</option><option>应届</option><option>1-3年</option><option>3-5年</option><option>5-10年</option><option>10年以上</option></select></label></div><label>必备技能<input v-model="jobForm.skills" placeholder="Python, FastAPI" /></label><label>岗位职责<textarea v-model="jobForm.responsibilities" rows="4" required></textarea><small>每行填写一项职责</small></label><button class="button button-primary full" :disabled="busy">{{ busy ? '正在确认...' : '确认' }}</button></form></template>
        <template v-else-if="modal === 'candidate'"><div class="modal-heading"><span>RESUME SCREENING</span><h2>录入候选人</h2><p>Agent 会评估简历匹配度；完成该职位筛选后，系统统一生成面试名单。</p></div><form @submit.prevent="createCandidate"><label>目标职位<select v-model.number="candidateForm.job_id" required><option disabled :value="0">请选择职位</option><option v-for="job in jobs" :key="job.id" :value="job.id">{{ job.title }} · {{ job.department }}</option></select></label><label>姓名<input v-model="candidateForm.name" required /></label><div class="form-row"><label>简历邮箱<input v-model="candidateForm.email" type="email" required /><small>用于发送面试邮件</small></label><label>简历手机号<input v-model="candidateForm.phone" type="tel" required minlength="6" /><small>用于发送面试短信</small></label></div><label>简历文本<textarea v-model="candidateForm.resume_text" rows="7" minlength="20" required placeholder="粘贴候选人简历内容..."></textarea></label><button class="button button-primary full" :disabled="busy || !jobs.length">{{ busy ? '正在 AI 评分...' : '开始 AI 筛选' }}</button></form></template>
        <template v-else-if="modal === 'employee'"><div class="modal-heading"><span>ONBOARDING AGENT</span><h2>办理员工入职</h2><p>创建档案并自动生成 HR、IT 和直属经理任务。</p></div><form @submit.prevent="createEmployee"><div class="form-row"><label>员工姓名<input v-model="employeeForm.name" required /></label><label>工作邮箱<input v-model="employeeForm.email" type="email" required /></label></div><div class="form-row"><label>所属部门<input v-model="employeeForm.department" required /></label><label>职位<input v-model="employeeForm.position" required /></label></div><label>入职日期<input v-model="employeeForm.start_date" type="date" required /></label><button class="button button-primary full" :disabled="busy">生成入职任务</button></form></template>
        <template v-else-if="modal === 'workflow'"><div class="modal-heading"><span>WORKFLOW ROUTER</span><h2>发起 HR 流程</h2><p>Agent 将识别请假、报销、调岗等意图并生成审批链。</p></div><form @submit.prevent="createWorkflow"><label>申请人<select v-model.number="workflowForm.employee_id" required><option disabled :value="0">请选择员工</option><option v-for="employee in activeEmployees" :key="employee.id" :value="employee.id">{{ employee.name }} · {{ employee.department }}</option></select></label><label>申请内容<textarea v-model="workflowForm.content" rows="6" required placeholder="例如：申请下周五休假一天"></textarea></label><button class="button button-primary full" :disabled="busy || !activeEmployees.length">识别并发起流程</button></form></template>
        <template v-else-if="modal === 'review'"><div class="modal-heading"><span>PERFORMANCE COACH</span><h2>创建绩效评审</h2><p>Agent 会根据分数和反馈生成发展建议。</p></div><form @submit.prevent="createReview"><div class="form-row"><label>员工<select v-model.number="reviewForm.employee_id" required><option disabled :value="0">请选择员工</option><option v-for="employee in activeEmployees" :key="employee.id" :value="employee.id">{{ employee.name }}</option></select></label><label>评审周期<input v-model="reviewForm.cycle" required /></label></div><label>绩效目标<textarea v-model="reviewForm.goals" rows="4" required placeholder="每行填写一项目标"></textarea></label><label>绩效分数 <b class="range-value">{{ reviewForm.score.toFixed(1) }}</b><input v-model.number="reviewForm.score" class="range" type="range" min="1" max="5" step="0.1" /></label><label>经理反馈<textarea v-model="reviewForm.manager_feedback" rows="4"></textarea></label><button class="button button-primary full" :disabled="busy || !activeEmployees.length">生成发展建议</button></form></template>
        <template v-else-if="modal === 'user'"><div class="modal-heading"><span>ACCESS CONTROL</span><h2>创建系统账号</h2><p>为用户分配最小必要权限。</p></div><form @submit.prevent="createSystemUser"><div class="form-row"><label>姓名<input v-model="userForm.full_name" required /></label><label>工号<input v-model="userForm.email" type="text" minlength="2" maxlength="64" required /></label></div><label>角色<select v-model="userForm.role" required><option value="admin">管理员 · 全部权限</option><option value="hr">HR · 员工全生命周期管理</option><option value="recruiter">招聘人员 · 招聘管理</option><option value="viewer">只读人员 · 仅查看</option></select></label><label>初始密码<input v-model="userForm.password" type="password" minlength="12" required autocomplete="new-password" /><small>密码至少12位，并包含大小写字母和数字。</small></label><button class="button button-primary full" :disabled="busy">{{ busy ? '正在创建...' : '确认创建' }}</button></form></template>
        <template v-else><div class="modal-heading"><span>OFFBOARDING AGENT</span><h2>发起离职流程</h2><p>系统将生成交接、资产、账号和结算清单。</p></div><form @submit.prevent="createOffboarding"><label>员工<select v-model.number="offboardingForm.employee_id" required><option disabled :value="0">请选择员工</option><option v-for="employee in activeEmployees" :key="employee.id" :value="employee.id">{{ employee.name }} · {{ employee.position }}</option></select></label><label>离职原因<textarea v-model="offboardingForm.reason" rows="5" required></textarea></label><label>最后工作日<input v-model="offboardingForm.last_working_day" type="date" /></label><button class="button button-primary danger-button full" :disabled="busy || !activeEmployees.length">生成交接清单</button></form></template>
      </section>
    </div>

    <transition name="toast"><div v-if="toast" class="toast" :class="{ error: toastError }"><span>{{ toastError ? '!' : '✓' }}</span>{{ toast }}</div></transition>
  </div>
</template>
