import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import sys
import time

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QThread, Signal, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QFont, QLinearGradient, QCursor, QIcon, QPixmap, QFontDatabase
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QSystemTrayIcon
from feeds import codex, claude, effective
from forecast import History
from providers import READERS, discover

ROOT=Path(__file__).resolve().parent
STATE=ROOT/'state'
STATE.mkdir(exist_ok=True)
logger=logging.getLogger('fuel'); logger.setLevel(logging.INFO)
handler=RotatingFileHandler(STATE/'widget.log',maxBytes=500000,backupCount=2)
handler.setFormatter(logging.Formatter('%(asctime)s %(message)s')); logger.addHandler(handler)
MINT='#39E7DA'; AMBER='#FFB547'; RED='#FF526D'; TEXT='#ECF1F7'; MUTED='#8591A7'

def meter_color(value):
    return MUTED if value is None else RED if value<30 else AMBER if value<=60 else MINT

class Worker(QThread):
    result=Signal(str,object,str)
    def __init__(self,name,fn):
        super().__init__(); self.name=name; self.fn=fn
    def run(self):
        try: self.result.emit(self.name,self.fn(),'')
        except Exception as e:
            # Do not log response bodies, headers or credentials.
            error=str(e) if isinstance(e,RuntimeError) else type(e).__name__+'; retrying'
            self.result.emit(self.name,None,error)

def countdown(reset):
    if not reset: return 'Reset unavailable'
    seconds=max(0,int(reset-time.time()))
    if seconds==0: return 'Reset due'
    mins=math.ceil(seconds/60); hours,mins=divmod(mins,60); days,hours=divmod(hours,24)
    return ('Refills '+(f'{days}d {hours}h' if days else f'{hours}h {mins:02}m' if hours else f'{mins}m'))

