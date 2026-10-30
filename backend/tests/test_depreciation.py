import unittest
from datetime import date

from app.services.depreciation import DepAsset, fy_bounds, fy_figures, fy_of, nbv_as_on, residual_value


def slm(cost=100000, cap=date(2025, 4, 1), life=5, res=5, disp=None, proceeds=0):
    return DepAsset(cost=cost, cap_date=cap, method="SLM", life=life, residual_pct=res, disposal_date=disp, proceeds=proceeds)


class FinancialYear(unittest.TestCase):
    def test_fy_of(self):
        self.assertEqual(fy_of(date(2025, 4, 1)), 2025)
        self.assertEqual(fy_of(date(2026, 3, 31)), 2025)
        self.assertEqual(fy_of(date(2026, 4, 1)), 2026)

    def test_bounds(self):
        self.assertEqual(fy_bounds(2025), (date(2025, 4, 1), date(2026, 3, 31)))


class StraightLine(unittest.TestCase):
    def test_full_years(self):
        a = slm()
        f = fy_figures(a, 2025)
        self.assertEqual((f["additions"], f["charge"], f["closing_acc"], f["closing_net"]), (100000.0, 19000.0, 19000.0, 81000.0))
        f = fy_figures(a, 2029)  # fifth and final year
        self.assertEqual((f["opening_acc"], f["charge"], f["closing_acc"], f["closing_net"]), (76000.0, 19000.0, 95000.0, 5000.0))
        f = fy_figures(a, 2030)  # fully depreciated down to residual
        self.assertEqual((f["opening_gross"], f["charge"], f["closing_net"]), (100000.0, 0.0, 5000.0))

    def test_part_year_addition_is_pro_rata_by_days(self):
        a = slm(cap=date(2025, 10, 1))  # 1 Oct..31 Mar = 182 days of 365
        f = fy_figures(a, 2025)
        self.assertEqual(f["charge"], 9473.97)
        self.assertEqual(fy_figures(a, 2026)["charge"], 19000.0)
        self.assertEqual(fy_figures(a, 2026)["opening_acc"], 9473.97)

    def test_leap_year_full_year_is_one_full_annual_charge(self):
        self.assertEqual(fy_figures(slm(cap=date(2023, 4, 1)), 2023)["charge"], 19000.0)

    def test_total_never_exceeds_depreciable_amount(self):
        a = slm(cap=date(2025, 10, 1))
        total = sum(fy_figures(a, y)["charge"] for y in range(2025, 2040))
        self.assertAlmostEqual(total, 95000.0, places=2)

    def test_zero_residual(self):
        f = fy_figures(slm(res=0), 2025)
        self.assertEqual(f["charge"], 20000.0)


class WrittenDownValue(unittest.TestCase):
    def wdv(self, **kw):
        return DepAsset(cost=100000, cap_date=kw.get("cap", date(2025, 4, 1)), method="WDV", life=5, residual_pct=5.0)

    def test_first_year_uses_schedule_ii_rate(self):
        rate = 1 - 0.05 ** (1 / 5)
        f = fy_figures(self.wdv(), 2025)
        self.assertEqual(f["charge"], round(100000 * rate, 2))
        second = fy_figures(self.wdv(), 2026)
        self.assertEqual(second["charge"], round((100000 - f["charge"]) * rate, 2))

    def test_never_falls_below_residual(self):
        a = self.wdv()
        for y in range(2025, 2045):
            self.assertGreaterEqual(fy_figures(a, y)["closing_net"], 5000.0 - 0.01)
        self.assertAlmostEqual(fy_figures(a, 2044)["closing_net"], 5000.0, delta=1.0)

    def test_zero_residual_uses_one_rupee_floor(self):
        a = DepAsset(cost=100000, cap_date=date(2025, 4, 1), method="WDV", life=5, residual_pct=0)
        self.assertEqual(residual_value(a), 1.0)


