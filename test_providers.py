import unittest
from unittest.mock import patch
import providers as p

class ProviderTests(unittest.TestCase):
    def test_kimi_api_balance_never_invents_percentage(self):
        with patch.object(p,'secret',return_value='test-key'),patch.object(p,'get_json',return_value={'code':0,'data':{'available_balance':12.34}}):
            data=p.kimi()
        self.assertEqual(data['balance'],12.34)
        self.assertEqual(data['windows'],[])
    def test_kimi_coding_windows(self):
        data=p.parse_kimi({'usage':{'limit':'100','remaining':'25','resetTime':'2026-10-01T00:00:00Z'},
            'limits':[{'window':{'duration':5},'detail':{'limit':100,'remaining':80,'resetTime':'2026-09-24T00:00:00Z'}}]})
        self.assertEqual([w['remaining'] for w in data['windows']],[25,80])
    def test_openrouter_no_cap_not_full(self):
        with patch.object(p,'secret',return_value='test'),patch.object(p,'get_json',return_value={'data':{'limit':None,'limit_remaining':None,'usage':10}}):
            data=p.openrouter()
        self.assertIsNone(data['balance']);self.assertEqual(data['windows'],[])
    def test_openrouter_budget(self):
        with patch.object(p,'secret',return_value='test'),patch.object(p,'get_json',return_value={'data':{'limit':100,'limit_remaining':20,'usage':80}}):
            data=p.openrouter()
        self.assertEqual(data['windows'][0]['remaining'],20)
        self.assertIsNone(data['windows'][0]['reset'])
    def test_local_models_have_no_subscription_gauge(self):
        with patch.object(p,'get_json',return_value={'models':[{'name':'example','size_vram':1073741824}]}):data=p.ollama()
        self.assertEqual(data['models'],['example']);self.assertEqual(data['windows'],[])
        self.assertIn('1.0 GB',data['detail'])
    def test_lmstudio_loaded_only(self):
        with patch.object(p,'get_json',return_value={'models':[{'key':'loaded','loaded_instances':[{}]},{'key':'unloaded','loaded_instances':[]}]}):data=p.lmstudio()
        self.assertEqual(data['models'],['loaded'])
    def test_malformed_values_rejected(self):
        for value in (None,float('nan'),float('inf'),'unknown'):
            with self.assertRaises(RuntimeError):p.number(value)
    def test_no_auth_or_raw_error_disclosed(self):
        for status in (401,403,429,500,302):
            with patch.object(p.requests,'Session') as session:
                session.return_value.__enter__.return_value=session.return_value
                session.return_value.get.return_value.status_code=status
                with self.assertRaises(RuntimeError) as ctx:p.get_json('https://example.test','test-secret')
                self.assertNotIn('test-secret',str(ctx.exception))

if __name__=='__main__':unittest.main()