class FuelWidget(QWidget):
    def __init__(self):
        super().__init__()
        if sys.platform == 'win32':
            for filename in ('segoeui.ttf','seguisb.ttf'):
                QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/filename))
        self.setWindowTitle('Fuel | AI usage')
        self.setWindowFlags(Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.Tool|Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        if sys.platform == 'darwin':
            self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setMouseTracking(True)
        self.data={}; self.errors={}; self.updated={}; self.workers={}; self.display={'Codex':0,'Claude':0}
        self.providers={'Codex':{'kind':'meter'},'Claude':{'kind':'meter'}}
        self.fonts={}; self.scroll=0.; self.last_frame=time.monotonic(); self.last_refresh=0.
        self.motion=True
        try:self.motion=json.loads((STATE/'preferences.json').read_text()).get('motion',True)
        except (OSError,ValueError):pass
        self.history=History(STATE/'usage-history.json')
        self.phase=0.; self.progress=0.; self.expanded=False; self.menu_open=False; self.opened=0
        self.anchor=QApplication.primaryScreen().availableGeometry().topRight()
        self.anchor.setX(self.anchor.x()-18); self.anchor.setY(self.anchor.y()+52)
        self.anim=QVariantAnimation(self); self.anim.setDuration(260); self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self.set_progress)
        self.close_timer=QTimer(self); self.close_timer.setSingleShot(True); self.close_timer.setInterval(360)
        self.close_timer.timeout.connect(self.maybe_collapse)
        self.tick=QTimer(self); self.tick.setTimerType(Qt.PreciseTimer); self.tick.timeout.connect(self.frame); self.tick.start(250)
        self.scroll_anim=QVariantAnimation(self);self.scroll_anim.setDuration(170);self.scroll_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.scroll_anim.valueChanged.connect(self.set_scroll)
        self.poll=QTimer(self); self.poll.timeout.connect(self.refresh); self.poll.start(90000)
        self.health=QTimer(self); self.health.timeout.connect(self.write_health); self.health.start(10000)
        self.set_progress(0)
        self.setToolTip('AI fuel: hover to expand. Right-click for controls.')
        self.make_tray()
        QApplication.primaryScreen().availableGeometryChanged.connect(self.reanchor)
        self.show(); self.refresh(); self.write_health()

    def reanchor(self,*args):
        self.anchor=QApplication.primaryScreen().availableGeometry().topRight()+QPointF(-18,52).toPoint()
        self.set_progress(self.progress)

    def set_progress(self,p):
        self.progress=float(p)
        height=min(self.content_height()+108,650,QApplication.primaryScreen().availableGeometry().height()-80)
        self.resize(round(72+260*self.progress),round(32+(height-32)*self.progress))
        self.move(self.anchor.x()-self.width(),self.anchor.y())
        self.update()

    def expand(self,yes):
        if self.expanded==yes: return
        self.expanded=yes; self.tick.setInterval(16 if yes and self.motion else 250)
        if yes:self.opened=time.monotonic()
        self.anim.setDuration(260 if self.motion else 1)
        self.anim.stop(); self.anim.setStartValue(self.progress); self.anim.setEndValue(1. if yes else 0.); self.anim.start()

    def enterEvent(self,event):
        self.close_timer.stop(); self.expand(True)

    def leaveEvent(self,event): self.close_timer.start()

    def maybe_collapse(self):
        if not self.menu_open and not self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            self.expand(False)

    def frame(self):
        now=time.monotonic();dt=min(.3,now-self.last_frame);self.last_frame=now
        if self.motion:self.phase+=dt*1.7
        for name in self.display:
            target=effective(self.data.get(name))
            if target is not None: self.display[name]+=(target-self.display[name])*(1-math.exp(-dt*9) if self.motion else 1)
        self.update()

    def refresh(self):
        if time.monotonic()-self.last_refresh<10:return
        self.last_refresh=time.monotonic()
        readers={'@discovery':discover,**{n:READERS[n] for n,d in self.providers.items() if d['kind']=='meter' and n in READERS}}
        self.start_readers(readers)

    def start_readers(self,readers):
        for name,fn in readers.items():
            if name in self.workers: continue
            worker=Worker(name,fn); self.workers[name]=worker
            worker.result.connect(self.received)
            worker.finished.connect(lambda n=name:self.worker_done(n))
            worker.start()

    def worker_done(self,name):
        worker=self.workers.pop(name,None)
        if worker: worker.deleteLater()

    def received(self,name,data,error):
        if name=='@discovery':
            if data:
                self.providers=data
                for n in data:self.display.setdefault(n,0)
                self.update_connections()
                self.set_progress(self.progress)
                self.start_readers({n:READERS[n] for n,d in data.items() if d['kind']=='meter' and n in READERS and n not in self.updated})
            return
        if data:
            self.data[name]=data; self.updated[name]=time.time(); self.errors.pop(name,None)
            try: self.history.record(name,data.get('windows',[]),self.updated[name])
            except OSError: logger.warning('Could not persist forecast history')
            logger.info('%s connected',name)
        else:
            self.errors[name]=error; logger.warning('%s: %s',name,error)
        self.set_progress(self.progress);self.write_health(); self.update()

    def write_health(self):
        record={'pid':os.getpid(),'heartbeat':time.time(),'expanded':self.expanded,
                'geometry':[self.x(),self.y(),self.width(),self.height()],
                'providers':self.providers,
                'feeds':{name:{'data':self.data.get(name),'updated':self.updated.get(name),'error':self.errors.get(name),
                    'forecasts':[self.history.estimate(name,w,time.time(),bool(self.errors.get(name)) or time.time()-self.updated.get(name,0)>300) for w in self.data.get(name,{}).get('windows',[])]} for name in self.providers}}
        temp=STATE/'health.tmp'; temp.write_text(json.dumps(record,indent=2)); temp.replace(STATE/'health.json')

    def make_tray(self):
        pix=QPixmap(32,32);pix.fill(Qt.transparent)
        p=QPainter(pix);p.setRenderHint(QPainter.Antialiasing);p.setPen(Qt.NoPen)
        p.setBrush(QColor('#121B29'));p.drawRoundedRect(QRectF(0,0,32,32),9,9)
        for x,c in [(8,MINT),(19,AMBER)]:p.setBrush(QColor(c));p.drawRoundedRect(QRectF(x,8,5,16),2,2)
        p.end(); self.setWindowIcon(QIcon(pix))
        self.tray=QSystemTrayIcon(QIcon(pix),self);self.tray.setToolTip('Fuel | AI usage and balances')
        self.menu=QMenu();self.menu.setStyleSheet('QMenu{background:#151D2B;color:#ECF1F7;border:1px solid #354154;padding:6px;}QMenu::item{padding:8px 18px;}QMenu::item:selected{background:#2B394C;}')
        self.menu.addAction('Refresh usage',self.refresh)
        self.menu.addAction('Move to top-right',self.reanchor)
        self.connections=self.menu.addMenu('Other detected apps')
        self.update_connections()
        motion_action=self.menu.addAction('Animate meters');motion_action.setCheckable(True);motion_action.setChecked(self.motion)
        motion_action.toggled.connect(self.set_motion)
        self.menu.addSeparator();self.menu.addAction('Quit (stays off until reopened)',self.quit_intentionally)
        self.tray.setContextMenu(self.menu);self.tray.show()

    def contextMenuEvent(self,event):
        self.menu_open=True;self.menu.exec(event.globalPos());self.menu_open=False;self.close_timer.start()

    def quit_intentionally(self):
        (STATE/'paused').write_text('Intentionally stopped. Open Start Fuel to resume.\n')
        logger.info('Intentional stop')
        self.hide();self.tray.hide()
        for worker in list(self.workers.values()):worker.wait(32000)
        QApplication.quit()

    def text(self,p,x,y,text,size=10,color=TEXT,bold=False):
        key=(size,bold)
        if key not in self.fonts:self.fonts[key]=QFont('Segoe UI' if sys.platform=='win32' else 'Helvetica Neue',size,QFont.DemiBold if bold else QFont.Normal)
        p.setFont(self.fonts[key])
        text=p.fontMetrics().elidedText(str(text),Qt.ElideRight,max(1,round(308-x)))
        p.setPen(QColor(color));p.drawText(QPointF(x,y),text)

    def box(self,p,rect,color,radius=12,border=None):
        p.setPen(QPen(QColor(border),1) if border else Qt.NoPen);p.setBrush(QColor(color));p.drawRoundedRect(rect,radius,radius)

    def energy_meter(self,p,y,name):
        data=self.data.get(name); val=effective(data); error=self.errors.get(name)
        stale=name in self.updated and time.time()-self.updated[name]>300
        color=meter_color(val) if not (error or stale) else MUTED
        height=self.panel_height(name)
        panel=QRectF(20,y,292,height)
        self.box(p,panel,'#0B131D',5,'#213E48')
        p.setPen(QPen(QColor(57,231,218,85),1.2))
        for x,dx in [(20,1),(312,-1)]:
            for yy,dy in [(y,1),(y+height,-1)]:
                p.drawLine(QPointF(x,yy+dy*9),QPointF(x,yy));p.drawLine(QPointF(x,yy),QPointF(x+dx*9,yy))
        self.text(p,33,y+24,name.upper(),9,TEXT,True)
        caption='CONNECTING' if val is None and not error else 'UNAVAILABLE' if val is None else 'LAST KNOWN' if error or stale else 'REMAINING'
        self.text(p,33,y+40,caption,6,MUTED)
        self.text(p,242,y+33,'--' if val is None else f'{round(self.display[name])}%',21,color,True)
        filled=0 if val is None else round(self.display[name]/100*16)
        if self.motion:filled=min(filled,max(0,int((time.monotonic()-self.opened)/.032)))
        for i in range(16):
            x=33+i*17; r=QRectF(x,y+51,13,24)
            self.box(p,r,'#202C36',2)
            if i<filled:
                pulse=.82+.18*math.sin(self.phase*1.8) if self.motion and val is not None and val<30 else 1.
                for spread,alpha in [(5,9),(3,17),(1,30)]:
                    glow=QColor(color);glow.setAlpha(round(alpha*pulse))
                    p.setPen(Qt.NoPen);p.setBrush(glow);p.drawRoundedRect(r.adjusted(-spread,-spread,spread,spread),3,3)
                c=QColor(color);c.setAlpha(round(225*pulse))
                p.setBrush(c);p.setPen(Qt.NoPen);p.drawRoundedRect(r.adjusted(0,-1 if i==filled-1 else 0,0,1 if i==filled-1 else 0),2,2)
                p.setPen(QPen(QColor(255,255,255,90),1));p.drawLine(QPointF(x+2,y+53),QPointF(x+11,y+53))
        p.setPen(QPen(QColor(0,0,0,25),1))
        for yy in range(int(y)+2,int(y)+height-1,4):p.drawLine(QPointF(22,yy),QPointF(310,yy))
        if data:
            wins=sorted(data['windows'],key=lambda z:z['remaining'])
            for i,w in enumerate(wins):
                yy=y+92+i*32
                label=w['label'][:16]
                self.text(p,33,yy,f"{label}  {round(w['remaining'])}% left",8,MUTED)
                self.text(p,192,yy,countdown(w['reset']),8,MUTED)
                forecast=self.history.estimate(name,w,time.time(),bool(error or stale))
                self.text(p,33,yy+14,forecast['text'],7,AMBER if forecast['kind']=='early' else MINT if forecast['kind']=='safe' else MUTED)
        else:self.text(p,33,y+96,self.errors.get(name,'Waiting for account connection'),8,MUTED)

    def set_motion(self,enabled):
        self.motion=enabled;self.tick.setInterval(16 if self.expanded and enabled else 250)
        (STATE/'preferences.json').write_text(json.dumps({'motion':enabled}))

    def update_connections(self):
        if not hasattr(self,'connections'):return
        self.connections.clear()
        for name,descriptor in self.providers.items():
            if descriptor['kind']=='detected':
                action=self.connections.addAction(name+' : usage unavailable');action.setEnabled(False)
        self.connections.setEnabled(bool(self.connections.actions()))

    def ordered_names(self):
        return [name for name,descriptor in self.providers.items() if descriptor['kind']=='meter']

    def panel_height(self,name):
        data=self.data.get(name,{})
        if self.providers[name]['kind']!='meter':return 88
        if data.get('kind') in ('balance','local'):return 124
        return 96+32*max(1,len(data.get('windows',[])))

    def content_height(self):return sum(self.panel_height(n)+10 for n in self.ordered_names())

    def set_scroll(self,value):
        self.scroll=max(0,min(float(value),max(0,self.content_height()-(self.height()-108))))
        self.update()

    def wheelEvent(self,event):
        delta=event.pixelDelta().y() or event.angleDelta().y()/2
        target=max(0,min(self.scroll-delta,max(0,self.content_height()-(self.height()-108))))
        self.scroll_anim.stop();self.scroll_anim.setStartValue(self.scroll);self.scroll_anim.setEndValue(target);self.scroll_anim.start()
        event.accept()

    def status_card(self,p,y,name):
        descriptor=self.providers[name];data=self.data.get(name,{})
        kind=data.get('kind') or descriptor['kind'];h=self.panel_height(name)
        self.box(p,QRectF(20,y,292,h),'#0B131D',6,'#213E48')
        self.text(p,33,y+23,name.upper(),9,TEXT,True)
        stale=bool(self.errors.get(name)) or (name in self.updated and time.time()-self.updated[name]>300)
        if kind=='balance':
            value=data.get('balance');text=f"${value:,.2f}" if value is not None else 'No key cap'
            self.text(p,33,y+57,text,23,MUTED if stale else MINT,True)
            self.text(p,33,y+78,'LAST KNOWN BALANCE' if stale else 'AVAILABLE '+data.get('unit',''),7,MUTED)
            self.text(p,33,y+102,data.get('detail','API balance'),8,MUTED)
        elif kind=='local':
            self.text(p,33,y+51,'LOCAL',18,MUTED if stale else MINT,True)
            self.text(p,33,y+73,data.get('detail','Local runtime'),8,MUTED)
            self.text(p,33,y+98,', '.join(data.get('models',[])) or 'No models currently loaded',8,MUTED)
        else:
            self.text(p,33,y+47,descriptor.get('detail','Usage unavailable'),9,MUTED)
            self.text(p,33,y+68,descriptor.get('subtitle','Detected on this PC'),7,MUTED)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        outer=QRectF(1,1,self.width()-2,self.height()-2)
        grad=QLinearGradient(0,0,self.width(),self.height());grad.setColorAt(0,QColor('#14212B'));grad.setColorAt(1,QColor('#080E17'))
        p.setBrush(grad);p.setPen(QPen(QColor('#3A495E'),1));p.drawRoundedRect(outer,16+6*self.progress,16+6*self.progress)
        if self.progress<.45:
            p.setOpacity(max(0,1-self.progress*2.2))
            for x,name,color in [(17,'Codex',MINT),(43,'Claude',AMBER)]:
                self.box(p,QRectF(x,10,17,12),'#384354',4)
                val=effective(self.data.get(name))
                c=QColor(meter_color(val) if name not in self.errors else MUTED)
                c.setAlpha(round(180+50*math.sin(self.phase)))
                p.setBrush(c);p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(x,10,max(3,17*(val or 0)/100),12),4,4)
            p.end();return
        p.setOpacity(min(1,(self.progress-.45)/.55))
        self.text(p,22,32,'F U E L',11,TEXT,True)
        self.text(p,22,51,'DEMO DATA / AI ENERGY RESERVES' if getattr(self,'demo',False) else 'FORECAST AT YOUR RECENT PACE',7,MUTED)
        meters=[n for n,d in self.providers.items() if d['kind']=='meter']
        live=bool(meters and all(n in self.updated and n not in self.errors and time.time()-self.updated[n]<300 for n in meters))
        self.box(p,QRectF(264,22,6,6),MINT if live else AMBER,3)
        self.text(p,277,29,'LIVE' if live else 'SYNC',7,MUTED,True)
        p.setPen(QPen(QColor('#2A3546'),1));p.drawLine(QPointF(22,64),QPointF(310,64))
        p.save();p.setClipRect(QRectF(14,72,304,max(0,self.height()-108)))
        self.scroll=min(self.scroll,max(0,self.content_height()-(self.height()-108)))
        y=76-self.scroll
        for name in self.ordered_names():
            h=self.panel_height(name)
            if y+h>=72 and y<self.height()-36:
                if self.providers[name]['kind']=='meter' and self.data.get(name,{}).get('kind') not in ('balance','local'):self.energy_meter(p,y,name)
                else:self.status_card(p,y,name)
            y+=h+10
        p.restore()
        footer=self.height()-30
        p.setPen(QPen(QColor('#2A3546'),1));p.drawLine(QPointF(22,footer),QPointF(310,footer))
        age=int(time.time()-min(self.updated.values())) if self.updated else None
        self.text(p,22,footer+18,'Syncing...' if age is None else f'Updated {age//60}m ago' if age>=60 else 'Just updated',8,MUTED)
        more=self.content_height()>self.height()-108
        self.text(p,185,footer+18,f'SCROLL / {len(self.ordered_names())} METERS' if more else 'RIGHT-CLICK FOR OPTIONS',6,MUTED)
        p.end()

def main():
    if '--resume' in sys.argv:
        (STATE/'paused').unlink(missing_ok=True)
    if (STATE/'paused').exists():return
    kernel=None; mutex=None; lock=None
    if sys.platform=='win32':
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateMutexW.restype=ctypes.c_void_p
        mutex=kernel.CreateMutexW(None,False,'Local\\FuelWidgetV1')
        if not mutex or ctypes.get_last_error()==183:return
    elif sys.platform=='darwin':
        import fcntl
        lock=(STATE/'widget.lock').open('a+')
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
    else:
        raise RuntimeError('Fuel supports Windows and macOS only')
    app=QApplication(sys.argv);app.setQuitOnLastWindowClosed(False)
    widget=FuelWidget()
    logger.info('Started pid=%s',os.getpid())
    try: sys.exit(app.exec())
    finally:
        if kernel:
            kernel.CloseHandle.argtypes=[ctypes.c_void_p];kernel.CloseHandle(mutex)
        if lock:lock.close()

if __name__=='__main__':main()
