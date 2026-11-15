"""Latest-request-only background processing feeding a local media player."""
from pathlib import Path
import copy,tempfile,uuid
from PySide6.QtCore import QObject,QThread,Signal,QUrl
from PySide6.QtMultimedia import QMediaPlayer
from audio_import import ImportCancelled
from offline_audio import OfflineRenderer,write_wave_atomic


class AudioRenderWorker(QThread):
    result=Signal(int,object,str,bool)

    def __init__(self,root,effects,job,destination,parent=None):
        super().__init__(parent);self.root=root;self.effects=effects;self.job=job;self.destination=Path(destination)

    def run(self):
        job=self.job;export=bool(job.get('export'))
        try:
            renderer=OfflineRenderer(self.root,self.effects,self.isInterruptionRequested,job.get('fade_ms',6))
            if job['kind']=='sound':data=renderer.sound(job['name'],job.get('setting'),job.get('gain_scale',1))
            elif job['kind']=='item':
                data=renderer.item(job['item'])
                if data is None:raise ValueError('此成员缺失或已被裁空。')
                data=data*job['item'].gain
            else:data=renderer.combo(job['combo'],full=True,from_row=job.get('from_row'),master=job.get('master'),randomize=not export,gain_scale=job.get('gain_scale',1))
            if export and self.destination.exists() and self.destination.resolve().is_relative_to(Path(self.root).resolve()):
                raise ValueError('不能覆盖音效库原文件，请导出为新文件。')
            write_wave_atomic(self.destination,data,self.isInterruptionRequested)
            self.result.emit(job['generation'],self.destination,'',export)
        except ImportCancelled:pass
        except Exception as exc:self.result.emit(job['generation'],None,str(exc),export)


class LocalAudition(QObject):
    status=Signal(str)
    failed=Signal()

    def __init__(self,root,effects,player,parent=None):
        super().__init__(parent);self.root=Path(root);self.effects=effects;self.player=player
        self.worker=None;self.pending=None;self.generation=0;self.temporary=None;self.closed=False

    def _clean(self):
        if self.temporary:
            for path in Path(self.temporary.name).glob('*.wav'):
                try:path.unlink(missing_ok=True)
                except OSError:pass

    def request(self,job,effects=None):
        if self.closed:return
        self.generation+=1;self.player.stop();self.player.setSource(QUrl());self._clean()
        job=copy.deepcopy(job);job['generation']=self.generation
        if self.temporary is None:self.temporary=tempfile.TemporaryDirectory(prefix='ff14-audition-',ignore_cleanup_errors=True)
        destination=Path(job['export']) if job.get('export') else Path(self.temporary.name)/(uuid.uuid4().hex+'.wav')
        self.pending=(copy.deepcopy(effects if effects is not None else self.effects),job,destination)
        self.status.emit('正在处理'+('导出…' if job.get('export') else '本地试听…'))
        if self.worker:self.worker.requestInterruption()
        else:self._start_pending()

    def _start_pending(self):
        if self.pending is None:return
        effects,job,destination=self.pending;self.pending=None
        worker=AudioRenderWorker(self.root,effects,job,destination,self);self.worker=worker
        worker.result.connect(self._result);worker.finished.connect(lambda w=worker:self._finished(w));worker.start()

    def _result(self,generation,path,error,export):
        if self.closed or generation!=self.generation:return
        if error:
            if not export:self.failed.emit()
            self.status.emit(('导出失败：' if export else '试听失败：')+error)
            return
        if export:self.status.emit('已导出：'+Path(path).name)
        else:
            self.player.setSource(QUrl.fromLocalFile(str(path)));self.player.play();self.status.emit('正在本地试听；不发送至语音，不占公共冷却。')

    def _finished(self,worker):
        if self.worker is worker:self.worker=None;self._start_pending()
        worker.deleteLater()

    def stop(self,wait=False):
        self.generation+=1;self.pending=None;self.player.stop();self.player.setSource(QUrl())
        worker=self.worker
        if worker:
            worker.requestInterruption()
            if wait:worker.wait();self.worker=None;worker.deleteLater()
        self._clean()

    def shutdown(self):
        if self.closed:return
        self.closed=True;self.stop(wait=True)
        if self.temporary:self.temporary.cleanup();self.temporary=None
