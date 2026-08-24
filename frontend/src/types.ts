export interface AgentInfo {
  name: string
  description: string
}

export interface LangChainStatus {
  framework: string
  version: string
  runtime: string
  supervisor_enabled: boolean
  provider: string | null
  model: string | null
  base_url: string | null
  api_key_configured: boolean
  tools: string[]
}

export interface LangChainChatResponse {
  answer: string
  model: string
  tools: string[]
}

export type UserRole = 'admin' | 'hr' | 'recruiter' | 'viewer'

export interface AuthUser {
  id: number
  email: string
  full_name: string
  role: UserRole
  is_active: boolean
  last_login_at: string | null
  created_at: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  expires_at: string
  user: AuthUser
}

export interface AuditLog {
  id: number
  actor_id: number | null
  actor_role: string
  action: string
  method: string
  path: string
  status_code: number
  ip_address: string
  user_agent: string
  created_at: string
}

export interface DashboardData {
  requisitions: number
  candidates: number
  employees: number
  hr_requests: number
  pending_human_actions: number
  performance_reviews: number
  offboarding_cases: number
}

export interface Job {
  id: number
  title: string
  department: string
  headcount: number
  salary: string
  education: string
  experience: string
  responsibilities: string[]
  required_skills: string[]
  job_profile: Record<string, unknown>
  status: string
  created_at: string
}

export interface Candidate {
  id: number
  job_id: number
  name: string
  email: string
  phone: string
  score: number
  strengths: string[]
  gaps: string[]
  recommendation: string
  status: string
  selection_rank: number | null
  selected_at: string | null
  created_at: string
}

export interface InterviewNotification {
  id: number
  candidate_id: number
  job_id: number
  channel: 'email' | 'sms'
  recipient: string
  scheduled_for: string
  status: 'pending_configuration' | 'scheduled' | 'sending' | 'sent' | 'failed'
  sent_at: string | null
  error: string
  task_id: string | null
  attempt_count: number
}

export interface Employee {
  id: number
  name: string
  email: string
  department: string
  position: string
  start_date: string
  status: string
  onboarding_tasks: Array<{ owner: string; task: string; required: boolean }>
  created_at: string
}

export interface AgentResultData {
  agent: string
  summary: string
  data: Record<string, any>
  human_review_required: boolean
  trace: string[]
  human_decision?: { approved: boolean; comment: string }
}

export interface HRRequest {
  id: number
  employee_id: number | null
  request_type: string
  content: string
  result: AgentResultData
  status: string
  created_at: string
}

export interface PerformanceReview {
  id: number
  employee_id: number
  cycle: string
  goals: string[]
  score: number
  manager_feedback: string
  development_plan: Record<string, any>
  created_at: string
}

export interface OffboardingCase {
  id: number
  employee_id: number
  reason: string
  last_working_day: string | null
  handover_items: Array<{ owner: string; task: string }>
  status: string
  created_at: string
}
