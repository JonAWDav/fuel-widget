import tempfile
from pathlib import Path
import unittest
from forecast import History

class ForecastTests(unittest.TestCase):
    def setUp(self):
        (Path(__file__).parent/'state').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent/'state')
        self.path=Path(self.temp.name)/'history.json'
        self.h=History(self.path)
        self.now=100000
    def tearDown(self): self.temp.cleanup()
    def seed(self,remaining=20,reset_in=7200,drop=10):
        for i in range(11):
            self.w={'label':'Weekly','remaining':remaining+drop*(10-i)/10,'reset':self.now+reset_in}
            self.h.record('Codex',[self.w],self.now-1800+i*180)
        return self.h.estimate('Codex',self.w,self.now)
    def test_early_math(self):
        f=self.seed()
        self.assertEqual(f['kind'],'early')
        self.assertEqual(f['empty_at'],self.now+3600)
        self.assertEqual(f['before_reset'],3600)
    def test_safe_math(self):
        f=self.seed(remaining=80)
        self.assertEqual(f['kind'],'safe')
        self.assertEqual(f['before_reset'],-7200)
    def test_restart_preserves_history(self):
        f=self.seed()
        self.assertEqual(History(self.path).estimate('Codex',self.w,self.now),f)
    def test_no_usage_does_not_claim_safe(self):
        self.assertEqual(self.seed(drop=0)['kind'],'learning')
    def test_reset_starts_new_series(self):
        self.seed();self.w['reset']+=604800
        self.h.record('Codex',[self.w],self.now+90)
        self.assertEqual(self.h.estimate('Codex',self.w,self.now+90)['kind'],'learning')
    def test_reset_timestamp_jitter_allowed(self):
        self.seed();self.w['reset']+=.8
        self.h.record('Codex',[self.w],self.now+90)
        self.assertEqual(self.h.estimate('Codex',self.w,self.now+90)['kind'],'early')
    def test_gap_and_refill_discard_history(self):
        for gap,refill in [(700,0),(90,5)]:
            self.seed();self.w['remaining']+=refill
            self.h.record('Codex',[self.w],self.now+gap)
            self.assertEqual(self.h.estimate('Codex',self.w,self.now+gap)['kind'],'learning')
    def test_stale_and_expired(self):
        self.seed()
        self.assertEqual(self.h.estimate('Codex',self.w,self.now,True)['kind'],'unknown')
        self.assertEqual(self.h.estimate('Codex',self.w,self.w['reset'])['kind'],'unknown')
    def test_empty(self):
        self.assertIn('Empty now',self.seed(remaining=0)['text'])
    def test_time_advancing_does_not_move_exhaustion(self):
        first=self.seed()
        self.assertEqual(self.h.estimate('Codex',self.w,self.now+60)['empty_at'],first['empty_at'])

if __name__=='__main__':unittest.main()
