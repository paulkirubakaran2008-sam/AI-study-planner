export type Priority = "critical" | "high" | "medium" | "low";
export type Status = "pending" | "in_progress" | "completed" | "skipped" | "overdue";

export interface User { id: number; name: string; email: string; college: string; department: string; year: number; is_demo: boolean; onboarded: boolean; theme: "light" | "dark" }
export interface Task {
  id: number; subject_id: number; subject_name: string; subject_color: string; topic_id: number | null; topic_name: string | null; title: string;
  task_type: "study" | "revision" | "practice"; date: string; start_time: string; end_time: string; start_minute: number; duration_minutes: number;
  priority: Priority; priority_score: number; difficulty: number; status: Status; notes: string; origin: string; locked: boolean;
  moved_from: string | null; reschedule_count: number; reason: string; actual_minutes: number; confidence: number | null;
}
export interface Topic { id: number; subject_id: number; name: string; difficulty: number; mastery: number; last_confidence: number | null; last_studied: string | null; review_stage: number; miss_count: number }
export interface Subject { id: number; name: string; color: string; difficulty: number; importance: number; target_marks: number; exam_date: string | null; days_left: number | null; preparation: number; topics: Topic[] }
export interface Score { score: number; consistency: number; completion: number; focus: number; planning: number; window_days: number; has_data: boolean }
export interface Streak { current: number; longest: number; studied_today: boolean; total_hours: number; tasks_completed: number }
export interface Recommendation { id: number; kind: string; title: string; body: string; reason: string; severity: "info" | "warn" | "urgent"; source: string; ai_explanation: string | null; action: Record<string, unknown> | null; status: string; created_at: string }
export interface NextExam { subject_id: number; subject: string; color: string; exam_date: string; title: string; seconds_remaining: number; days_left: number; preparation: number; recommended: string }
export interface Dashboard {
  greeting: string; name: string; today: string; now_minute: number;
  stats: { study_minutes_today: number; planned_minutes_today: number; completion_rate_week: number; tasks_today: number; tasks_done_today: number; remaining_today: number; remaining_total: number; completion_today: number };
  streak: Streak; score: Score; today_tasks: Task[]; priority_task: Task | null; next_exam: NextExam | null; recommendation: Recommendation | null;
  exams: { subject: string; color: string; date: string; days_left: number; preparation: number }[];
  warnings: { date: string; planned_minutes: number; recommended_max: number }[];
  week_series: { date: string; actual_minutes: number; planned_minutes: number; completed: number; missed: number }[];
  sync: { missed: number; moved: { topic: string; from_date: string; from_time: string; to_date: string; to_time: string; task_id: number }[]; replanned: boolean };
}
export interface Analytics {
  range_days: number; completion_rate: number; score: Score; streak: Streak;
  series: { date: string; actual_minutes: number; planned_minutes: number; completed: number; missed: number }[];
  subject_distribution: { subject_id: number; name: string; color: string; minutes: number; share: number }[];
  productivity: { planned_minutes: number; actual_minutes: number; completion_rate: number; focus_sessions: number; missed_tasks: number; avg_confidence: number | null };
  topics: { subject: string; color: string; name: string; mastery: number }[];
}
export interface Settings {
  name: string; college: string; department: string; year: number; timezone: string; daily_minutes: number[]; max_daily_minutes: number;
  preferred_times: string[]; max_block_minutes: number; break_minutes: number; target_marks: number; default_level: number; blocked_dates: string[];
  theme: "light" | "dark"; notifications_enabled: boolean; browser_notifications: boolean; pomodoro: { focus: number; short_break: number; long_break: number; rounds: number };
}
export interface Overview {
  today: string; pending_minutes: number; capacity_minutes: number; max_daily_minutes: number; last_planned_at: string | null;
  subjects: { subject_id: number; name: string; color: string; planned_minutes: number; needed_minutes: number; exam_date: string | null; days_left: number | null }[];
  overloaded_days: { date: string; planned_minutes: number; recommended_max: number }[]; weights: Record<string, number>;
}
export interface AppNotification { id: number; kind: string; title: string; body: string; read: boolean; created_at: string }
export interface Interpretation { understood: boolean; reply: string; actions: Record<string, unknown>[]; descriptions: string[]; errors: string[]; source: string; ai_available: boolean }
