/**
 * Shared formatting utilities for the dashboard
 */

/**
 * Format a date to HH:MM:SS time string
 */
export function formatTime(date: Date | null | undefined): string {
	if (!date) return '--:--:--';
	return date.toLocaleTimeString('en-US', {
		hour12: false,
		hour: '2-digit',
		minute: '2-digit',
		second: '2-digit'
	});
}

/**
 * Format a number with locale-appropriate thousands separators
 */
export function formatNumber(num: number | null | undefined): string {
	return (num ?? 0).toLocaleString();
}
