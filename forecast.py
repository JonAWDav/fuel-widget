"""Conservative extrapolation of recently observed allowance consumption."""
import json
import math

HORIZON = 7200
MIN_SPAN = 900
MAX_GAP = 600

def duration(seconds):
    minutes = max(1, math.ceil(seconds / 60))
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    return f'{days}d {hours}h' if days else f'{hours}h {minutes:02}m' if hours else f'{minutes}m'

class History:
    def __init__(self, path):
        self.path = path
        try:
            self.series = json.loads(path.read_text())
            if not isinstance(self.series, dict): self.series = {}
        except (OSError, ValueError): self.series = {}
        self.series = {key:[p for p in points if isinstance(p,dict) and
            all(isinstance(p.get(k),(int,float)) and math.isfinite(p[k]) for k in ('t','r','reset'))]
            for key,points in self.series.items() if isinstance(points,list)}

    def record(self, provider, windows, now):
        for w in windows:
            key = provider + ':' + w['label']
            points = self.series.get(key, [])
            if not isinstance(points, list): points = []
            points = [p for p in points if isinstance(p, dict) and
                      all(isinstance(p.get(k), (int,float)) and math.isfinite(p[k]) for k in ('t','r','reset'))]
            reset = w.get('reset')
            if not isinstance(reset, (int,float)) or not math.isfinite(reset):
                self.series[key] = []; continue
            if points:
                prev = points[-1]
                if (now < prev['t'] or now-prev['t'] > MAX_GAP or
                    abs(reset-prev['reset']) > 60 or w['remaining'] > prev['r']+.5):
                    points = []
            points = [p for p in points if now-HORIZON <= p['t'] < now]
            points.append({'t':now,'r':w['remaining'],'reset':reset})
            self.series[key] = points[-100:]
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.series))
        temp.replace(self.path)

    def estimate(self, provider, w, now, unavailable=False):
        reset = w.get('reset')
        if unavailable: return {'kind':'unknown','text':'Forecast paused: reconnecting'}
        if not reset: return {'kind':'unknown','text':'Forecast needs a reset time'}
        if reset <= now: return {'kind':'unknown','text':'Waiting for reset update'}
        if w['remaining'] <= 0:
            return {'kind':'early','text':f'Empty now; reset in {duration(reset-now)}'}
        points = self.series.get(provider+':'+w['label'], [])
        points = [p for p in points if now-HORIZON <= p['t'] <= now and abs(p['reset']-reset)<=60]
        if not points or now-points[-1]['t']>300:
            return {'kind':'learning','text':'Learning your pace (15m minimum)'}
        span = points[-1]['t']-points[0]['t']
        if len(points)<6 or span<MIN_SPAN:
            return {'kind':'learning','text':'Learning your pace (15m minimum)'}
        consumed = points[0]['r']-points[-1]['r']
        if consumed<2:
            return {'kind':'learning','text':'Waiting for measurable usage'}
        rate = consumed/span
        empty_at = points[-1]['t']+points[-1]['r']/rate
        until = max(0,empty_at-now)
        margin = reset-empty_at
        if margin>0:
            text = f'Est. empty in {duration(until)}; {duration(margin)} before reset'
            kind = 'early'
        else:
            text = f'Est. lasts to reset (+{duration(-margin)})'
            kind = 'safe'
        return {'kind':kind,'text':text,'empty_at':empty_at,'before_reset':margin,
                'rate_per_hour':rate*3600,'observed_seconds':span}