class Disposal(unittest.TestCase):
    def test_disposal_mid_year(self):
        a = slm(disp=date(2025, 9, 30), proceeds=60000)  # 1 Apr..30 Sep inclusive = 183 days
        f = fy_figures(a, 2025)
        self.assertEqual(f["charge"], 9526.03)
        self.assertEqual((f["additions"], f["disposals"], f["closing_gross"], f["closing_acc"], f["closing_net"]), (100000.0, 100000.0, 0.0, 0.0, 0.0))
        self.assertEqual(f["acc_on_disposal"], 9526.03)
        self.assertEqual(f["profit_loss_on_disposal"], round(60000 - (100000 - 9526.03), 2))
        self.assertTrue(f["disposed_in_year"])

    def test_disposed_asset_disappears_next_year(self):
        a = slm(disp=date(2025, 9, 30), proceeds=60000)
        f = fy_figures(a, 2026)
        self.assertTrue(all(v in (0, 0.0, False) for v in f.values()))

    def test_opening_balance_of_asset_disposed_in_later_year(self):
        a = slm(disp=date(2026, 6, 30), proceeds=50000)
        f = fy_figures(a, 2026)
        self.assertEqual((f["opening_gross"], f["opening_acc"], f["disposals"], f["closing_gross"]), (100000.0, 19000.0, 100000.0, 0.0))


class OtherCases(unittest.TestCase):
    def test_land_is_not_depreciated(self):
        land = DepAsset(cost=5000000, cap_date=date(2020, 7, 1), life=0)
        f = fy_figures(land, 2025)
        self.assertEqual((f["opening_gross"], f["charge"], f["closing_net"]), (5000000.0, 0.0, 5000000.0))

    def test_not_yet_in_use_has_no_balances(self):
        f = fy_figures(slm(cap=date(2026, 4, 2)), 2025)
        self.assertTrue(all(v in (0, 0.0, False) for v in f.values()))


class Identities(unittest.TestCase):
    def test_roll_forward_identities_and_year_to_year_tie_out(self):
        assets = [
            slm(), slm(cap=date(2024, 8, 17), life=3), slm(cost=73519.45, cap=date(2023, 11, 3), life=7, res=3),
            DepAsset(cost=48210.5, cap_date=date(2024, 2, 29), method="WDV", life=6, residual_pct=5),
            slm(cap=date(2022, 1, 5), disp=date(2025, 5, 20), proceeds=12000),
        ]
        for a in assets:
            prev = None
            for fy in range(2021, 2036):
                f = fy_figures(a, fy)
                self.assertAlmostEqual(f["closing_gross"], f["opening_gross"] + f["additions"] - f["disposals"], places=2)
                self.assertAlmostEqual(f["closing_acc"], f["opening_acc"] + f["charge"] - f["acc_on_disposal"], places=2)
                self.assertAlmostEqual(f["closing_net"], f["closing_gross"] - f["closing_acc"], places=2)
                if prev is not None and not prev["disposed_in_year"]:
                    self.assertEqual(f["opening_gross"], prev["closing_gross"])
                    self.assertEqual(f["opening_acc"], prev["closing_acc"])
                prev = f


class NetBookValueOnDate(unittest.TestCase):
    def test_mid_year_value(self):
        a = slm()  # 1 Apr..30 Sep = 183 days of 365
        self.assertEqual(nbv_as_on(a, date(2025, 9, 30)), round(100000 - 9526.03, 2))

    def test_on_the_day_of_purchase_is_one_day_of_depreciation(self):
        self.assertEqual(nbv_as_on(slm(), date(2025, 4, 1)), round(100000 - 19000 / 365, 2))

    def test_before_capitalisation_and_after_disposal_is_zero(self):
        self.assertEqual(nbv_as_on(slm(), date(2025, 3, 31)), 0.0)
        self.assertEqual(nbv_as_on(slm(disp=date(2026, 1, 1)), date(2026, 1, 1)), 0.0)

    def test_agrees_with_year_end_figures(self):
        for a in (slm(), slm(cap=date(2024, 8, 17), life=3), DepAsset(cost=48210.5, cap_date=date(2024, 2, 29), method="WDV", life=6, residual_pct=5)):
            for fy in range(2024, 2034):
                self.assertAlmostEqual(nbv_as_on(a, fy_bounds(fy)[1]), fy_figures(a, fy)["closing_net"], places=2)

    def test_land_keeps_full_cost(self):
        self.assertEqual(nbv_as_on(DepAsset(cost=5000000, cap_date=date(2020, 7, 1), life=0), date(2026, 1, 1)), 5000000.0)


if __name__ == "__main__":
    unittest.main()
