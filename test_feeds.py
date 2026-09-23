import unittest
from unittest.mock import patch, Mock
import feeds
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

    def test_mac_codex_probe_does_not_use_windows_process_flags(self):
        result=Mock(returncode=0,stdout='{"rateLimits":{"primary":{"windowDurationMins":300,"usedPercent":20,"resetsAt":1790121600}}}')
        with patch.object(feeds.sys,'platform','darwin'),patch.object(feeds.shutil,'which',return_value='/opt/homebrew/bin/node'),patch.object(feeds.subprocess,'run',return_value=result) as run:
            self.assertEqual(feeds.codex()['windows'][0]['remaining'],80)
        self.assertNotIn('creationflags',run.call_args.kwargs)

    def test_mac_claude_keychain_fallback(self):
        keychain=Mock(returncode=0,stdout='{"claudeAiOauth":{"accessToken":"test-token"}}')
        response=Mock(status_code=200)
        response.json.return_value={'five_hour':{'utilization':35,'resets_at':'2026-09-24T00:00:00Z'}}
        with patch.object(feeds.sys,'platform','darwin'),patch.object(feeds.Path,'exists',return_value=False),patch.object(feeds.subprocess,'run',return_value=keychain) as run,patch.object(feeds.requests,'get',return_value=response):
            self.assertEqual(feeds.claude()['windows'][0]['remaining'],65)
        self.assertEqual(run.call_args.args[0][0],'security')

if __name__=='__main__':unittest.main()
