"""Exercise the real QWidget offscreen, including hover transitions and stale state."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import json
import time
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEvent
from PySide6.QtGui import QEnterEvent
from PySide6.QtCore import QPointF
from PySide6.QtTest import QTest
import widget

snapshot=json.loads((widget.STATE/'health.json').read_text()) if (widget.STATE/'health.json').exists() else {
    'feeds':{name:{'data':{'windows':[{'label':'Weekly','remaining':value,'reset':time.time()+86400}]},'updated':time.time()} for name,value in [('Codex',82),('Claude',25)]}}
demo='--demo' in sys.argv
if demo:
    snapshot={'providers':{'Codex':{'kind':'meter'},'Claude':{'kind':'meter'},'Kimi':{'kind':'meter'},
        'Hermes':{'kind':'linked','linked':'Kimi','detail':'Allowance shown under Kimi','subtitle':'Agent uses its configured provider'},
        'Cursor':{'kind':'detected','detail':'Usage is not exposed to Fuel','subtitle':'Detected on this PC'}},'feeds':{
        'Codex':{'data':{'windows':[{'label':'Weekly','remaining':82,'reset':time.time()+172800}]},'updated':time.time()},
        'Claude':{'data':{'windows':[{'label':'5-hour','remaining':66,'reset':time.time()+7200},{'label':'Weekly','remaining':25,'reset':time.time()+86400}]},'updated':time.time()},
        'Kimi':{'data':{'kind':'balance','windows':[],'balance':42.5,'unit':'USD','detail':'Moonshot API prepaid balance'},'updated':time.time()}}}
# Keep this rendering test isolated from the live instance and its network workers.
widget.FuelWidget.refresh=lambda self:None
widget.FuelWidget.write_health=lambda self:None
widget.FuelWidget.make_tray=lambda self:None
app=QApplication([])
w=widget.FuelWidget()
w.demo=demo
if 'providers' in snapshot:w.providers=snapshot['providers']
for name,feed in snapshot['feeds'].items():
    if feed.get('data'):
        w.data[name]=feed['data'];w.updated[name]=feed['updated'];w.display[name]=widget.effective(feed['data']) or 0
if demo:
    w.history.series={}
QTest.qWait(100)
assert (w.width(),w.height())==(72,32)
w.grab().save(str(widget.STATE/'pill.png'))
QApplication.sendEvent(w,QEnterEvent(QPointF(10,10),QPointF(10,10),QPointF(10,10)))
QTest.qWait(1000)
assert w.expanded and w.width()==332 and w.height()==min(w.content_height()+108,650,app.primaryScreen().availableGeometry().height()-80)
w.grab().save(str(widget.STATE/('demo.png' if demo else 'expanded.png')))
w.set_scroll(99999)
assert 0<=w.scroll<=max(0,w.content_height()-(w.height()-108))
w.grab().save(str(widget.STATE/'scrolled.png'))
w.set_scroll(0)
w.errors['Claude']='Connection failed'
w.grab().save(str(widget.STATE/'stale.png'))
w.errors.clear()
QApplication.sendEvent(w,QEvent(QEvent.Leave))
QTest.qWait(800)
assert not w.expanded and (w.width(),w.height())==(72,32)
print('PASS: collapsed 72x32, adaptive expansion, bounded scrolling, leave collapse and stale rendering.')
w.close()
