import unittest
from feeds import window, effective

class AllowanceTests(unittest.TestCase):
    def test_tightest_limit_controls_fuel(self):
        self.assertEqual(effective({'windows':[window('Session',4,None),window('Weekly',75,None)]}),25)
    def test_unknown_is_not_empty(self):
        self.assertIsNone(window('Session',None,None))
        self.assertIsNone(effective({}))
    def test_blocked_is_empty(self):
        self.assertEqual(effective({'blocked':True,'windows':[window('Weekly',2,None)]}),0)
    def test_zero_used_is_full(self):
        self.assertEqual(window('Weekly',0,None)['remaining'],100)
    def test_invalid_rejected(self):
        for value in (-1,101,float('nan')):
            with self.assertRaises(ValueError):window('Weekly',value,None)
    def test_reset_parse(self):
        self.assertEqual(window('Weekly',10,'2026-09-23T00:00:00+00:00')['reset'],1790121600)

if __name__=='__main__':unittest.main()
