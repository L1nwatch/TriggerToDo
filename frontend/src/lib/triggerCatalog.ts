export const DATE_TRIGGER_REFS = ['date', 'date:daily', 'date:weekly', 'date:monthly', 'date:yearly'] as const

export function isDateTriggerRef(ref: string | null | undefined): boolean {
  const value = String(ref || '').trim()
  return value === 'date' || value.startsWith('date:')
}

export function dateTriggerLabel(ref: string): string {
  if (ref === 'date') return 'date-trigger'
  if (ref === 'date:daily') return 'daily-trigger'
  if (ref === 'date:weekly') return 'weekly-trigger'
  if (ref === 'date:monthly') return 'monthly-trigger'
  if (ref === 'date:yearly') return 'yearly-trigger'
  return ref
}

export function builtInTriggerOptions() {
  return [
    { value: 'date', label: 'date-trigger (activate when due date arrives)' },
    { value: 'date:daily', label: 'daily-trigger (due-date based)' },
    { value: 'date:weekly', label: 'weekly-trigger (due-date based)' },
    { value: 'date:monthly', label: 'monthly-trigger (due-date based)' },
    { value: 'date:yearly', label: 'yearly-trigger (due-date based)' },
  ]
}
