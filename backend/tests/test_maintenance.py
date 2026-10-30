import unittest
from datetime import date

from app.services.maintenance import available_quantity, next_due_after, return_status, task_status, warranty_status

T = date(2026, 6, 15)


class TaskStatus(unittest.TestCase):
    def test_overdue_when_due_date_has_passed(self):
        self.assertEqual(task_status(date(2026, 6, 14), T), "Overdue")

    def test_due_today_is_due_soon_not_overdue(self):
        self.assertEqual(task_status(T, T), "Due soon")

    def test_thirty_day_window_is_inclusive(self):
        self.assertEqual(task_status(date(2026, 7, 15), T), "Due soon")
        self.assertEqual(task_status(date(2026, 7, 16), T), "Scheduled")

    def test_no_next_due_means_completed(self):
        self.assertEqual(task_status(None, T), "Completed")


class NextDue(unittest.TestCase):
    def test_recurring_counts_from_completion_date(self):
        self.assertEqual(next_due_after(date(2026, 6, 20), 90), date(2026, 9, 18))

    def test_one_off_has_no_next_due(self):
        self.assertIsNone(next_due_after(date(2026, 6, 20), None))
        self.assertIsNone(next_due_after(date(2026, 6, 20), 0))

    def test_year_end_rollover(self):
        self.assertEqual(next_due_after(date(2026, 12, 20), 30), date(2027, 1, 19))


class Warranty(unittest.TestCase):
    def test_states(self):
        self.assertEqual(warranty_status(None, T), "None")
        self.assertEqual(warranty_status(date(2026, 6, 14), T), "Expired")
        self.assertEqual(warranty_status(T, T), "Expiring soon")
        self.assertEqual(warranty_status(date(2026, 8, 14), T), "Expiring soon")
        self.assertEqual(warranty_status(date(2026, 8, 15), T), "In warranty")


class Custody(unittest.TestCase):
    def test_available(self):
        self.assertEqual(available_quantity(5, 2), 3)
        self.assertEqual(available_quantity(5, 5), 0)

    def test_return_status(self):
        self.assertEqual(return_status(date(2026, 6, 10), True, T), "Returned")
        self.assertEqual(return_status(date(2026, 6, 10), False, T), "Overdue")
        self.assertEqual(return_status(T, False, T), "Out")
        self.assertEqual(return_status(None, False, T), "Out")


if __name__ == "__main__":
    unittest.main()
